"""Token, formato dos erros que não vêm das regras (404, 405, 500) e a rota /saude."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import banco
from app.main import app
from tests.conftest import Pessoa, token

TOKEN_INVALIDO = {"erro": "token_invalido", "mensagem": "Sessão inválida. Entre de novo."}


@pytest.mark.parametrize(
    "autorizacao",
    [
        None,
        "Bearer isto-nao-e-um-token",
        "Basic YW5hOnNlZ3JlZG8x",
        f"Bearer {token(str(uuid.uuid4()), segredo='outro-segredo-' + 'x' * 32)}",
        f"Bearer {token('bot-p1-1', 'Bot 1')}",  # token de bot: o sub não é um usuário
    ],
)
@pytest.mark.parametrize("caminho", ["/api/ranking", f"/api/ranking/jogadores/{uuid.uuid4()}"])
def test_sem_token_valido_responde_401_token_invalido(cliente, autorizacao, caminho):
    headers = {"Authorization": autorizacao} if autorizacao else {}

    resposta = cliente.get(caminho, headers=headers)

    assert resposta.status_code == 401
    assert resposta.json() == TOKEN_INVALIDO


def test_token_vencido_responde_token_expirado(cliente):
    vencido = token(str(uuid.uuid4()), validade=timedelta(seconds=-1))

    resposta = cliente.get("/api/ranking", headers={"Authorization": f"Bearer {vencido}"})

    assert resposta.status_code == 401
    assert resposta.json() == {"erro": "token_expirado", "mensagem": "Sua sessão expirou. Entre de novo."}


def test_rota_inexistente_responde_no_formato_do_contrato(cliente):
    resposta = cliente.get("/api/ranking/nao/existe", headers=Pessoa("Ana").headers)

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "nao_encontrado", "mensagem": "Endereço não encontrado."}


def test_metodo_errado_responde_no_formato_do_contrato(cliente):
    resposta = cliente.post("/api/ranking", headers=Pessoa("Ana").headers)

    assert resposta.status_code == 405
    assert resposta.json()["erro"] == "metodo_nao_permitido"


def test_erro_inesperado_responde_500_no_formato_do_contrato(monkeypatch):
    def banco_quebrado(usuario_id):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(banco, "ranking", banco_quebrado)
    cliente = TestClient(app, raise_server_exceptions=False)

    resposta = cliente.get("/api/ranking", headers=Pessoa("Ana").headers)

    assert resposta.status_code == 500
    assert resposta.json() == {"erro": "erro_interno", "mensagem": "Ocorreu um erro no servidor. Tente de novo em instantes."}


def test_saude_responde_ok_com_o_banco_no_ar(cliente):
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
