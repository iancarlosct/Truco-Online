"""Estratégia do bot, nível "padrao" (o único por enquanto).

Como o bot pensa
----------------
O bot é um jogador como outro qualquer: só sabe o que a mensagem "estado" mostra para o assento
dele (docs/guia-backend-mesa.md, seção 4). Ele vê as próprias cartas, a vira, as cartas abertas
na mesa, o placar e de quem é a vez. Não vê as cartas dos adversários.

A cada "estado" recebido, a função decidir() responde uma de duas coisas:
- a mensagem que o bot envia ao Game, uma das mesmas que a tela envia (jogar_carta,
  pedir_truco, responder_truco ou decidir_mao_de_onze, seção 5 do guia);
- None, quando não cabe ao bot fazer nada agora.

Este arquivo não conversa com a rede nem espera nada: recebe o estado e devolve a decisão. Por
isso cada situação pode ser testada sem subir nenhum serviço (tests/estrategia).

A nota da mão
-------------
Para o truco e a mão de onze, o bot dá uma nota à mão, somando:
- os pontos de cada carta que ainda tem na mão (cartas.pontos: zap 5, outra manilha 4, o 3 vale
  3, o 2 vale 2, o ás vale 1 e o resto 0);
- os pontos da carta do time que está ganhando a rodada em andamento, se houver uma;
- 3 pontos por rodada que o time já ganhou nesta mão, e menos 3 por rodada que já perdeu.

Com a nota, ele classifica a mão:

    nota >= 8   muito forte   pede truco; desafiado, aumenta (seis, nove, doze)
    nota >= 6   forte         pede truco; desafiado, aceita
    nota >= 3   razoável      não pede; desafiado, aceita
    nota <  3   fraca         não pede; desafiado, corre

Exemplos, no começo da mão: zap + 3 = 8 (muito forte); manilha + 2 = 6 (forte); um 3 sozinho = 3
(razoável); K, J e 7 = 0 (fraca).
"""

import random

from app.cartas import forca, forca_da_jogada, manilha, pontos

# ---------- Limites ----------

NOTA_RAZOAVEL = 3
NOTA_FORTE = 6
NOTA_MUITO_FORTE = 8
# Na mão de onze, o time com 11 joga se a nota passar disto (decidir_mao_de_onze).
NOTA_MAO_DE_ONZE = 5
# Quanto vale, na nota, cada rodada que o time já ganhou (ou perdeu, com o sinal trocado).
PONTOS_POR_RODADA = 3
# Nota de uma mão que já está ganha: o bot é o último a jogar na rodada que decide a mão e tem
# carta para vencê-la (resultado_garantido).
NOTA_GARANTIDA = 99

# Chance de blefar: pedir truco com a mão fraca, na primeira carta da mão, para ver se o
# adversário corre. Baixa de propósito: um bot que blefa sempre é fácil de pegar.
CHANCE_DE_BLEFE = 0.08

VALOR_MAXIMO = 12

# Força de um lado que ainda não jogou na rodada em andamento: menor até que a de uma coberta.
SEM_CARTA = -2


# ---------- A decisão ----------


def decidir(estado: dict, rng: random.Random, seguro: bool = False) -> dict | None:
    """A mensagem que o bot deve enviar agora, ou None se não cabe a ele agir.

    rng: o sorteio do bot, usado só no blefe. Com uma semente fixa (random.Random(42)), as
    decisões se repetem, o que os testes aproveitam.
    seguro: depois de uma ação recusada pelo Game (que não deveria acontecer), o bot tenta uma
    jogada simples: carta aberta e sem truco.
    """
    if estado.get("status") != "em_andamento":
        return None  # partida encerrada: só o chat valeria, e o bot não conversa
    mao = estado["mao_atual"]
    if mao.get("vez_assento") is None:
        return None  # pausa entre as mãos: ninguém age até a próxima ser distribuída
    time = meu_time(estado)

    # 1. Mão de onze: antes de qualquer carta, o time com 11 pontos decide se joga ou corre.
    #    Enquanto isso, ninguém joga carta.
    if mao.get("aguardando_decisao_mao_de_onze"):
        if estado["placar"][time] == 11 and responde_pelo_time(estado):
            return {"tipo": "decidir_mao_de_onze", "jogar": deve_jogar_mao_de_onze(estado)}
        return None

    # 2. Pedido de truco esperando resposta. Quem responde é o time desafiado; enquanto isso,
    #    ninguém joga carta.
    pedido = mao.get("truco_pendente")
    if pedido:
        if pedido["pedido_por_time"] != time and responde_pelo_time(estado):
            return {"tipo": "responder_truco", "resposta": resposta_ao_truco(estado)}
        return None

    # 3. A vez é do bot: ele pede truco ou joga uma carta.
    if mao["vez_assento"] != estado["meu_assento"]:
        return None
    if not seguro and pode_pedir_truco(estado) and deve_pedir_truco(estado, rng):
        return {"tipo": "pedir_truco"}
    return escolher_carta(estado, seguro)


