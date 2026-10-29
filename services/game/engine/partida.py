"""A partida: criação, distribuição das mãos e as ações dos jogadores
(docs/guia-backend-mesa.md, seções 4, 5 e 6).

Estado completo, como o servidor guarda. As cartas de todos ficam aqui, inclusive as jogadas
cobertas, com o valor de verdade: quem esconde o que cada jogador não pode ver é visao.py.

    {
      "partida_id": "...", "sala_id": "..." ou None, "formato": "1x1" ou "2x2",
      "status": "em_andamento" ou "encerrada", "vencedor_time": None, "A" ou "B",
      "jogadores": [{"assento", "usuario_id", "nome", "time", "bot", "mao": ["7O", ...]}],
      "placar": {"A": 0, "B": 0},
      "mao_atual": {
        "numero", "pe", "vira", "valor", "tipo", "truco_pendente", "ultimo_aumento_time",
        "aguardando_decisao_mao_de_onze", "rodadas", "vez_assento",
        "encerrada": False,  # só do servidor: a mão acabou e a próxima ainda não foi distribuída
      },
      # cada item de "rodadas":
      #   {"jogadas": [{"assento", "carta", "coberta"}], "vencedor_time", "vencedor_assento"}
      "chat": [{"de", "texto"}],
    }

Campos a mais que a camada de serviço acrescente (como "criada_em") passam intactos.

Regras adotadas:
- Truco: o valor da mão vai de 1 para 3, 6, 9 e 12. "valor" é sempre quanto a mão vale agora,
  isto é, quanto o adversário ganha se alguém correr. Ele muda no aceite e no "aumentar" (que
  aceita o pedido anterior e faz o seguinte), nunca no pedido. O mesmo time não aumenta duas
  vezes seguidas: quem teve o último pedido aceito ("ultimo_aumento_time") espera o adversário.
  Só se pede truco na própria vez, numa mão "normal".
- Mão de onze (um time com 11): o time com 11 decide antes de qualquer carta. Jogando, a mão
  vale 3; correndo, o adversário ganha 1 (o "valor" mostrado durante a decisão). Não há truco.
- Mão de ferro (11 a 11): só marca o tipo e bloqueia o truco. As cartas são jogadas à vista,
  como numa mão comum, valendo 1 (decisão do grupo). Quem vencer a mão chega a 12.
- Ninguém passa de 12 pontos no placar: aos 12 a partida termina.
- Rodadas, empates e quem abre cada rodada: ver regras.py.
"""

import copy
import random

from engine.cartas import baralho_embaralhado, manilha
from engine.erros import AssentosInvalidos, ErroJogada
from engine.regras import outro_time, resultado_da_mao, resultado_da_rodada, time_do_assento

PONTOS_PARA_VENCER = 12
CARTAS_POR_JOGADOR = 3
NOME_MAX = 20  # o mesmo limite do cadastro no Auth

# Próximo valor da mão a cada pedido: truco (3), seis, nove e doze.
PROXIMO_VALOR = {1: 3, 3: 6, 6: 9, 9: 12}
VALOR_MAO_DE_ONZE = 3

LIMITE_CHAT = 50  # mensagens guardadas
TAMANHO_CHAT = 200  # caracteres por mensagem

NOME_DO_TIPO = {"mao_de_onze": "mão de onze", "mao_de_ferro": "mão de ferro"}


# ---------- Criação e distribuição ----------


def criar_partida(partida_id: str, sala_id: str | None, assentos: list[dict], rng: random.Random) -> dict:
    """Cria a partida já com a primeira mão distribuída: a tela não tem tela de espera, e todo
    "estado" precisa de uma mao_atual (guia da mesa, seção 3.3).

    assentos: [{"assento", "usuario_id", "nome", "bot"}], o corpo do POST /interno/partidas.
    Levanta AssentosInvalidos quando a lista não forma uma mesa 1x1 ou 2x2 válida.
    """
    _validar_assentos(assentos)
    estado = {
        "partida_id": partida_id,
        "sala_id": sala_id,
        "formato": "1x1" if len(assentos) == 2 else "2x2",
        "status": "em_andamento",
        "vencedor_time": None,
        "jogadores": [
            {
                "assento": a["assento"],
                "usuario_id": None if a["bot"] else a["usuario_id"],
                "nome": a["nome"].strip(),
                "time": time_do_assento(a["assento"]),
                "bot": a["bot"],
                "mao": [],
            }
            for a in sorted(assentos, key=lambda a: a["assento"])
        ],
        "placar": {"A": 0, "B": 0},
        "mao_atual": None,
        "chat": [],
    }
    _distribuir_mao(estado, rng)
    return estado


