"""Preparação dos testes. Eles rodam dentro do container, com o Postgres e o broker de verdade:

    docker compose run --rm lobby pytest

Para não mexer nas salas e nos eventos de quem está usando o sistema:
- o banco é um separado no mesmo lobby-db: o de sempre com "_teste" no fim (lobby_teste, com o
  .env de exemplo), criado na primeira vez e esvaziado antes de cada teste;
- o broker é o banco lógico 2 do Redis "eventos" (o serviço usa o 0; os testes do Game, o 1);
- o Game é um servidor falso, dentro do próprio teste (GameFalso), que responde ao
  POST /interno/partidas. Assim os testes não criam partidas no Game de verdade.
"""

import os

# O banco de teste tem que ser escolhido ANTES de importar o app: o app.config lê as variáveis
# de ambiente uma vez só, quando é importado.
BANCO_PRINCIPAL = os.environ["BANCO_NOME"]
BANCO_TESTE = f"{BANCO_PRINCIPAL}_teste"
os.environ["BANCO_NOME"] = BANCO_TESTE
os.environ["EVENTOS_NUMERO"] = "2"

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
import redis  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import banco, config  # noqa: E402
from app.main import app  # noqa: E402

# As linhas de execução dos eventos esperam bem menos nos testes: param e recomeçam rápido.
config.ESPERA_POR_EVENTOS = 0.1
config.INTERVALO_DE_NOVA_TENTATIVA = 0.2

URL = "/api/lobby"


def criar_banco_de_teste() -> None:
    """Cria o banco de teste, se ainda não existir. CREATE DATABASE não roda dentro de uma
    transação, por isso a conexão é feita em modo AUTOCOMMIT, ligada ao banco principal."""
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


