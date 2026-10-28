"""Ponto de entrada do serviço Ranking. O Uvicorn sobe a variável "app" deste arquivo
(app.main:app, no Dockerfile), num processo só (explicação em eventos.py)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import banco, eventos
from app.erros import erro, registrar_tratadores
from app.rotas import rotas


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    # Ao subir: cria as tabelas, se ainda não existirem (explicação em banco.py), e começa a ler o
    # partida.finalizada, inclusive os eventos publicados antes de o Ranking subir.
    banco.criar_tabelas()
    broker = eventos.conectar()
    app.state.consumidor = eventos.Consumidor(
        broker, eventos.STREAM_PARTIDA_FINALIZADA, eventos.GRUPO, eventos.CONSUMIDOR, eventos.tratar_partida_finalizada
    )
    app.state.consumidor.iniciar()
    yield
    # Ao parar: para o consumidor e fecha as conexões com o broker e o banco.
    app.state.consumidor.parar()
    broker.close()
    banco.engine.dispose()


app = FastAPI(
    title="Truco Online — Ranking",
    lifespan=ciclo_de_vida,
    # A página de testes do FastAPI fica dentro de /api/ranking/ para ser aberta pelo gateway:
    # http://localhost/api/ranking/docs. O serviço não tem porta aberta no computador.
    docs_url="/api/ranking/docs",
    openapi_url="/api/ranking/openapi.json",
    redoc_url=None,
)
registrar_tratadores(app)
app.include_router(rotas)


# Healthcheck do container (docker-compose.yml). Fica fora de /api/ranking, então o gateway não a
# repassa: só é chamada de dentro da rede do Docker. O broker não entra na conta: sem ele o ranking
# continua respondendo, só não recebe partidas novas até ele voltar.
@app.get("/saude", include_in_schema=False)
def saude():
    if not banco.banco_disponivel():
        return erro(503, "banco_indisponivel", "O banco de dados está indisponível.")
    return {"status": "ok"}
