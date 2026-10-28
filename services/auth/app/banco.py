"""Acesso ao banco do Auth (container auth-db). Só este serviço conecta nele.

Usa o SQLAlchemy 2 com o driver psycopg 3, escrevendo o SQL à mão com text(): as consultas são
as da seção 7 do docs/guia-backend-login.md. Os dados do usuário entram sempre como parâmetros
(:email, :nome...), nunca juntando textos, para evitar injeção de SQL.
"""

import uuid

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import config

# Código de erro do Postgres para "valor repetido numa coluna UNIQUE".
VIOLACAO_DE_UNICIDADE = "23505"

# O engine guarda um conjunto de conexões abertas e reaproveita cada uma entre as requisições.
engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        username=config.BANCO_USUARIO,
        password=config.BANCO_SENHA,
        host=config.BANCO_HOST,
        port=config.BANCO_PORTA,
        database=config.BANCO_NOME,
    ),
    pool_pre_ping=True,  # descarta conexões que caíram (se o banco reiniciou, por exemplo)
    connect_args={"connect_timeout": 5},  # segundos; sem isso, um banco fora do ar trava a rota
)


class EmailJaCadastrado(Exception):
    """O e-mail já tem conta: o banco recusou o INSERT pela restrição UNIQUE."""


# ---------- Criação da tabela ----------

# A tabela é criada pelo próprio serviço, toda vez que ele sobe. O "IF NOT EXISTS" deixa o
# comando idempotente: na primeira vez cria a tabela, nas outras não faz nada e não mexe nos
# dados. Assim ninguém precisa rodar nenhum script à mão, e o banco novo de quem acabou de clonar
# o repositório fica pronto sozinho.
# Escolhemos isso no lugar de uma ferramenta de migrações (como o Alembic) por ser o mais simples
# para uma equipe iniciante e para uma tabela que quase não muda. O limite: este comando não
# altera uma tabela que já existe. Se a estrutura mudar (uma coluna nova, por exemplo), é preciso
# um ALTER TABLE à mão ou recriar o banco do zero (docker compose down -v, que apaga os usuários).
# Se isso começar a acontecer com frequência, é a hora de adotar o Alembic.
SQL_CRIAR_TABELA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       VARCHAR(20) NOT NULL,
    email      TEXT        NOT NULL UNIQUE,
    senha_hash TEXT        NOT NULL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def criar_tabela() -> None:
    # engine.begin() abre uma transação e confirma (commit) ao sair do bloco.
    with engine.begin() as conexao:
        conexao.execute(text(SQL_CRIAR_TABELA))


# ---------- Consultas ----------
# Cada função devolve o usuário como dicionário, ou None quando ele não existe. O id vem do
# Postgres como objeto uuid.UUID: quem precisa dele em texto (o token, por exemplo) usa str().


def inserir_usuario(nome: str, email: str, senha_hash: str) -> dict:
    """Grava o usuário e devolve {id, nome}. Levanta EmailJaCadastrado se o e-mail já existe."""
    try:
        # O commit acontece ao sair do bloco, antes de a rota responder: o login que a tela faz
        # logo depois do cadastro já encontra o usuário.
        with engine.begin() as conexao:
            linha = conexao.execute(
                text(
                    "INSERT INTO usuarios (nome, email, senha_hash) "
                    "VALUES (:nome, :email, :senha_hash) RETURNING id, nome"
                ),
                {"nome": nome, "email": email, "senha_hash": senha_hash},
            ).mappings().one()
    except IntegrityError as erro:
        # Dois cadastros com o mesmo e-mail ao mesmo tempo passam os dois pela conferência da
        # rota; o segundo INSERT esbarra no UNIQUE da tabela e chega aqui.
        if getattr(erro.orig, "sqlstate", None) == VIOLACAO_DE_UNICIDADE:
            raise EmailJaCadastrado from erro
        raise
    return dict(linha)


def buscar_usuario_por_email(email: str) -> dict | None:
    """{id, nome, email, senha_hash} do usuário com este e-mail (já em minúsculas)."""
    with engine.connect() as conexao:
        linha = conexao.execute(
            text("SELECT id, nome, email, senha_hash FROM usuarios WHERE email = :email"),
            {"email": email},
        ).mappings().first()
    return dict(linha) if linha else None


def buscar_usuario_por_id(usuario_id: uuid.UUID) -> dict | None:
    """{id, nome, email} do usuário com este id."""
    with engine.connect() as conexao:
        linha = conexao.execute(
            text("SELECT id, nome, email FROM usuarios WHERE id = :id"),
            {"id": usuario_id},
        ).mappings().first()
    return dict(linha) if linha else None


def banco_disponivel() -> bool:
    """Confere se o banco responde. Usada pela rota /saude."""
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
