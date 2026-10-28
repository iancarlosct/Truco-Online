"""Ponto de entrada do serviço Auth. O Uvicorn sobe a variável "app" deste arquivo
(app.main:app, no Dockerfile)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import banco
from app.erros import erro, registrar_tratadores
from app.rotas import rotas


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Ao subir: cria a tabela de usuários, se ainda não existir (explicação em banco.py).
    banco.criar_tabela()
    yield
    # Ao parar: fecha as conexões com o banco.
    banco.engine.dispose()


app = FastAPI(
    title="Truco Online — Auth",
    lifespan=ciclo_de_vida,
    # A página de testes do FastAPI fica dentro de /api/auth/ para ser aberta pelo gateway:
    # http://localhost/api/auth/docs. O serviço não tem porta aberta no computador.
    docs_url="/api/auth/docs",
    openapi_url="/api/auth/openapi.json",
    redoc_url=None,
)
registrar_tratadores(app)
app.include_router(rotas)


# Healthcheck do container (docker-compose.yml). Fica fora de /api/auth/, então o gateway não a
# repassa: só é chamada de dentro da rede do Docker.
@app.get("/saude", include_in_schema=False)
def saude():
    if not banco.banco_disponivel():
        return erro(503, "banco_indisponivel", "O banco de dados está indisponível.")
    return {"status": "ok"}
