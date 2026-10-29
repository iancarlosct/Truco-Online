"""Rotas do Game: a criação da partida, chamada pelo Lobby, e o WebSocket da mesa.

O gateway repassa ao Game só o /ws/. A rota /interno/partidas fica fora dele: só os containers
da rede-servicos a alcançam (o Lobby, ao iniciar uma sala).
"""

from fastapi import APIRouter, Request, WebSocket
from pydantic import BaseModel

import engine
from app import seguranca
from app.erros import erro
from app.partidas import FORA_DA_PARTIDA, PARTIDA_INEXISTENTE, TOKEN_INVALIDO

rotas = APIRouter()


# Corpo do POST /interno/partidas (docs/guia-backend-lobby.md, seção 6.6). O FastAPI confere os
# tipos; as regras da mesa (2 ou 4 assentos, numeração, bots) quem confere é o motor.
class Assento(BaseModel):
    assento: int
    usuario_id: str | None = None
    nome: str
    bot: bool = False


class DadosPartida(BaseModel):
    sala_id: str | None = None
    assentos: list[Assento]


@rotas.post("/interno/partidas", status_code=201)
async def criar_partida(dados: DadosPartida, request: Request):
    """Cria a partida com a primeira mão já distribuída e responde {"partida_id"}. Publica o
    evento partida.criada."""
    try:
        partida_id = await request.app.state.partidas.criar(
            dados.sala_id, [assento.model_dump() for assento in dados.assentos]
        )
    except engine.AssentosInvalidos as problema:
        return erro(422, "dados_invalidos", str(problema))
    return {"partida_id": partida_id}


@rotas.websocket("/ws/partidas/{partida_id}")
async def mesa(websocket: WebSocket, partida_id: str, token: str = ""):
    """Conexão de um jogador (ou bot) com a partida: /ws/partidas/{partida_id}?token=<jwt>
    (guia da mesa, seção 3.3)."""
    partidas = websocket.app.state.partidas

    # Aceita antes de conferir qualquer coisa. Uma recusa sem accept() chega ao navegador como
    # queda (código 1006), e a tela ficaria tentando conectar de novo para sempre (seção 3.4).
    await websocket.accept()

    sub = seguranca.dono_do_token(token)
    if sub is None:
        await websocket.close(code=TOKEN_INVALIDO, reason="token inválido")
        return
    estado = await partidas.buscar(partida_id)
    if estado is None:
        await websocket.close(code=PARTIDA_INEXISTENTE, reason="partida inexistente")
        return
    assento = seguranca.assento_na_partida(estado, sub)
    if assento is None:
        await websocket.close(code=FORA_DA_PARTIDA, reason="não pertence à partida")
        return

    # Guarda a conexão e envia o estado atual: é com ele que a tela se desenha.
    if not await partidas.entrar(partida_id, assento, websocket):
        return
    try:
        while True:
            mensagem = await websocket.receive()
            if mensagem["type"] == "websocket.disconnect":
                break  # aba fechada, F5, rede caiu ou conexão substituída
            # Mensagem binária chega sem "text" e é tratada como malformada.
            await partidas.receber(partida_id, assento, websocket, mensagem.get("text"))
    finally:
        partidas.sair(partida_id, assento, websocket)
