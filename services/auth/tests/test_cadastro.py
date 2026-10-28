"""POST /api/auth/cadastro (docs/guia-backend-login.md, seções 3.3 e 5)."""

import uuid

import pytest
from sqlalchemy import text

from app import banco
from tests.conftest import ANA


def usuario_no_banco(email):
    with banco.engine.connect() as conexao:
        return conexao.execute(
            text("SELECT nome, email, senha_hash FROM usuarios WHERE email = :email"), {"email": email}
        ).mappings().first()


def test_cadastro_responde_201_com_id_e_nome(cadastrar):
    resposta = cadastrar()

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert set(corpo) == {"id", "nome"}  # nem a senha nem o hash voltam
    assert corpo["nome"] == "Ana"
    uuid.UUID(corpo["id"])  # o id é um UUID em texto


def test_cadastro_grava_email_em_minusculas_e_so_o_hash_da_senha(cadastrar):
    cadastrar({"nome": "  Ana  ", "email": "  Ana@Teste.COM ", "senha": "segredo1"})

    usuario = usuario_no_banco("ana@teste.com")
    assert usuario["nome"] == "Ana"  # sem os espaços das pontas
    assert usuario["senha_hash"].startswith("$argon2id$")
    assert "segredo1" not in usuario["senha_hash"]


def test_cadastro_aceita_os_limites_exatos(cadastrar):
    # 20 caracteres no nome (acentos contam 1, como na tela) e 6 na senha.
    resposta = cadastrar({"nome": "ã" * 20, "email": "limite@teste.com", "senha": "123456"})
    assert resposta.status_code == 201


@pytest.mark.parametrize("email", [ANA["email"], "ANA@teste.com", " ana@TESTE.com "])
def test_email_ja_cadastrado_responde_409(cadastrar, email):
    cadastrar()

    resposta = cadastrar({"nome": "Outra Ana", "email": email, "senha": "outrasenha"})

    assert resposta.status_code == 409
    assert resposta.json() == {"erro": "email_ja_cadastrado", "mensagem": "Este e-mail já está cadastrado."}


def test_email_repetido_que_chega_pelo_banco_tambem_responde_409(cadastrar, monkeypatch):
    # Simula dois cadastros simultâneos: a conferência da rota não vê o primeiro, e quem barra
    # o segundo é a restrição UNIQUE da tabela.
    cadastrar()
    monkeypatch.setattr(banco, "buscar_usuario_por_email", lambda email: None)

    resposta = cadastrar()

    assert resposta.status_code == 409
    assert resposta.json()["erro"] == "email_ja_cadastrado"


@pytest.mark.parametrize(
    ("dados", "mensagem"),
    [
        ({"nome": "1" * 21, "email": "bia@teste.com", "senha": "segredo1"}, "O nome pode ter no máximo 20 caracteres."),
        ({"nome": "   ", "email": "bia@teste.com", "senha": "segredo1"}, "Informe seu nome."),
        ({"nome": "Bia", "email": "bia-sem-arroba", "senha": "segredo1"}, "Informe um e-mail válido, como nome@exemplo.com."),
        ({"nome": "Bia", "email": "bia@teste", "senha": "segredo1"}, "Informe um e-mail válido, como nome@exemplo.com."),
        ({"nome": "Bia", "email": "", "senha": "segredo1"}, "Informe seu e-mail."),
        ({"nome": "Bia", "email": "bia@teste.com", "senha": "12345"}, "A senha precisa ter no mínimo 6 caracteres."),
    ],
)
def test_regra_violada_responde_422_dizendo_o_problema(cadastrar, dados, mensagem):
    resposta = cadastrar(dados)

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": mensagem}
    assert usuario_no_banco(dados["email"].strip().lower()) is None


@pytest.mark.parametrize(
    "corpo",
    [
        {"json": {"nome": "Bia", "email": "bia@teste.com"}},  # campo faltando
        {"json": {"nome": 123, "email": "bia@teste.com", "senha": "segredo1"}},  # número no lugar de texto
        {"content": "isto não é json", "headers": {"Content-Type": "application/json"}},
        {},  # sem corpo
    ],
)
def test_corpo_fora_do_formato_responde_422_no_formato_do_contrato(cliente, corpo):
    resposta = cliente.post("/api/auth/cadastro", **corpo)

    assert resposta.status_code == 422
    assert resposta.json()["erro"] == "dados_invalidos"
    assert resposta.json()["mensagem"]
