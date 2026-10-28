"""Acesso ao banco do Game: o Redis "game-redis". Só este serviço conecta nele.

Chaves:
    partida:<partida_id>   estado completo da partida, em JSON (formato em engine/partida.py).
                           Vence depois de VALIDADE_DA_PARTIDA sem mudanças.
    eventos:pendentes      fila (lista) dos eventos que ainda não foram entregues ao broker de
                           eventos. Quem a esvazia é o Entregador (eventos.py).

O estado e os eventos de uma mesma mudança são gravados juntos, numa transação do Redis
(MULTI/EXEC): ou os dois ficam gravados, ou nenhum. Assim um partida.finalizada nunca se perde,
nem sai sem a partida estar mesmo encerrada.
"""

import json

import redis.asyncio as redis
from redis.exceptions import RedisError

from app import config

FILA_DE_EVENTOS = "eventos:pendentes"


def conectar() -> redis.Redis:
    """Cliente do game-redis. Ele guarda um conjunto de conexões e as reaproveita."""
    return redis.Redis(
        host=config.BANCO_HOST,
        port=config.BANCO_PORTA,
        password=config.BANCO_SENHA,
        db=config.BANCO_NUMERO,
        decode_responses=True,  # devolve texto (str) em vez de bytes
        socket_connect_timeout=5,  # segundos; sem isso, um Redis fora do ar trava a conexão
        socket_timeout=5,
    )


def chave_da_partida(partida_id: str) -> str:
    return f"partida:{partida_id}"


async def buscar_partida(banco: redis.Redis, partida_id: str) -> dict | None:
    texto = await banco.get(chave_da_partida(partida_id))
    return json.loads(texto) if texto else None


async def salvar_partida(banco: redis.Redis, estado: dict, eventos: list[dict] | None = None) -> None:
    """Grava o estado da partida e põe os eventos na fila de entrega, na mesma transação."""
    async with banco.pipeline(transaction=True) as transacao:
        transacao.set(
            chave_da_partida(estado["partida_id"]),
            json.dumps(estado, ensure_ascii=False),
            ex=config.VALIDADE_DA_PARTIDA,
        )
        for evento in eventos or []:
            transacao.rpush(FILA_DE_EVENTOS, json.dumps(evento, ensure_ascii=False))
        await transacao.execute()


async def banco_disponivel(banco: redis.Redis) -> bool:
    """Confere se o game-redis responde. Usada pela rota /saude."""
    try:
        return await banco.ping()
    except (RedisError, OSError):
        return False
