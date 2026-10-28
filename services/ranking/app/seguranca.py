"""Token (JWT) de quem chama as rotas do Ranking.

O Ranking confere o token sozinho, com o mesmo JWT_SEGREDO do Auth, sem chamar o Auth
(docs/guia-backend-lobby.md, seção 6.1). É a mesma conferência do GET /api/auth/me: o "sub" é o
id do usuário, sempre um UUID no Auth. É com ele que GET /api/ranking acha a linha do usuário
logado.
"""

import uuid

import jwt  # pacote PyJWT
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config
from app.erros import ErroRanking

# Lê o cabeçalho "Authorization: Bearer <token>". Com auto_error=False, quando ele falta o
# FastAPI não responde sozinho (seria no formato dele): quem decide é usuario_logado.
bearer = HTTPBearer(auto_error=False)


def usuario_logado(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Dependência das rotas: confere o token e devolve o id do usuário (o "sub"). Sem token
    válido, a rota nem roda: a resposta é 401."""
    if credenciais is None:  # sem o cabeçalho, ou sem a palavra "Bearer"
        raise ErroRanking("token_invalido")
    try:
        conteudo = jwt.decode(
            credenciais.credentials,
            config.JWT_SEGREDO,
            algorithms=[config.JWT_ALGORITMO],
            options={"require": ["sub", "exp"]},  # recusa token sem dono ou sem validade
        )
        uuid.UUID(conteudo["sub"])  # só usuários do Auth: o token de um bot ("bot-...") não vale
    except jwt.ExpiredSignatureError:  # vem antes: é um caso particular de InvalidTokenError
        raise ErroRanking("token_expirado")
    except (jwt.InvalidTokenError, ValueError):
        raise ErroRanking("token_invalido")
    return conteudo["sub"]
