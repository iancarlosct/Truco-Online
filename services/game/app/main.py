"""Ponto de entrada do serviço Game. O Uvicorn sobe a variável "app" deste arquivo
(app.main:app, no Dockerfile), num processo só (limitação explicada em partidas.py)."""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import banco, eventos
from app.erros import erro, registrar_tratadores
from app.partidas import Partidas
from app.rotas import rotas


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Ao subir: conecta aos dois Redis (o banco do Game e o broker de eventos) e começa a
    # entregar os eventos pendentes, inclusive os que ficaram na fila antes de um reinício.
    banco_redis = banco.conectar()
    broker = eventos.conectar()
    entregador = eventos.Entregador(banco_redis, broker)
    tarefa_de_entrega = asyncio.create_task(entregador.rodar())
    app.state.banco = banco_redis
    app.state.partidas = Partidas(banco_redis, entregador)
    yield
    # Ao parar: para as tarefas e fecha as conexões com os dois Redis.
    tarefa_de_entrega.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarefa_de_entrega
    await app.state.partidas.encerrar()
    await banco_redis.aclose()
    await broker.aclose()


app = FastAPI(
    title="Truco Online — Game",
    lifespan=ciclo_de_vida,
    # A página de testes do FastAPI fica dentro de /interno, como a rota de criar partida: o
    # gateway não a repassa, e só os containers da rede-servicos a abrem.
    docs_url="/interno/docs",
    openapi_url="/interno/openapi.json",
    redoc_url=None,
)
registrar_tratadores(app)
app.include_router(rotas)


# Healthcheck do container (docker-compose.yml). O gateway não repassa esta rota: ela só é
# chamada de dentro da rede do Docker. O broker de eventos não entra na conta: sem ele as
# partidas continuam, e os eventos esperam na fila (eventos.py).
@app.get("/saude", include_in_schema=False)
async def saude():
    if not await banco.banco_disponivel(app.state.banco):
        return erro(503, "banco_indisponivel", "O banco de dados está indisponível.")
    return {"status": "ok"}
