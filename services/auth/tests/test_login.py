"""POST /api/auth/login (docs/guia-backend-login.md, seções 3.4 e 6)."""

import time

import jwt
import pytest

from app import config
from tests.conftest import ANA

CREDENCIAIS_INVALIDAS = {"erro": "credenciais_invalidas", "mensagem": "E-mail ou senha incorretos."}


def entrar(cliente, email=ANA["email"], senha=ANA["senha"], **opcoes):
    return cliente.post("/api/auth/login", json={"email": email, "senha": senha}, **opcoes)


def test_login_responde_token_e_usuario(cliente, cadastrar):
    id_cadastrado = cadastrar().json()["id"]

    resposta = entrar(cliente)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["usuario"] == {"id": id_cadastrado, "nome": "Ana", "email": "ana@teste.com"}

    # O token é um JWT HS256 com sub (o id, em texto), nome e exp para daqui a 24 horas.
    assert jwt.get_unverified_header(corpo["token"])["alg"] == "HS256"
    conteudo = jwt.decode(corpo["token"], config.JWT_SEGREDO, algorithms=["HS256"])
    assert set(conteudo) == {"sub", "nome", "exp"}
    assert conteudo["sub"] == id_cadastrado
    assert conteudo["nome"] == "Ana"
    assert abs(conteudo["exp"] - (time.time() + 24 * 3600)) < 60


def test_login_nao_diferencia_maiusculas_no_email(cliente, cadastrar):
    cadastrar()

    resposta = entrar(cliente, email="  ANA@TESTE.COM ")

    assert resposta.status_code == 200
    assert resposta.json()["usuario"]["email"] == "ana@teste.com"


@pytest.mark.parametrize(
    ("email", "senha"),
    [
        (ANA["email"], "errada"),  # senha errada
        (ANA["email"], "1"),  # senha curta: é só mais uma senha errada, e não 422
        (ANA["email"], ""),
        (ANA["email"], "segredo1 "),  # a senha não é limpa: o espaço conta
        ("ninguem@teste.com", ANA["senha"]),  # e-mail sem conta: mesma resposta da senha errada
        ("isto-nem-e-email", ANA["senha"]),
    ],
)
def test_credenciais_erradas_respondem_401_sempre_igual(cliente, cadastrar, email, senha):
    cadastrar()

    resposta = entrar(cliente, email=email, senha=senha)

    assert resposta.status_code == 401
    assert resposta.json() == CREDENCIAIS_INVALIDAS


def test_login_ignora_token_antigo_no_cabecalho(cliente, cadastrar):
    # A tela manda o Authorization em qualquer chamada quando há token guardado, até no login.
    cadastrar()

    resposta = entrar(cliente, headers={"Authorization": "Bearer token.vencido.qualquer"})

    assert resposta.status_code == 200


def test_login_com_campo_faltando_responde_422(cliente):
    resposta = cliente.post("/api/auth/login", json={"email": ANA["email"]})

    assert resposta.status_code == 422
    assert resposta.json()["erro"] == "dados_invalidos"