class GameFalso:
    """Faz o papel do Game: responde ao POST /interno/partidas e guarda cada pedido recebido.
    Os testes mudam "status", "corpo" e "atraso" para simular as falhas do Game."""

    def __init__(self):
        jogo = self

        class Tratador(BaseHTTPRequestHandler):
            def do_POST(self):
                tamanho = int(self.headers.get("Content-Length", 0))
                jogo.pedidos.append({"caminho": self.path, "corpo": json.loads(self.rfile.read(tamanho))})
                time.sleep(jogo.atraso)
                corpo = jogo.corpo if jogo.corpo is not None else {"partida_id": str(uuid.uuid4())}
                dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode()
                self.send_response(jogo.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *args):
                pass  # sem uma linha no terminal a cada pedido

        class Servidor(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass  # o Lobby desistiu antes da resposta (teste de tempo esgotado)

        self.http = Servidor(("127.0.0.1", 0), Tratador)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.reiniciar()

    def reiniciar(self):
        self.pedidos = []
        self.status = 201
        self.corpo = None  # None: um partida_id novo a cada pedido
        self.atraso = 0.0


@pytest.fixture(scope="session")
def game_falso():
    jogo = GameFalso()
    config.GAME_URL = jogo.url
    yield jogo
    jogo.http.shutdown()


@pytest.fixture(scope="session")
def cliente(game_falso):
    """Cliente HTTP que chama o app direto, sem rede. O "with" roda o ciclo de vida do app, que
    cria as tabelas no banco de teste e começa as linhas de execução dos eventos."""
    criar_banco_de_teste()
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture(scope="session")
def broker():
    """O broker de eventos (banco lógico 2), para os testes lerem e escreverem nos streams."""
    cliente = redis.Redis(
        host=config.EVENTOS_HOST, port=config.EVENTOS_PORTA, password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO, decode_responses=True,
    )
    yield cliente
    cliente.close()


@pytest.fixture(autouse=True)
def ambiente_limpo(cliente, broker, game_falso):
    """Cada teste começa sem salas, sem eventos e com o Game falso respondendo 201. As linhas de
    execução dos eventos param durante a limpeza e recomeçam depois, como num serviço que sobe."""
    estado = cliente.app.state
    estado.consumidor.parar()
    estado.entregador.parar()
    with banco.engine.begin() as conexao:
        conexao.execute(text("TRUNCATE assentos, salas, eventos_pendentes"))
    broker.flushdb()
    game_falso.reiniciar()
    estado.entregador.iniciar()
    estado.consumidor.iniciar()


# ---------- Ajudantes usados nos testes ----------


def token(sub, nome="Jogador", validade=timedelta(hours=1), segredo=None, **extra):
    conteudo = {"sub": sub, "nome": nome, "exp": datetime.now(timezone.utc) + validade, **extra}
    return jwt.encode(conteudo, segredo or config.JWT_SEGREDO, algorithm="HS256")


class Jogador:
    """Um usuário logado, com um token do mesmo formato do Auth, e as chamadas às rotas."""

    def __init__(self, cliente, nome):
        self.cliente = cliente
        self.id = str(uuid.uuid4())
        self.nome = nome
        self.headers = {"Authorization": f"Bearer {token(self.id, nome)}"}

    def get(self, caminho):
        return self.cliente.get(URL + caminho, headers=self.headers)

    def post(self, caminho, corpo=None):
        if corpo is None:
            return self.cliente.post(URL + caminho, headers=self.headers)  # sem corpo, como a tela
        return self.cliente.post(URL + caminho, headers=self.headers, json=corpo)

    def delete(self, caminho):
        return self.cliente.delete(URL + caminho, headers=self.headers)

    def criar_sala(self, formato="1x1"):
        resposta = self.post("/salas", {"formato": formato})
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    def entrar(self, sala, assento):
        resposta = self.post(f"/salas/{sala['id']}/entrar", {"assento": assento})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def bot(self, sala, assento):
        resposta = self.post(f"/salas/{sala['id']}/bot", {"assento": assento, "nivel": "padrao"})
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    def iniciar(self, sala):
        resposta = self.post(f"/salas/{sala['id']}/iniciar")
        assert resposta.status_code == 200, resposta.text
        return resposta.json()["partida_id"]

    def assento_na(self, sala):
        return next((a["assento"] for a in sala["assentos"] if a["usuario_id"] == self.id), None)


@pytest.fixture
def ana(cliente):
    return Jogador(cliente, "Ana")


@pytest.fixture
def beto(cliente):
    return Jogador(cliente, "Beto")


@pytest.fixture
def caio(cliente):
    return Jogador(cliente, "Caio")


@pytest.fixture
def duda(cliente):
    return Jogador(cliente, "Duda")


def assento_vazio(numero):
    return {"assento": numero, "usuario_id": None, "nome": None, "bot": False}


def erro(resposta):
    """O código de um erro, conferindo que ele veio no formato do contrato, com mensagem."""
    corpo = resposta.json()
    assert set(corpo) == {"erro", "mensagem"} and corpo["mensagem"], corpo
    return corpo["erro"]


def envelhecer_presenca(sala_id, usuario_id, segundos):
    """Faz de conta que o jogador pediu a sala pela última vez há tantos segundos."""
    with banco.engine.begin() as conexao:
        conexao.execute(
            text("UPDATE assentos SET visto_em = now() - make_interval(secs => :s) WHERE sala_id = :sala AND usuario_id = :u"),
            {"s": segundos, "sala": sala_id, "u": usuario_id},
        )


def esperar(condicao, limite=3.0):
    """Espera a condição ficar verdadeira (quem age é uma linha de execução em paralelo)."""
    fim = time.monotonic() + limite
    while not condicao():
        if time.monotonic() > fim:
            return False
        time.sleep(0.02)
    return True


def eventos_do_stream(broker, nome, quantidade=1, espera=3.0):
    """Os eventos publicados no stream, já lidos do JSON."""
    esperar(lambda: broker.xlen(nome) >= quantidade, espera)
    return [json.loads(campos["dados"]) for _id, campos in broker.xrange(nome)]