# ---------- Quem é quem ----------


def meu_jogador(estado: dict) -> dict:
    """O item do próprio bot em "jogadores". É o único que traz a "mao" (fora a mão de onze)."""
    return next(j for j in estado["jogadores"] if j["assento"] == estado["meu_assento"])


def meu_time(estado: dict) -> str:
    return meu_jogador(estado)["time"]


def outro_time(time: str) -> str:
    return "B" if time == "A" else "A"


def parceiro(estado: dict) -> dict | None:
    """O parceiro do bot no 2x2 (o outro jogador do mesmo time), ou None no 1x1."""
    eu = meu_jogador(estado)
    return next((j for j in estado["jogadores"] if j["time"] == eu["time"] and j is not eu), None)


def responde_pelo_time(estado: dict) -> bool:
    """Se é este bot quem responde ao truco e decide a mão de onze pelo time.

    No 2x2, os dois jogadores do time podem responder, e vale a primeira resposta que chega ao
    Game (guia da mesa, seção 5.3). Para o bot não passar na frente de uma pessoa nem responder
    junto com outro bot:
    - no 1x1, o bot responde sempre: ele é o time inteiro;
    - com um parceiro humano, o bot nunca responde: a decisão é da pessoa;
    - com um parceiro bot, responde só o de menor assento.
    """
    companheiro = parceiro(estado)
    if companheiro is None:
        return True
    if not companheiro.get("bot"):
        return False
    return estado["meu_assento"] < companheiro["assento"]


# ---------- Rodadas ----------


def numero_da_proxima_rodada(mao: dict) -> int:
    """Rodada da próxima carta (1, 2 ou 3). A rodada nova só aparece em "rodadas" com a
    primeira carta dela (guia da mesa, seção 4.1)."""
    rodadas = mao["rodadas"]
    if not rodadas:
        return 1
    return len(rodadas) + 1 if rodadas[-1].get("vencedor_time") else len(rodadas)


def rodada_em_andamento(mao: dict) -> list[dict]:
    """As cartas da rodada em andamento, na ordem em que foram jogadas. Lista vazia quando a
    próxima carta abre uma rodada nova."""
    rodadas = mao["rodadas"]
    if rodadas and not rodadas[-1].get("vencedor_time"):
        return rodadas[-1].get("jogadas", [])
    return []


def resultados(mao: dict) -> list[str]:
    """Quem venceu cada rodada já terminada desta mão: "A", "B" ou "empate"."""
    return [r["vencedor_time"] for r in mao["rodadas"] if r.get("vencedor_time")]


def vencedor_da_mao(resultados_das_rodadas: list[str]) -> str | None:
    """Quem leva a mão com estes resultados, pela regra do Game (guia da mesa, seção 10.2): vence
    quem ganhar duas rodadas; havendo empate, vence quem ganhou a primeira rodada que não
    empatou. Devolve "A", "B", "empate" (três rodadas empatadas) ou None (a mão continua)."""
    for time in ("A", "B"):
        if resultados_das_rodadas.count(time) >= 2:
            return time
    primeiro_vencedor = next((r for r in resultados_das_rodadas if r != "empate"), None)
    if "empate" in resultados_das_rodadas and primeiro_vencedor:
        return primeiro_vencedor
    if len(resultados_das_rodadas) == 3:
        return "empate"
    return None


