"""Hash de senha (argon2) e token de login (JWT)."""

import uuid
from datetime import datetime, timezone

import jwt  # pacote PyJWT
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app import config

# argon2id com os parâmetros padrão da biblioteca. Cada cálculo é lento de propósito (uma fração
# de segundo), para dificultar quem tenta adivinhar senhas em massa.
hasher = PasswordHasher()


# ---------- Senha ----------
# O banco guarda só o hash. A mesma senha gera um hash diferente a cada vez, então não dá para
# comparar hashes com ==: busque o usuário pelo e-mail e confira com senha_confere().


def gerar_hash(senha: str) -> str:
    return hasher.hash(senha)


def senha_confere(senha_hash: str, senha: str) -> bool:
    """Compara a senha digitada com o hash guardado."""
    try:
        return hasher.verify(senha_hash, senha)
    except VerifyMismatchError:
        return False


# ---------- Token (JWT) ----------
# O conteúdo do token não é secreto (qualquer um lê), mas não pode ser alterado sem invalidar a
# assinatura. Por isso ele leva só o id e o nome, nunca senha ou hash.


def criar_token(usuario_id: uuid.UUID, nome: str) -> str:
    """Emite o JWT: quem é o usuário (sub), o nome dele e até quando o token vale (exp)."""
    conteudo = {
        "sub": str(usuario_id),  # tem que ser texto: o PyJWT recusa outro tipo na validação
        "nome": nome,
        "exp": datetime.now(timezone.utc) + config.JWT_VALIDADE,
    }
    return jwt.encode(conteudo, config.JWT_SEGREDO, algorithm=config.JWT_ALGORITMO)


def conteudo_do_token(token: str) -> dict:
    """Confere a assinatura e a validade do token e devolve o que há dentro dele.

    Levanta jwt.ExpiredSignatureError quando o token venceu e jwt.InvalidTokenError (de que a
    anterior é um caso particular) quando ele não serve por qualquer outro motivo.
    Lobby, Game e Ranking repetem esta mesma função, com o mesmo JWT_SEGREDO.
    """
    return jwt.decode(
        token,
        config.JWT_SEGREDO,
        algorithms=[config.JWT_ALGORITMO],
        options={"require": ["sub", "exp"]},  # recusa token sem dono ou sem validade
    )
