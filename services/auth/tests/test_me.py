"""GET /api/auth/me (docs/guia-backend-login.md, seções 3.5 e 6.6)."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import config

TOKEN_INVALIDO = {"erro": "token_invalido", "mensagem": "Sessão inválida. Entre de novo."}


def consultar(cliente, token=None, autorizacao=None):
    if token is not None:
        autorizacao = f"Bearer {token}"
    headers = {"Authorization": autorizacao} if autorizacao else {}
    return cliente.get("/api/auth/me", headers=headers)


def token_feito_a_mao(sub, exp_em=timedelta(hours=1), segredo=None):
    conteudo = {"sub": sub, "nome": "Ana", "exp": datetime.now(timezone.utc) + exp_em}
    return jwt.encode(conteudo, segredo or config.JWT_SEGREDO, algorithm="HS256")


def test_me_com_token_valido_devolve_o_usuario(cliente, token_da_ana):
    resposta = consultar(cliente, token_da_ana)

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"id", "nome", "email"}
    assert corpo["nome"] == "Ana"
    assert corpo["email"] == "ana@teste.com"


def test_token_vencido_responde_token_expirado(cliente, token_da_ana):
    id_da_ana = consultar(cliente, token_da_ana).json()["id"]

    resposta = consultar(cliente, token_feito_a_mao(id_da_ana, exp_em=timedelta(seconds=-1)))

    assert resposta.status_code == 401
    assert resposta.json() == {"erro": "token_expirado", "mensagem": "Sua sessão expirou. Entre de novo."}


@pytest.mark.parametrize(
    "autorizacao",
    [
        None,  # sem o cabeçalho
        "Bearer isto-nao-e-um-token",
        "Basic YW5hOnNlZ3JlZG8x",  # outro esquema, sem "Bearer"
    ],
)
def test_sem_token_valido_responde_token_invalido(cliente, autorizacao):
    resposta = consultar(cliente, autorizacao=autorizacao)

    assert resposta.status_code == 401
    assert resposta.json() == TOKEN_INVALIDO


def test_token_adulterado_responde_token_invalido(cliente, token_da_ana):
    resposta = consultar(cliente, token_da_ana + "x")

    assert resposta.status_code == 401
    assert resposta.json() == TOKEN_INVALIDO


def test_token_assinado_com_outro_segredo_responde_token_invalido(cliente, token_da_ana):
    id_da_ana = consultar(cliente, token_da_ana).json()["id"]

    resposta = consultar(cliente, token_feito_a_mao(id_da_ana, segredo="outro-segredo-" + "x" * 32))

    assert resposta.status_code == 401
    assert resposta.json() == TOKEN_INVALIDO


@pytest.mark.parametrize("sub", [str(uuid.uuid4()), "nao-e-um-uuid"])
def test_token_de_usuario_inexistente_responde_token_invalido(cliente, sub):
    resposta = consultar(cliente, token_feito_a_mao(sub))

    assert resposta.status_code == 401
    assert resposta.json() == TOKEN_INVALIDO
