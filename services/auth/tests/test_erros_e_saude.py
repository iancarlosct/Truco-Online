"""Formato dos erros que não vêm das regras (404, 405, 500) e a rota /saude."""

from fastapi.testclient import TestClient

from app import banco
from app.main import app


def test_rota_inexistente_responde_no_formato_do_contrato(cliente):
    resposta = cliente.get("/api/auth/nao-existe")

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "nao_encontrado", "mensagem": "Endereço não encontrado."}


def test_metodo_errado_responde_no_formato_do_contrato(cliente):
    resposta = cliente.get("/api/auth/login")

    assert resposta.status_code == 405
    assert resposta.json()["erro"] == "metodo_nao_permitido"
    assert resposta.headers["allow"] == "POST"


def test_erro_inesperado_responde_500_no_formato_do_contrato(monkeypatch):
    def banco_quebrado(email):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(banco, "buscar_usuario_por_email", banco_quebrado)
    # Por padrão o TestClient repassa a exceção ao teste; aqui queremos ver a resposta.
    cliente = TestClient(app, raise_server_exceptions=False)

    resposta = cliente.post("/api/auth/login", json={"email": "ana@teste.com", "senha": "segredo1"})

    assert resposta.status_code == 500
    assert resposta.json() == {
        "erro": "erro_interno",
        "mensagem": "Ocorreu um erro no servidor. Tente de novo em instantes.",
    }


def test_saude_responde_ok_com_o_banco_no_ar(cliente):
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}