def melhores_da_mesa(estado: dict) -> tuple[int, int]:
    """Força da melhor carta do time do bot e da melhor carta do adversário na rodada em
    andamento. Quem ainda não jogou nela fica com SEM_CARTA."""
    mao = estado["mao_atual"]
    valor_da_manilha = manilha(mao["vira"])
    time = meu_time(estado)
    time_do_assento = {j["assento"]: j["time"] for j in estado["jogadores"]}
    nosso = deles = SEM_CARTA
    for jogada in rodada_em_andamento(mao):
        valor = forca_da_jogada(jogada, valor_da_manilha)
        if time_do_assento[jogada["assento"]] == time:
            nosso = max(nosso, valor)
        else:
            deles = max(deles, valor)
    return nosso, deles


# ---------- Cartas ----------


def jogar(carta: str, coberta: bool = False) -> dict:
    return {"tipo": "jogar_carta", "carta": carta, "coberta": coberta}


def escolher_carta(estado: dict, seguro: bool = False) -> dict | None:
    """Qual carta jogar, quando é a vez do bot (sem truco nem mão de onze pendente).

    - Abrindo a rodada (mesa vazia): joga a mais forte, para tentar ganhá-la. Exceção: se o time
      já ganhou uma rodada desta mão, joga a mais fraca e guarda a forte para a última.
    - O parceiro já está ganhando a rodada: descarta a mais fraca.
    - Senão, joga a MENOR carta que vence a mesa: ganha a rodada sem gastar à toa uma carta
      forte, que pode fazer falta depois.
    - Se nenhuma carta vence a mesa: descarta a mais fraca.

    Os descartes da segunda rodada em diante vão cobertos, para o adversário não ver a carta. A
    coberta não vale nada, mas um descarte não ia ganhar a rodada mesmo. Na primeira rodada, o
    Game não aceita carta coberta.
    """
    mao = estado["mao_atual"]
    valor_da_manilha = manilha(mao["vira"])
    cartas = sorted(meu_jogador(estado).get("mao") or [], key=lambda carta: forca(carta, valor_da_manilha))
    if not cartas:
        return None
    mais_fraca, mais_forte = cartas[0], cartas[-1]
    pode_cobrir = numero_da_proxima_rodada(mao) >= 2 and not seguro

    if not rodada_em_andamento(mao):
        ja_ganhamos_uma = meu_time(estado) in resultados(mao)
        return jogar(mais_fraca if ja_ganhamos_uma else mais_forte)

    nosso, deles = melhores_da_mesa(estado)
    if nosso > deles:
        return jogar(mais_fraca, coberta=pode_cobrir)
    for carta in cartas:  # da mais fraca para a mais forte: a primeira que vence é a menor
        if forca(carta, valor_da_manilha) > deles:
            return jogar(carta)
    return jogar(mais_fraca, coberta=pode_cobrir)


# ---------- A nota da mão ----------


def nota_da_mao(estado: dict, com_parceiro: bool = False) -> int:
    """A nota da mão do bot (explicada no começo do arquivo). Quanto maior, mais chance de o time
    levar a mão.

    com_parceiro: na mão de onze do 2x2, o time com 11 vê as cartas do parceiro (guia da mesa,
    seção 4.3). Aí a nota usa as três melhores cartas das duas mãos, que são as que o time vai
    usar nas três rodadas.
    """
    mao = estado["mao_atual"]
    valor_da_manilha = manilha(mao["vira"])
    time = meu_time(estado)

    garantido = resultado_garantido(estado)
    if garantido == time:
        return NOTA_GARANTIDA
    if garantido == outro_time(time):
        return 0

    cartas = list(meu_jogador(estado).get("mao") or [])
    companheiro = parceiro(estado)
    if com_parceiro and companheiro and companheiro.get("mao"):
        juntas = sorted(cartas + companheiro["mao"], key=lambda carta: forca(carta, valor_da_manilha), reverse=True)
        cartas = juntas[:3]
    nota = sum(pontos(carta, valor_da_manilha) for carta in cartas)

    # A carta do time que está ganhando a rodada em andamento ainda conta: ela já está na mesa,
    # mas pode levar a rodada.
    _nosso, deles = melhores_da_mesa(estado)
    time_do_assento = {j["assento"]: j["time"] for j in estado["jogadores"]}
    nossas_na_mesa = [
        j["carta"] for j in rodada_em_andamento(mao)
        if time_do_assento[j["assento"]] == time and not j.get("coberta") and j.get("carta")
    ]
    if nossas_na_mesa:
        melhor = max(nossas_na_mesa, key=lambda carta: forca(carta, valor_da_manilha))
        if forca(melhor, valor_da_manilha) > deles:
            nota += pontos(melhor, valor_da_manilha)

    for resultado in resultados(mao):
        if resultado == time:
            nota += PONTOS_POR_RODADA
        elif resultado == outro_time(time):
            nota -= PONTOS_POR_RODADA
    return nota


