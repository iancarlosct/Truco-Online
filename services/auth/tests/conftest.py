"""Preparação dos testes. Eles rodam dentro do container, com o Postgres de verdade:

    docker compose run --rm auth pytest

Para não apagar os usuários de quem está usando o sistema, os testes usam um banco separado no
mesmo auth-db: o de sempre com "_teste" no fim (auth_teste, com o .env de exemplo). Ele é criado
na primeira vez, e a tabela é esvaziada antes de cada teste.
"""

import os

# O banco de teste tem que ser escolhido ANTES de importar o app: o app.config lê as variáveis
# de ambiente uma vez só, quando é importado.
BANCO_PRINCIPAL = os.environ["BANCO_NOME"]
BANCO_TESTE = f"{BANCO_PRINCIPAL}_teste"
os.environ["BANCO_NOME"] = BANCO_TESTE

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import banco  # noqa: E402
from app.main import app  # noqa: E402


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


@pytest.fixture(scope="session")
def cliente():
    """Cliente HTTP que chama o app direto, sem rede. O "with" roda o ciclo de vida do app, que
    cria a tabela no banco de teste."""
    criar_banco_de_teste()
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture(autouse=True)
def banco_vazio(cliente):
    """Cada teste começa sem nenhum usuário cadastrado."""
    with banco.engine.begin() as conexao:
        conexao.execute(text("TRUNCATE usuarios"))


# ---------- Ajudantes usados nos testes ----------

ANA = {"nome": "Ana", "email": "Ana@Teste.com", "senha": "segredo1"}


@pytest.fixture
def cadastrar(cliente):
    """Faz o cadastro e devolve a resposta. Sem argumentos, cadastra a ANA."""

    def fazer(dados=None):
        return cliente.post("/api/auth/cadastro", json=dados or ANA)

    return fazer


@pytest.fixture
def token_da_ana(cliente, cadastrar):
    """Cadastra a ANA, faz o login e devolve o token."""
    cadastrar()
    resposta = cliente.post("/api/auth/login", json={"email": ANA["email"], "senha": ANA["senha"]})
    return resposta.json()["token"]
