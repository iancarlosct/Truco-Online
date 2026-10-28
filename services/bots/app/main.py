"""Ponto de entrada do serviço de Bots. O Uvicorn sobe a variável "app" deste arquivo
(app.main:app, no Dockerfile), num processo só (explicação em eventos.py).

O serviço não atende ninguém: o trabalho é do Gerenciador (eventos.py), que lê os pedidos de bot
numa tarefa ao lado do servidor e põe cada bot para jogar. A única rota é a /saude, usada pelo
healthcheck do Docker Compose. Nenhuma porta é aberta no computador e o gateway não repassa nada
para cá.
"""

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import eventos


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Ao subir: conecta ao broker e começa a ler os pedidos. Os bots que estavam jogando antes
    # de um reinício voltam primeiro (os pedidos pendentes, eventos.py).
    broker = eventos.conectar()
    gerenciador = eventos.Gerenciador(broker)
    tarefa = asyncio.create_task(gerenciador.rodar())
    app.state.broker = broker
    app.state.gerenciador = gerenciador
    yield
    # Ao parar: para a leitura e os bots, sem confirmar os pedidos deles (voltam no próximo
    # início), e fecha a conexão com o broker.
    tarefa.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarefa
    await gerenciador.encerrar()
    await broker.aclose()


app = FastAPI(
    title="Truco Online — Bots",
    lifespan=ciclo_de_vida,
    # Sem página de testes: o serviço não tem rotas para testar.
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
)


# Healthcheck do container (docker-compose.yml), chamado de dentro do próprio container. Pronto
# quando alcança o broker, de onde vêm os pedidos e onde ficam os bots ativos. O Game não entra
# na conta: sem ele os bots esperam e reconectam sozinhos.
@app.get("/saude", include_in_schema=False)
async def saude():
    try:
        await app.state.broker.ping()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"erro": "broker_indisponivel", "mensagem": "O broker de eventos está indisponível."},
        )
    return {"status": "ok", "bots_ativos": len(app.state.gerenciador.ativos)}
