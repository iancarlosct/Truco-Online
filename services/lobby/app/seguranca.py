"""Token (JWT) de quem chama as rotas do Lobby.

O Lobby confere o token sozinho, com o mesmo JWT_SEGREDO do Auth, sem chamar o Auth
(docs/guia-backend-lobby.md, seção 6.1). É a mesma conferência do GET /api/auth/me:

- o "sub" é o id do usuário, o mesmo "usuario.id" que a tela recebeu no login. É com ele que a
  tela acha o próprio assento e descobre se é dona da sala. No Auth ele é sempre um UUID; um
  "sub" que não é UUID (o token de um bot, "bot-<partida>-<assento>", por exemplo) é recusado:
  só jogadores usam o Lobby;
- o "nome" é o que vai na plaquinha do assento. O Lobby não consulta o Auth (P16 do guia).
"""

import uuid

import jwt  # pacote PyJWT
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config
from app.erros import ErroLobby

# Lê o cabeçalho "Authorization: Bearer <token>". Com auto_error=False, quando ele falta o
# FastAPI não responde sozinho (seria no formato dele): quem decide é usuario_logado.
bearer = HTTPBearer(auto_error=False)


def usuario_do_token(token: str) -> dict:
    """{"id", "nome"} do dono do token. Levanta ErroLobby token_expirado ou token_invalido."""
    try:
        conteudo = jwt.decode(
            token,
            config.JWT_SEGREDO,
            algorithms=[config.JWT_ALGORITMO],
            options={"require": ["sub", "exp"]},  # recusa token sem dono ou sem validade
        )
        uuid.UUID(conteudo["sub"])
    except jwt.ExpiredSignatureError:  # vem antes: é um caso particular de InvalidTokenError
        raise ErroLobby("token_expirado")
    except (jwt.InvalidTokenError, ValueError):
        raise ErroLobby("token_invalido")
    nome = conteudo.get("nome")
    if not isinstance(nome, str) or not nome.strip() or len(nome) > config.NOME_MAX:
        raise ErroLobby("token_invalido")  # o Auth sempre põe um nome de 1 a 20 caracteres
    return {"id": conteudo["sub"], "nome": nome}


def usuario_do_cabecalho(autorizacao: str | None) -> dict:
    """Confere o valor do cabeçalho Authorization ("Bearer <token>")."""
    esquema, _, token = (autorizacao or "").partition(" ")
    if esquema.lower() != "bearer" or not token:
        raise ErroLobby("token_invalido")
    return usuario_do_token(token.strip())


def usuario_logado(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Dependência das rotas: o FastAPI a chama antes da rota, e sem token válido a rota nem roda
    (a resposta é 401). Devolve {"id", "nome"}."""
    if credenciais is None:  # sem o cabeçalho, ou sem a palavra "Bearer"
        raise ErroLobby("token_invalido")
    return usuario_do_token(credenciais.credentials)