def aguardando_proxima_mao(estado: dict) -> bool:
    """A mão terminou, a partida não, e a próxima mão ainda não foi distribuída. A camada de
    serviço espera uns 2 segundos e chama iniciar_proxima_mao (guia da mesa, seção 6.4)."""
    return estado["status"] == "em_andamento" and estado["mao_atual"]["encerrada"]


def iniciar_proxima_mao(estado: dict, rng: random.Random) -> dict:
    """Distribui a mão seguinte. Só vale enquanto aguardando_proxima_mao(estado)."""
    if not aguardando_proxima_mao(estado):
        raise ValueError("A mão atual ainda não terminou, ou a partida já acabou.")
    novo = copy.deepcopy(estado)
    _distribuir_mao(novo, rng)
    return novo


def _validar_assentos(assentos: list[dict]) -> None:
    quantidade = len(assentos)
    if quantidade not in (2, 4):
        raise AssentosInvalidos("A partida precisa de 2 assentos (1x1) ou 4 (2x2).")
    if sorted(a["assento"] for a in assentos) != list(range(quantidade)):
        raise AssentosInvalidos(f"Os assentos precisam ser numerados de 0 a {quantidade - 1}, sem repetir.")
    usuarios = set()
    for a in assentos:
        if not a["nome"].strip() or len(a["nome"].strip()) > NOME_MAX:
            raise AssentosInvalidos(f"O nome de cada assento precisa ter de 1 a {NOME_MAX} caracteres.")
        if a["bot"]:
            if a["usuario_id"] is not None:
                raise AssentosInvalidos("Assento de bot não tem usuario_id.")
            continue
        if not a["usuario_id"]:
            raise AssentosInvalidos("Assento de jogador precisa do usuario_id.")
        if a["usuario_id"] in usuarios:
            raise AssentosInvalidos("O mesmo usuário não pode ocupar dois assentos.")
        usuarios.add(a["usuario_id"])


def _tipo_da_mao(placar: dict) -> str:
    if placar["A"] == 11 and placar["B"] == 11:
        return "mao_de_ferro"
    if placar["A"] == 11 or placar["B"] == 11:
        return "mao_de_onze"
    return "normal"


def _distribuir_mao(estado: dict, rng: random.Random) -> None:
    """Embaralha, dá 3 cartas a cada jogador e vira a carta seguinte. O pé (quem dá as cartas)
    passa para o assento seguinte a cada mão, e joga primeiro quem está depois do pé: na
    primeira mão, o assento 0."""
    quantidade = len(estado["jogadores"])
    anterior = estado["mao_atual"]
    pe = (anterior["pe"] + 1) % quantidade if anterior else quantidade - 1
    baralho = baralho_embaralhado(rng)
    for jogador in estado["jogadores"]:
        jogador["mao"] = [baralho.pop() for _ in range(CARTAS_POR_JOGADOR)]
    tipo = _tipo_da_mao(estado["placar"])
    estado["mao_atual"] = {
        "numero": anterior["numero"] + 1 if anterior else 1,
        "pe": pe,
        "vira": baralho.pop(),
        "valor": 1,
        "tipo": tipo,
        "truco_pendente": None,
        "ultimo_aumento_time": None,
        "aguardando_decisao_mao_de_onze": tipo == "mao_de_onze",
        "rodadas": [],
        "vez_assento": (pe + 1) % quantidade,
        "encerrada": False,
    }


# ---------- Ações ----------


def aplicar_acao(estado: dict, assento: int, mensagem: object) -> dict:
    """Aplica a mensagem enviada pelo jogador do assento e devolve o novo estado.

    mensagem: o JSON recebido pela conexão, já lido (guia da mesa, seção 5). Ação que não vale,
    ou mensagem fora do formato, levanta ErroJogada, e o estado recebido continua igual.
    """
    tipo = mensagem.get("tipo") if isinstance(mensagem, dict) else None
    acao = ACOES.get(tipo) if isinstance(tipo, str) else None
    if acao is None:
        raise ErroJogada("acao_invalida", "Mensagem desconhecida.")
    novo = copy.deepcopy(estado)
    jogador = next((j for j in novo["jogadores"] if j["assento"] == assento), None)
    if jogador is None:
        raise ValueError(f"Não há assento {assento} nesta partida.")
    acao(novo, jogador, mensagem)
    return novo