def resultado_garantido(estado: dict) -> str | None:
    """Às vezes o bot já sabe quem leva a mão: quando ele é o último a jogar na rodada e essa
    rodada decide a mão. Se ele tem carta para vencer a mesa (ou o parceiro já está ganhando), a
    mão é do time dele; se não tem, é do adversário. Devolve o time que leva a mão, ou None
    quando ainda não dá para saber."""
    mao = estado["mao_atual"]
    mesa = rodada_em_andamento(mao)
    if mao.get("vez_assento") != estado["meu_assento"] or len(mesa) != len(estado["jogadores"]) - 1:
        return None
    valor_da_manilha = manilha(mao["vira"])
    nosso, deles = melhores_da_mesa(estado)
    minha_melhor = max((forca(c, valor_da_manilha) for c in meu_jogador(estado).get("mao") or []), default=SEM_CARTA)
    melhor_do_time = max(nosso, minha_melhor)
    time = meu_time(estado)
    if melhor_do_time > deles:
        rodada = time
    elif melhor_do_time < deles:
        rodada = outro_time(time)
    else:
        rodada = "empate"
    vencedor = vencedor_da_mao(resultados(mao) + [rodada])
    return vencedor if vencedor in ("A", "B") else None


# ---------- Truco ----------


def pode_pedir_truco(estado: dict) -> bool:
    """As condições do Game para pedir truco (guia da mesa, seção 5.2): na própria vez, numa mão
    "normal", sem pedido pendente, valendo menos de 12 e sem ter sido o time do bot o último a
    ter um pedido aceito."""
    mao = estado["mao_atual"]
    return (
        mao.get("vez_assento") == estado["meu_assento"]
        and mao.get("tipo") == "normal"
        and not mao.get("truco_pendente")
        and not mao.get("aguardando_decisao_mao_de_onze")
        and mao["valor"] < VALOR_MAXIMO
        and mao.get("ultimo_aumento_time") != meu_time(estado)
    )


def deve_pedir_truco(estado: dict, rng: random.Random) -> bool:
    """Pede truco com a mão forte. Depois de um pedido já aceito (para pedir seis, nove ou doze),
    só com a mão muito forte. E, de vez em quando, blefa: com a mão fraca, na primeira carta da
    mão, pede truco para ver se o adversário corre."""
    mao = estado["mao_atual"]
    nota = nota_da_mao(estado)
    if mao["valor"] > 1:
        return nota >= NOTA_MUITO_FORTE
    if nota >= NOTA_FORTE:
        return True
    return numero_da_proxima_rodada(mao) == 1 and rng.random() < CHANCE_DE_BLEFE


def resposta_ao_truco(estado: dict) -> str:
    """Resposta a um pedido do adversário: aumenta com a mão muito forte (se a aposta ainda não
    chegou a 12), aceita com a mão razoável e corre com a mão fraca."""
    pedido = estado["mao_atual"]["truco_pendente"]
    nota = nota_da_mao(estado)
    if nota >= NOTA_MUITO_FORTE and pedido["valor_proposto"] < VALOR_MAXIMO:
        return "aumentar"
    if nota >= NOTA_RAZOAVEL:
        return "aceitar"
    return "correr"


# ---------- Mão de onze ----------


def deve_jogar_mao_de_onze(estado: dict) -> bool:
    """Na mão de onze, joga com uma mão boa e corre com uma fraca. Jogando, a mão vale 3: quem
    perder dá 3 pontos ao adversário. Correndo, o adversário ganha só 1. No 2x2, a nota usa
    também as cartas do parceiro, que o time com 11 enxerga."""
    return nota_da_mao(estado, com_parceiro=True) >= NOTA_MAO_DE_ONZE
