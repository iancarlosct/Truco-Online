"""Preparação dos testes. Eles rodam dentro do container, com o Postgres e o broker de verdade:

    docker compose run --rm ranking pytest

Para não mexer no ranking e nos eventos de quem está usando o sistema:
- o banco é um separado no mesmo ranking-db: o de sempre com "_teste" no fim (ranking_teste, com o
  .env de exemplo), criado na primeira vez e esvaziado antes de cada teste;
- o broker é o banco lógico 3 do Redis "eventos" (o serviço usa o 0; os do Game e do Lobby, o 1
  e o 2).

Os resultados entram como no sistema de verdade: um partida.finalizada publicado no broker, no
formato do Game, lido pelo Consumidor, que roda em paralelo ao teste.
"""

import os

# O banco de teste tem que ser escolhido ANTES de importar o app: o app.config lê as variáveis
# de ambiente uma vez só, quando é importado.
BANCO_PRINCIPAL = os.environ["BANCO_NOME"]
BANCO_TESTE = f"{BANCO_PRINCIPAL}_teste"
os.environ["BANCO_NOME"] = BANCO_TESTE
os.environ["EVENTOS_NUMERO"] = "3"

import itertools  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import banco, config  # noqa: E402
from app.main import app  # noqa: E402

# O consumidor espera bem menos nos testes: para e recomeça rápido.
config.ESPERA_POR_EVENTOS = 0.1
config.INTERVALO_DE_NOVA_TENTATIVA = 0.2

STREAM = "partida.finalizada"


def criar_banco_de_teste() -> None:
    """Cria o banco de teste, se ainda não existir (CREATE DATABASE roda fora de transação)."""
    url = banco.engine.url.set(database=BANCO_PRINCIPAL)
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conexao:
            existe = conexao.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :nome"), {"nome": BANCO_TESTE}
            ).scalar()
            if not existe:
                conexao.execute(text(f'CREATE DATABASE "{BANCO_TESTE}"'))
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def cliente():
    """Cliente HTTP que chama o app direto, sem rede. O "with" roda o ciclo de vida do app, que
    cria as tabelas no banco de teste e começa o consumidor."""
    criar_banco_de_teste()
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture(scope="session")
def broker():
    cliente = redis.Redis(
        host=config.EVENTOS_HOST, port=config.EVENTOS_PORTA, password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO, decode_responses=True,
    )
    yield cliente
    cliente.close()


@pytest.fixture
def consumidor(cliente):
    return cliente.app.state.consumidor


@pytest.fixture(autouse=True)
def ambiente_limpo(cliente, broker):
    """Cada teste começa sem partidas e com o broker vazio (sem stream nem grupo). O consumidor
    para durante a limpeza e recomeça depois, como um Ranking que acabou de subir."""
    consumidor = cliente.app.state.consumidor
    consumidor.parar()
    with banco.engine.begin() as conexao:
        conexao.execute(text("TRUNCATE participantes, partidas, jogadores"))
    broker.flushdb()
    consumidor.iniciar()


# ---------- Ajudantes usados nos testes ----------


def token(sub, nome="Jogador", validade=timedelta(hours=1), segredo=None):
    conteudo = {"sub": sub, "nome": nome, "exp": datetime.now(timezone.utc) + validade}
    return jwt.encode(conteudo, segredo or config.JWT_SEGREDO, algorithm="HS256")


class Pessoa:
    """Um usuário do Auth: id (UUID), nome e o cabeçalho com o token dele."""

    def __init__(self, nome):
        self.id = str(uuid.uuid4())
        self.nome = nome
        self.headers = {"Authorization": f"Bearer {token(self.id, nome)}"}

    def jogador(self, assento):
        return {"assento": assento, "usuario_id": self.id, "nome": self.nome, "bot": False}


def bot(assento, nome="Bot 1"):
    return {"assento": assento, "usuario_id": None, "nome": nome, "bot": True}


_relogio = itertools.count()


def partida(time_a, time_b, vencedor="A", partida_id=None, encerrada_em=None, placar=None):
    """Um partida.finalizada no formato do Game (guia da mesa, 10.4). Cada time é uma lista de
    jogadores, de Pessoa.jogador() ou bot(). Sem data, cada partida termina um minuto depois da
    anterior."""
    if encerrada_em is None:
        encerrada_em = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc) + timedelta(minutes=next(_relogio))
    return {
        "partida_id": partida_id or str(uuid.uuid4()),
        "sala_id": str(uuid.uuid4()),
        "formato": "1x1" if len(time_a) == 1 else "2x2",
        "times": {"A": time_a, "B": time_b},
        "vencedor_time": vencedor,
        "placar_final": placar or ({"A": 12, "B": 7} if vencedor == "A" else {"A": 7, "B": 12}),
        "encerrada_em": encerrada_em.isoformat(),
    }


def vitoria(vencedor, perdedor, **opcoes):
    """Partida 1x1 em que o primeiro vence."""
    return partida([vencedor.jogador(0)], [perdedor.jogador(1)], "A", **opcoes)


def publicar(broker, *eventos):
    for evento in eventos:
        broker.xadd(STREAM, {"dados": evento if isinstance(evento, str) else json.dumps(evento)})


def esperar(condicao, limite=3.0):
    fim = time.monotonic() + limite
    while not condicao():
        if time.monotonic() > fim:
            return False
        time.sleep(0.02)
    return True


def tudo_lido(broker):
    """O grupo "ranking" leu e confirmou (XACK) tudo o que está no stream."""
    if not broker.exists(STREAM):
        return False
    grupos = {g["name"]: g for g in broker.xinfo_groups(STREAM)}
    return "ranking" in grupos and grupos["ranking"]["pending"] == 0 and grupos["ranking"]["lag"] == 0


def publicar_e_esperar(broker, *eventos):
    publicar(broker, *eventos)
    assert esperar(lambda: tudo_lido(broker)), "o consumidor não leu os eventos"


def partidas_registradas():
    with banco.engine.connect() as conexao:
        return conexao.execute(text("SELECT count(*) FROM partidas")).scalar()
