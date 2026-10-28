"""Rotas do Lobby: salas, assentos, bots, presença e início da partida (docs/guia-backend-lobby.md,
seção 3).

O gateway repassa o caminho inteiro (/api/lobby/salas chega aqui como /api/lobby/salas), por isso
o prefixo completo fica no APIRouter.

Cada rota faz as conferências na ordem das tabelas da seção 3 do guia, a mesma do mock da tela:
ela decide qual erro o jogador vê quando há mais de um problema ao mesmo tempo. O token vem
sempre primeiro (dependência usuario_logado). Toda regra que falha faz raise ErroLobby("codigo"),
e o tratador de erros.py responde no formato do contrato.

As rotas usam "def" comum, sem "async": o banco e a chamada ao Game são feitos com bibliotecas
que esperam a resposta parados, e o FastAPI roda cada requisição numa linha de execução separada.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, StrictInt, StrictStr

from app import banco, config, game
from app.erros import ErroLobby
from app.eventos import STREAM_BOT_SOLICITADO
from app.seguranca import usuario_logado

rotas = APIRouter(prefix="/api/lobby")

Usuario = Annotated[dict, Depends(usuario_logado)]


# Corpo esperado em cada rota que recebe JSON. Strict: "1" (texto) não vale como número, nem
# true como assento; sem o campo, ou com outro tipo, quem responde é o tratador de
# RequestValidationError (erros.py), com 422 dados_invalidos.
class DadosNovaSala(BaseModel):
    formato: StrictStr


class DadosAssento(BaseModel):
    assento: StrictInt


class DadosBot(BaseModel):
    assento: StrictInt
    nivel: StrictStr = "padrao"  # a tela sempre manda "padrao"


# ---------- Ajudantes ----------


def ocupado(assento: dict) -> bool:
    return assento["bot"] or assento["usuario_id"] is not None


def assento_do_usuario(sala: dict, usuario_id: str) -> dict | None:
    return next((a for a in sala["assentos"] if a["usuario_id"] == usuario_id), None)


def nome_de_bot(sala: dict) -> str:
    """"Bot 1", "Bot 2"...: o menor número ainda não usado na sala. Se o "Bot 1" sair, o próximo
    bot volta a ser "Bot 1"."""
    usados = {a["nome"] for a in sala["assentos"] if a["bot"]}
    numero = 1
    while f"Bot {numero}" in usados:
        numero += 1
    return f"Bot {numero}"


def para_resposta(sala: dict) -> dict:
    """A sala no formato do contrato (seção 4), sem os campos internos (nível e presença)."""
    return {
        "id": str(sala["id"]),
        "formato": sala["formato"],
        "dono_id": sala["dono_id"],
        "status": sala["status"],
        "partida_id": sala["partida_id"],
        "assentos": [
            {"assento": a["assento"], "usuario_id": a["usuario_id"], "nome": a["nome"], "bot": a["bot"]}
            for a in sala["assentos"]
        ],
    }


def sala_atualizada(conexao, sala_id: uuid.UUID) -> dict:
    """A sala relida do banco depois de uma alteração, já no formato do contrato: a tela se
    redesenha com ela (seção 1.3)."""
    return para_resposta(banco.buscar_sala(conexao, sala_id))


def id_da_sala(texto: str) -> uuid.UUID:
    """O {id} do caminho. Um id que nem é UUID é uma sala que nunca existiu: 404."""
    try:
        return uuid.UUID(texto)
    except ValueError:
        raise ErroLobby("sala_nao_encontrada")


def sala_para_acao(conexao, texto_id: str) -> dict:
    """Sala travada para uma ação. Uma sala encerrada ainda responde ao GET, mas para as ações
    (entrar, sair, bot, DELETE, iniciar) ela não existe mais: 404 (seção 6.4, P8)."""
    sala = banco.buscar_sala(conexao, id_da_sala(texto_id), travar=True)
    if sala is None or sala["status"] == "encerrada":
        raise ErroLobby("sala_nao_encontrada")
    return sala


def buscar_assento(sala: dict, numero: int) -> dict:
    if not 0 <= numero < len(sala["assentos"]):
        raise ErroLobby("dados_invalidos", "Assento inválido.")
    return sala["assentos"][numero]


def exigir_dono(sala: dict, usuario: dict) -> None:
    if sala["dono_id"] != usuario["id"]:
        raise ErroLobby("apenas_dono")


def exigir_aguardando(sala: dict) -> None:
    if sala["status"] != "aguardando":
        raise ErroLobby("partida_ja_iniciada")


def tirar_da_sala(conexao, sala_id: uuid.UUID, dono_id: str, assento: int, usuario_id: str) -> None:
    """Esvazia o assento de um jogador. Se ele era o dono, a sala é encerrada (seção 6.4). Os
    outros jogadores continuam nos assentos, mas uma sala encerrada não conta para a regra de uma
    sala por vez: eles ficam livres para entrar em outra."""
    banco.vagar(conexao, sala_id, assento)
    if usuario_id == dono_id:
        banco.encerrar_sala(conexao, sala_id)


def tirar_ausentes() -> None:
    """Regra de presença (seção 6.5): quem está sentado numa sala "aguardando" e passou 60
    segundos sem pedir GET /salas/{id} sai da sala, como no /sair; se for o dono, a sala é
    encerrada. Bots não entram na regra. Roda no começo de toda requisição, numa transação própria,
    antes das conferências da rota."""
    with banco.engine.begin() as conexao:
        for ausente in banco.ausentes(conexao):
            tirar_da_sala(conexao, ausente["sala_id"], ausente["dono_id"], ausente["assento"], ausente["usuario_id"])


# ---------- Rotas ----------


@rotas.get("/salas")
def listar_salas(usuario: Usuario):
    tirar_ausentes()
    return [para_resposta(sala) for sala in banco.salas_aguardando()]


@rotas.post("/salas", status_code=201)
def criar_sala(dados: DadosNovaSala, usuario: Usuario):
    tirar_ausentes()
    if dados.formato not in config.ASSENTOS_POR_FORMATO:
        raise ErroLobby("dados_invalidos", "Formato de sala inválido.")
    with banco.transacao(usuario["id"]) as conexao:
        if banco.sala_aberta_do_usuario(conexao, usuario["id"]):
            raise ErroLobby("ja_esta_em_outra_sala")
        sala_id = banco.inserir_sala(conexao, dados.formato, usuario)  # o criador no assento 0
        return sala_atualizada(conexao, sala_id)


@rotas.get("/salas/{sala_id}")
def obter_sala(sala_id: str, usuario: Usuario):
    """Responde a qualquer usuário logado, sentado na sala ou não: é o link de convite (6.3).
    Uma sala encerrada também responde 200, com o status novo."""
    tirar_ausentes()
    with banco.engine.begin() as conexao:
        sala = banco.buscar_sala(conexao, id_da_sala(sala_id))
        if sala is None:
            raise ErroLobby("sala_nao_encontrada")
        # Quem está sentado e pede a sala está presente: o prazo de 60 segundos recomeça.
        if sala["status"] == "aguardando" and assento_do_usuario(sala, usuario["id"]):
            banco.renovar_presenca(conexao, sala["id"], usuario["id"])
        return para_resposta(sala)


@rotas.post("/salas/{sala_id}/entrar")
def entrar(sala_id: str, dados: DadosAssento, usuario: Usuario):
    """Entra na sala ou, para quem já está nela, troca de assento (o antigo fica vago)."""
    tirar_ausentes()
    with banco.transacao(usuario["id"]) as conexao:
        sala = sala_para_acao(conexao, sala_id)
        exigir_aguardando(sala)
        destino = buscar_assento(sala, dados.assento)
        atual = assento_do_usuario(sala, usuario["id"])
        if destino is atual:
            return para_resposta(sala)  # já está nesse assento: nada muda
        # "Sala cheia" vem antes de "assento ocupado": numa sala cheia, quem está de fora sempre
        # recebe sala_cheia.
        if atual is None and all(ocupado(a) for a in sala["assentos"]):
            raise ErroLobby("sala_cheia")
        if ocupado(destino):
            raise ErroLobby("assento_ocupado")
        if atual is None and banco.sala_aberta_do_usuario(conexao, usuario["id"]):
            raise ErroLobby("ja_esta_em_outra_sala")
        if atual is not None:
            banco.vagar(conexao, sala["id"], atual["assento"])  # troca de assento; o dono continua dono
        banco.sentar(conexao, sala["id"], destino["assento"], usuario)
        return sala_atualizada(conexao, sala["id"])


@rotas.post("/salas/{sala_id}/sair")
def sair(sala_id: str, usuario: Usuario):
    """Sem corpo. Se quem sai é o dono, a sala é encerrada."""
    tirar_ausentes()
    with banco.transacao(usuario["id"]) as conexao:
        sala = sala_para_acao(conexao, sala_id)
        exigir_aguardando(sala)
        atual = assento_do_usuario(sala, usuario["id"])
        if atual is None:
            raise ErroLobby("nao_esta_na_sala")
        tirar_da_sala(conexao, sala["id"], sala["dono_id"], atual["assento"], usuario["id"])
        return sala_atualizada(conexao, sala["id"])


@rotas.post("/salas/{sala_id}/bot")
def colocar_bot(sala_id: str, dados: DadosBot, usuario: Usuario):
    tirar_ausentes()
    with banco.transacao(usuario["id"]) as conexao:
        sala = sala_para_acao(conexao, sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        alvo = buscar_assento(sala, dados.assento)
        if dados.nivel not in config.NIVEIS_DE_BOT:
            raise ErroLobby("dados_invalidos", "Nível de bot inválido.")
        if ocupado(alvo):
            raise ErroLobby("assento_ocupado")
        # O nível não aparece na sala, mas fica guardado: ele vai no evento bot.solicitado.
        banco.por_bot(conexao, sala["id"], alvo["assento"], nome_de_bot(sala), dados.nivel)
        return sala_atualizada(conexao, sala["id"])


@rotas.delete("/salas/{sala_id}/assentos/{assento}")
def liberar_assento(sala_id: str, assento: int, usuario: Usuario):
    """Só o dono: tira o bot ou o jogador do assento. O jogador removido descobre no próximo GET
    da sala (seção 1.4)."""
    tirar_ausentes()
    with banco.transacao(usuario["id"]) as conexao:
        sala = sala_para_acao(conexao, sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        alvo = buscar_assento(sala, assento)
        if not ocupado(alvo):
            raise ErroLobby("assento_vazio")
        if alvo["usuario_id"] == usuario["id"]:
            raise ErroLobby("dados_invalidos", "Para sair da sala, use o botão Sair da sala.")
        banco.vagar(conexao, sala["id"], alvo["assento"])
        return sala_atualizada(conexao, sala["id"])


@rotas.post("/salas/{sala_id}/iniciar")
def iniciar(sala_id: str, usuario: Usuario, request: Request):
    """Só o dono, com todos os assentos ocupados. Sem corpo. Pede a partida ao Game, grava o
    partida_id na sala e põe um bot.solicitado na fila para cada bot (seção 6.6)."""
    tirar_ausentes()
    with banco.transacao(usuario["id"]) as conexao:
        sala = sala_para_acao(conexao, sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        if not all(ocupado(a) for a in sala["assentos"]):
            raise ErroLobby("sala_incompleta")
        # A sala fica travada enquanto o Game responde (até GAME_TEMPO_LIMITE segundos): um
        # "entrar" ou um "sair" ao mesmo tempo espera, e não muda os assentos de uma partida que
        # já está sendo criada. Os GET não esperam.
        try:
            partida_id = game.criar_partida(str(sala["id"]), para_resposta(sala)["assentos"])
        except game.GameIndisponivel:
            # A sala continua "aguardando" (nada foi gravado): o dono pode tentar de novo.
            raise ErroLobby("game_indisponivel")
        banco.marcar_em_partida(conexao, sala["id"], partida_id)
        for assento in sala["assentos"]:
            if assento["bot"]:
                banco.guardar_evento(
                    conexao,
                    STREAM_BOT_SOLICITADO,
                    {"partida_id": partida_id, "assento": assento["assento"], "nome": assento["nome"], "nivel": assento["nivel"]},
                )
    # Depois do commit: o Entregador publica os bot.solicitado agora, sem esperar a próxima volta.
    request.app.state.entregador.acordar()
    return {"partida_id": partida_id}
