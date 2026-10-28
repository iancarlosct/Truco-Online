"""Preparação dos testes da camada de serviço. Eles rodam dentro do container, com os dois Redis
de verdade (o game-redis e o broker de eventos):

    docker compose run --rm game pytest

Para não apagar as partidas e os eventos de quem está usando o sistema, os testes usam o banco
lógico 1 de cada Redis (o serviço usa o 0), esvaziado antes de cada teste.
"""

import os

# Os bancos de teste têm que ser escolhidos ANTES de importar o app: o app.config lê as
# variáveis de ambiente uma vez só, quando é importado.
os.environ["BANCO_NUMERO"] = "1"
os.environ["EVENTOS_NUMERO"] = "1"

import json  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.banco import FILA_DE_EVENTOS  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def cliente():
    """Cliente que chama o app direto, sem rede: HTTP e WebSocket. O "with" roda o ciclo de vida
    do app (conexões com os Redis e o Entregador de eventos)."""
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture(scope="session")
def banco():
    """O game-redis, para os testes lerem e prepararem o estado das partidas."""
    cliente = redis.Redis(
        host=config.BANCO_HOST, port=config.BANCO_PORTA, password=config.BANCO_SENHA,
        db=config.BANCO_NUMERO, decode_responses=True,
    )
    yield cliente
    cliente.close()


@pytest.fixture(scope="session")
def broker():
    """O broker de eventos, para os testes lerem os streams."""
    cliente = redis.Redis(
        host=config.EVENTOS_HOST, port=config.EVENTOS_PORTA, password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO, decode_responses=True,
    )
    yield cliente
    cliente.close()


@pytest.fixture(autouse=True)
def redis_vazio(cliente, banco, broker, monkeypatch):
    """Cada teste começa sem partidas nem eventos, e com a pausa entre as mãos bem curta.

    Antes de limpar, espera o Entregador terminar os eventos do teste anterior: ele roda em
    paralelo, e um evento entregue depois da limpeza apareceria no stream deste teste."""
    limite = time.monotonic() + 3
    while banco.llen(FILA_DE_EVENTOS) and time.monotonic() < limite:
        time.sleep(0.01)
    banco.flushdb()
    broker.flushdb()
    monkeypatch.setattr(config, "PAUSA_ENTRE_MAOS", 0.05)


# ---------- Ajudantes usados nos testes ----------

ANA = str(uuid.uuid4())
BETO = str(uuid.uuid4())
CAIO = str(uuid.uuid4())

ASSENTOS_1X1 = [
    {"assento": 0, "usuario_id": ANA, "nome": "Ana", "bot": False},
    {"assento": 1, "usuario_id": BETO, "nome": "Beto", "bot": False},
]


def token(sub, nome="Jogador", validade=timedelta(hours=1), segredo=None):
    conteudo = {"sub": sub, "nome": nome, "exp": datetime.now(timezone.utc) + validade}
    return jwt.encode(conteudo, segredo or config.JWT_SEGREDO, algorithm="HS256")


def criar_partida(cliente, assentos=ASSENTOS_1X1, sala_id="sala-1"):
    resposta = cliente.post("/interno/partidas", json={"sala_id": sala_id, "assentos": assentos})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["partida_id"]


def conectar(cliente, partida_id, sub=None, token_pronto=None):
    """Abre o WebSocket da mesa (use com "with"). Sem token_pronto, gera um token para o sub."""
    return cliente.websocket_connect(f"/ws/partidas/{partida_id}?token={token_pronto or token(sub)}")


def ler_partida(banco, partida_id):
    return json.loads(banco.get(f"partida:{partida_id}"))


def preparar_partida(banco, partida_id, maos=None, vira=None, placar=None):
    """Troca as cartas sorteadas (e o placar) por valores escolhidos, direto no Redis."""
    estado = ler_partida(banco, partida_id)
    for jogador, cartas in zip(estado["jogadores"], maos or []):
        jogador["mao"] = list(cartas)
    if vira:
        estado["mao_atual"]["vira"] = vira
    if placar:
        estado["placar"] = dict(placar)
    banco.set(f"partida:{partida_id}", json.dumps(estado))
    return estado


def eventos_do_stream(broker, nome, quantidade=1, espera=3.0):
    """Os eventos publicados no stream, já lidos do JSON. Espera um pouco: quem publica é o
    Entregador, que roda em paralelo ao teste."""
    limite = time.monotonic() + espera
    while True:
        mensagens = broker.xrange(nome)
        if len(mensagens) >= quantidade or time.monotonic() > limite:
            return [json.loads(campos["dados"]) for _id, campos in mensagens]
        time.sleep(0.02)