def numero_da_proxima_rodada(mao: dict) -> int:
    """Rodada da próxima carta (1, 2 ou 3). A rodada nova só entra em "rodadas" com a primeira
    carta dela, para a rodada encerrada continuar na mesa até alguém abrir a seguinte."""
    rodadas = mao["rodadas"]
    if not rodadas:
        return 1
    return len(rodadas) + 1 if rodadas[-1]["vencedor_time"] else len(rodadas)


def _exigir_mao_em_jogo(estado: dict) -> None:
    if estado["status"] == "encerrada":
        raise ErroJogada("acao_invalida", "A partida já terminou.")
    if estado["mao_atual"]["encerrada"]:
        raise ErroJogada("acao_invalida", "A mão terminou. Aguarde a próxima.")


def _encerrar_mao(estado: dict, time: str | None, pontos: int) -> None:
    """Fim da mão: o time vencedor (None quando ninguém pontua) ganha os pontos. Aos 12 a
    partida termina; senão a mão fica encerrada, à espera da próxima."""
    mao = estado["mao_atual"]
    mao["vez_assento"] = None
    mao["truco_pendente"] = None
    mao["aguardando_decisao_mao_de_onze"] = False
    mao["encerrada"] = True
    if time is None:
        return
    estado["placar"][time] = min(PONTOS_PARA_VENCER, estado["placar"][time] + pontos)
    if estado["placar"][time] == PONTOS_PARA_VENCER:
        estado["status"] = "encerrada"
        estado["vencedor_time"] = time


def _jogar_carta(estado: dict, jogador: dict, mensagem: dict) -> None:
    carta = mensagem.get("carta")
    coberta = mensagem.get("coberta", False)  # a tela sempre manda; ausente vale false
    if not isinstance(carta, str) or not isinstance(coberta, bool):
        raise ErroJogada("acao_invalida", "Jogada inválida.")
    _exigir_mao_em_jogo(estado)
    mao = estado["mao_atual"]
    if mao["vez_assento"] != jogador["assento"]:
        raise ErroJogada("fora_da_vez", "Não é a sua vez.")
    if mao["aguardando_decisao_mao_de_onze"]:
        raise ErroJogada("acao_invalida", "Aguarde a decisão da mão de onze.")
    if mao["truco_pendente"]:
        raise ErroJogada("acao_invalida", "O pedido de truco ainda não foi respondido.")
    if carta not in jogador["mao"]:
        raise ErroJogada("carta_invalida", "Você não tem essa carta.")
    if coberta and numero_da_proxima_rodada(mao) == 1:
        raise ErroJogada("carta_invalida", "Na primeira rodada não dá para jogar coberta.")

    jogador["mao"].remove(carta)
    rodadas = mao["rodadas"]
    if not rodadas or rodadas[-1]["vencedor_time"]:
        rodadas.append({"jogadas": [], "vencedor_time": None, "vencedor_assento": None})
    rodada = rodadas[-1]
    rodada["jogadas"].append({"assento": jogador["assento"], "carta": carta, "coberta": coberta})

    quantidade = len(estado["jogadores"])
    if len(rodada["jogadas"]) < quantidade:
        mao["vez_assento"] = (jogador["assento"] + 1) % quantidade
        return

    # Rodada completa: vencedor da rodada e, se já der, da mão. Fora do empate, quem abre a
    # próxima é quem jogou a carta vencedora: é ela que a mesa destaca (vencedor_assento).
    vencedor, abre_a_proxima = resultado_da_rodada(rodada["jogadas"], manilha(mao["vira"]))
    rodada["vencedor_time"] = vencedor
    rodada["vencedor_assento"] = None if vencedor == "empate" else abre_a_proxima
    vencedor_da_mao = resultado_da_mao([r["vencedor_time"] for r in rodadas])
    if vencedor_da_mao is None:
        mao["vez_assento"] = abre_a_proxima
    else:
        _encerrar_mao(estado, None if vencedor_da_mao == "empate" else vencedor_da_mao, mao["valor"])


