"""Preparação dos testes do serviço. Rodam dentro do container, com os serviços de verdade no ar,
no ambiente de testes isolado (o projeto "truco-testes" do Docker Compose, com bancos próprios):

    ./testes.sh bots

ou, passo a passo, a partir da raiz do repositório:

    docker compose -p truco-testes up -d --build --wait auth game lobby ranking bots
    docker compose -p truco-testes run --rm --no-deps bots pytest
    docker compose -p truco-testes down -v

Eles criam salas, partidas e linhas no ranking de verdade, por isso não rodam no projeto
"truco-online", o do sistema em uso: lá, o fixture sistema_no_ar os faz falhar com um aviso.

Há dois tipos de teste:

- test_partidas.py: partidas criadas pelo Lobby, com os bots jogados pelo serviço bots que está
  no ar. O teste faz o papel da pessoa: assina um token de usuário, cria a sala, põe os bots,
  inicia e joga pela mesa do Game até o fim. O bot.solicitado vai para o broker de verdade
  (banco lógico 0), e quem joga pelos bots é o container bots. Por isso o sistema precisa subir
  com --build antes: é o código que está rodando nele que estes testes conferem.
- test_retomada.py: o Gerenciador (app/eventos.py) roda dentro do próprio teste, sem atraso,
  lendo o banco lógico 4 do broker (o serviço usa o 0; os testes do Game, do Lobby e do Ranking,
  o 1, o 2 e o 3). As partidas são criadas direto no Game (POST /interno/partidas), e o teste
  publica o bot.solicitado como o Lobby faria. Assim dá para derrubar o serviço no meio de uma
  partida e repetir o pedido, sem que o serviço no ar veja essas partidas.

Todos usam a mesma pessoa de teste, "Teste dos Bots", com um id fixo. As partidas que terminam
contam para ela no ranking do ambiente de testes, que é apagado no fim do testes.sh.
"""

import os

# O banco lógico de teste tem que ser escolhido ANTES de importar o app: o app.config lê as
# variáveis de ambiente uma vez só, quando é importado.
os.environ["EVENTOS_NUMERO"] = "4"

import json  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402
import redis  # noqa: E402

from app import config, eventos  # noqa: E402

# Os bots do teste não esperam antes de agir, e o Gerenciador volta rápido de cada leitura.
config.ATRASO_MINIMO = config.ATRASO_MAXIMO = 0.0
config.ESPERA_POR_EVENTOS = 0.1
config.INTERVALO_DE_NOVA_TENTATIVA = 0.2

# Endereços internos dos serviços, na rede-servicos (os testes não passam pelo gateway).
LOBBY_URL = os.environ.get("LOBBY_URL", "http://lobby:8000")
GAME_URL = os.environ.get("GAME_URL", "http://game:8000")
RANKING_URL = os.environ.get("RANKING_URL", "http://ranking:8000")
BOTS_URL = os.environ.get("BOTS_URL", "http://bots:8000")

PESSOA_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "truco-online/testes-dos-bots"))
PESSOA_NOME = "Teste dos Bots"


# ---------- HTTP ----------


def pedir(metodo: str, url: str, token: str | None = None, corpo: dict | None = None) -> tuple[int, dict]:
    """Uma requisição HTTP com JSON. Devolve o status e o corpo da resposta."""
    cabecalhos = {"Content-Type": "application/json"}
    if token:
        cabecalhos["Authorization"] = f"Bearer {token}"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            return resposta.status, json.loads(resposta.read() or b"null")
    except urllib.error.HTTPError as erro:
        return erro.code, json.loads(erro.read() or b"null")


def esperar(condicao, limite: float, motivo: str = "a condição"):
    """Espera condicao() devolver algo verdadeiro (e devolve esse valor); falha depois de
    "limite" segundos."""
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        if valor := condicao():
            return valor
        time.sleep(0.2)
    raise AssertionError(f"{motivo} não aconteceu em {limite} s")


# Projeto do Docker Compose em que o teste está rodando (docker-compose.yml, serviço bots).
PROJETO_COMPOSE = os.environ.get("PROJETO_COMPOSE", "")
PROJETO_DO_SISTEMA = "truco-online"


@pytest.fixture(scope="session")
def sistema_no_ar():
    """Os testes precisam do Game, do Lobby, do Ranking e do serviço bots no ar, no ambiente de
    testes: no projeto do sistema em uso, eles gravariam salas, partidas e ranking de verdade."""
    if PROJETO_COMPOSE == PROJETO_DO_SISTEMA:
        pytest.fail(
            "Os testes de serviço dos Bots gravam salas, partidas e ranking nos bancos. Rode-os no "
            "ambiente de testes isolado: ./testes.sh bots (README, seção Testes)."
        )
    for nome, url in [("game", GAME_URL), ("lobby", LOBBY_URL), ("ranking", RANKING_URL), ("bots", BOTS_URL)]:
        try:
            status, _ = pedir("GET", f"{url}/saude")
        except OSError:
            status = None
        if status != 200:
            pytest.fail(f"O serviço {nome} não está no ar. Rode pelo ambiente de testes: ./testes.sh bots")


# ---------- Broker ----------


@pytest.fixture
def broker():
    """O broker de teste (banco lógico 4), vazio no começo de cada teste."""
    cliente = redis.Redis(
        host=config.EVENTOS_HOST, port=config.EVENTOS_PORTA, password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO, decode_responses=True,
    )
    cliente.flushdb()
    yield cliente
    cliente.close()


@pytest.fixture(scope="session")
def broker_do_sistema():
    """O broker que o Lobby e o serviço bots usam (banco lógico 0). Os testes só leem dele."""
    cliente = redis.Redis(
        host=config.EVENTOS_HOST, port=config.EVENTOS_PORTA, password=config.EVENTOS_SENHA,
        db=0, decode_responses=True,
    )
    yield cliente
    cliente.close()


def publicar_pedido(broker, partida_id: str, assento: int, nome: str) -> str:
    """Publica um bot.solicitado como o Lobby publica."""
    dados = {"partida_id": partida_id, "assento": assento, "nome": nome, "nivel": "padrao"}
    return broker.xadd(eventos.STREAM, {"dados": json.dumps(dados)})


def pendentes(broker, partida_id: str | None = None) -> list[str]:
    """Os pedidos de bot que o grupo "bots" recebeu e ainda não confirmou: os dos bots que estão
    jogando. Com partida_id, só os daquela partida."""
    try:
        lista = broker.xpending_range(eventos.STREAM, eventos.GRUPO, min="-", max="+", count=1000)
    except redis.ResponseError:  # o grupo ainda não existe
        return []
    ids = [item["message_id"] for item in lista]
    if partida_id is None:
        return ids
    return [i for i in ids if any(json.loads(c["dados"]).get("partida_id") == partida_id for _i, c in broker.xrange(eventos.STREAM, i, i))]


def criar_partida_no_game(assentos: list[dict]) -> str:
    """Cria a partida direto no Game, como o Lobby faz ao iniciar uma sala (sem sala)."""
    status, corpo = pedir("POST", f"{GAME_URL}/interno/partidas", corpo={"sala_id": None, "assentos": assentos})
    assert status == 201, corpo
    return corpo["partida_id"]
