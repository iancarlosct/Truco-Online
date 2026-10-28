"""Eventos que o Game publica no broker de eventos: o Redis "eventos", com Redis Streams.

O broker é o meio de comunicação entre os serviços, separado do game-redis (que guarda os dados
do Game). Nesta fase só o Game se conecta a ele; Lobby, Ranking e Bots vão ler daqui.

Formato (proposta do docs/guia-backend-lobby.md, seção 7.4, adotada aqui):
- Um stream por evento, com o nome do evento: "partida.criada" e "partida.finalizada".
- Cada mensagem com um campo só, "dados", com o evento em JSON.
- Quem consome lê com um grupo próprio (XREADGROUP), confirma com XACK e ignora repetidos pelo
  partida_id: o mesmo evento pode chegar mais de uma vez.

partida.criada, publicado quando a partida é criada (POST /interno/partidas):
    {"partida_id", "sala_id", "formato", "criada_em"}

partida.finalizada, publicado quando um time chega a 12:
    {"partida_id", "sala_id", "formato",
     "times": {"A": [{"assento", "usuario_id", "nome", "bot"}], "B": [...]},
     "vencedor_time": "A" ou "B",
     "placar_final": {"A": 12, "B": 7},
     "encerrada_em"}
    Bots aparecem nos times com "usuario_id": null e "bot": true.

As datas são texto no formato ISO 8601, em UTC: "2026-10-28T14:03:12+00:00".

Entrega: o evento não vai direto ao broker. Ele entra primeiro na fila "eventos:pendentes" do
game-redis, junto com o estado da partida (banco.salvar_partida), e o Entregador passa a fila
para o broker. Com o broker fora do ar, a partida continua, e os eventos esperam na fila até
ele voltar. Se o Game cair entre o envio de um evento e a retirada dele da fila, o evento sai
de novo quando o Game voltar: por isso quem consome precisa ignorar repetidos.
"""

import asyncio
import json
import logging

import redis.asyncio as redis

from app import config
from app.banco import FILA_DE_EVENTOS

log = logging.getLogger("uvicorn.error")


def conectar() -> redis.Redis:
    """Cliente do broker de eventos."""
    return redis.Redis(
        host=config.EVENTOS_HOST,
        port=config.EVENTOS_PORTA,
        password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


# ---------- Os eventos ----------


def partida_criada(estado: dict) -> dict:
    return {
        "nome": "partida.criada",
        "dados": {
            "partida_id": estado["partida_id"],
            "sala_id": estado["sala_id"],
            "formato": estado["formato"],
            "criada_em": estado["criada_em"],
        },
    }


def partida_finalizada(estado: dict) -> dict:
    times = {"A": [], "B": []}
    for jogador in estado["jogadores"]:
        times[jogador["time"]].append(
            {
                "assento": jogador["assento"],
                "usuario_id": jogador["usuario_id"],
                "nome": jogador["nome"],
                "bot": jogador["bot"],
            }
        )
    return {
        "nome": "partida.finalizada",
        "dados": {
            "partida_id": estado["partida_id"],
            "sala_id": estado["sala_id"],
            "formato": estado["formato"],
            "times": times,
            "vencedor_time": estado["vencedor_time"],
            "placar_final": dict(estado["placar"]),
            "encerrada_em": estado["encerrada_em"],
        },
    }


# ---------- Entrega ----------


class Entregador:
    """Tarefa que roda ao lado do servidor e passa os eventos da fila do game-redis para o
    broker, na ordem em que entraram. Acorda na hora quando um evento novo entra (acordar) e,
    de qualquer jeito, a cada INTERVALO segundos, para tentar de novo depois de uma falha."""

    INTERVALO = 5

    def __init__(self, banco: redis.Redis, broker: redis.Redis):
        self.banco = banco
        self.broker = broker
        self._acordar = asyncio.Event()

    def acordar(self) -> None:
        self._acordar.set()

    async def entregar_pendentes(self) -> None:
        """Publica cada evento da fila e só então o tira dela."""
        while (texto := await self.banco.lindex(FILA_DE_EVENTOS, 0)) is not None:
            evento = json.loads(texto)
            await self.broker.xadd(evento["nome"], {"dados": json.dumps(evento["dados"], ensure_ascii=False)})
            await self.banco.lpop(FILA_DE_EVENTOS)

    async def rodar(self) -> None:
        while True:
            self._acordar.clear()
            try:
                await self.entregar_pendentes()
            except Exception as erro:  # a tarefa não pode morrer: sem ela, nenhum evento sai
                log.warning("Eventos não entregues ao broker (%s). Nova tentativa em %s s.", erro, self.INTERVALO)
            try:
                await asyncio.wait_for(self._acordar.wait(), timeout=self.INTERVALO)
            except TimeoutError:
                pass