def _pedir_truco(estado: dict, jogador: dict, mensagem: dict) -> None:
    _exigir_mao_em_jogo(estado)
    mao = estado["mao_atual"]
    if mao["vez_assento"] != jogador["assento"]:
        raise ErroJogada("fora_da_vez", "Só dá para pedir truco na sua vez.")
    if mao["tipo"] != "normal":
        raise ErroJogada("acao_invalida", f"Não se pede truco na {NOME_DO_TIPO[mao['tipo']]}.")
    if mao["truco_pendente"]:
        raise ErroJogada("acao_invalida", "Já há um pedido de truco esperando resposta.")
    if mao["valor"] >= PONTOS_PARA_VENCER:
        raise ErroJogada("acao_invalida", "A mão já vale 12.")
    if mao["ultimo_aumento_time"] == jogador["time"]:
        raise ErroJogada("acao_invalida", "Seu time fez o último aumento: agora só o adversário pode pedir.")
    mao["truco_pendente"] = {"pedido_por_time": jogador["time"], "valor_proposto": PROXIMO_VALOR[mao["valor"]]}


def _responder_truco(estado: dict, jogador: dict, mensagem: dict) -> None:
    """No 2x2, qualquer jogador do time desafiado responde, e vale a primeira resposta: a
    segunda já não encontra pedido pendente."""
    _exigir_mao_em_jogo(estado)
    mao = estado["mao_atual"]
    pedido = mao["truco_pendente"]
    if not pedido:
        raise ErroJogada("acao_invalida", "Não há pedido de truco para responder.")
    if pedido["pedido_por_time"] == jogador["time"]:
        raise ErroJogada("nao_autorizado", "Quem responde ao truco é o time adversário.")

    resposta = mensagem.get("resposta")
    if resposta == "aceitar":
        mao["valor"] = pedido["valor_proposto"]
        mao["ultimo_aumento_time"] = pedido["pedido_por_time"]
        mao["truco_pendente"] = None
    elif resposta == "correr":
        # Quem pediu ganha o que a mão vale agora, antes do pedido.
        _encerrar_mao(estado, pedido["pedido_por_time"], mao["valor"])
    elif resposta == "aumentar":
        if pedido["valor_proposto"] >= PONTOS_PARA_VENCER:
            raise ErroJogada("acao_invalida", "A aposta já está em 12.")
        # Aumentar aceita o pedido anterior e faz um novo, um nível acima.
        mao["valor"] = pedido["valor_proposto"]
        mao["ultimo_aumento_time"] = pedido["pedido_por_time"]
        mao["truco_pendente"] = {
            "pedido_por_time": jogador["time"],
            "valor_proposto": PROXIMO_VALOR[pedido["valor_proposto"]],
        }
    else:
        raise ErroJogada("acao_invalida", "Resposta inválida.")


def _decidir_mao_de_onze(estado: dict, jogador: dict, mensagem: dict) -> None:
    """No 2x2, qualquer um dos parceiros com 11 decide, e vale a primeira decisão."""
    _exigir_mao_em_jogo(estado)
    mao = estado["mao_atual"]
    if not mao["aguardando_decisao_mao_de_onze"]:
        raise ErroJogada("acao_invalida", "Não há decisão de mão de onze pendente.")
    if estado["placar"][jogador["time"]] != 11:
        raise ErroJogada("nao_autorizado", "Quem decide a mão de onze é o time com 11 pontos.")
    jogar = mensagem.get("jogar")
    if not isinstance(jogar, bool):
        raise ErroJogada("acao_invalida", "Decisão inválida.")
    mao["aguardando_decisao_mao_de_onze"] = False
    if jogar:
        mao["valor"] = VALOR_MAO_DE_ONZE
    else:
        _encerrar_mao(estado, outro_time(jogador["time"]), mao["valor"])


def _escrever_no_chat(estado: dict, jogador: dict, mensagem: dict) -> None:
    """O chat vale a qualquer momento, inclusive entre as mãos e depois do fim da partida."""
    texto = mensagem.get("texto")
    limpo = texto.strip()[:TAMANHO_CHAT] if isinstance(texto, str) else ""
    if not limpo:
        raise ErroJogada("acao_invalida", "A mensagem está vazia.")
    estado["chat"].append({"de": jogador["nome"], "texto": limpo})
    del estado["chat"][:-LIMITE_CHAT]


# Mensagens que a mesa envia: "tipo" -> ação. Cada ação recebe o estado (já copiado), o
# jogador que enviou e a mensagem, e muda o estado ou levanta ErroJogada.
ACOES = {
    "jogar_carta": _jogar_carta,
    "pedir_truco": _pedir_truco,
    "responder_truco": _responder_truco,
    "decidir_mao_de_onze": _decidir_mao_de_onze,
    "chat": _escrever_no_chat,
}
