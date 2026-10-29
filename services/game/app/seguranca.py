"""Token (JWT) da conexão com a mesa: quem está conectando e em que assento.

O Game confere o token sozinho, com o mesmo JWT_SEGREDO do Auth, sem chamar o Auth
(docs/guia-backend-login.md, seção 6.6). O token chega na URL do WebSocket (?token=<jwt>),
porque o navegador não deixa pôr cabeçalhos numa conexão WebSocket.

Dois tipos de token valem:

- Jogador: o token do login, emitido pelo Auth. O "sub" é o id do usuário (UUID em texto), o
  mesmo "usuario_id" que o Lobby mandou na criação da partida. É por ele que o Game acha o
  assento do jogador.
- Bot (serviço de Bots, services/bots): o serviço de Bots assina o próprio token com o mesmo
  JWT_SEGREDO, em HS256, com "sub" no formato "bot-<partida_id>-<assento>", "nome" (o nome do
  assento, como "Bot 1") e "exp". O Game aceita esse token só na partida e no assento que
  ele indica, e só se o assento foi criado como bot. Um sub de usuário nunca começa com "bot-"
  (é um UUID), então os dois tipos não se confundem. O partida_id pode ter hífens (é um UUID):
  o assento é o número depois do ÚLTIMO hífen.

Como o token vem na URL, o Uvicorn o gravaria no log de cada conexão ("WebSocket
/ws/partidas/...?token=<jwt>" [accepted]). O filtro SemTokenNoLog, instalado em main.py, tira o
valor antes de a linha ser escrita. O gateway faz o mesmo no log de acesso dele
(gateway/nginx.conf).
"""

import logging
import re

import jwt  # pacote PyJWT

from app import config

SUB_DE_BOT = re.compile(r"bot-(?P<partida_id>.+)-(?P<assento>[0-9]+)")

# O valor do parâmetro token numa URL: tudo depois de "token=" até o próximo "&", espaço ou aspas.
TOKEN_NA_URL = re.compile(r"(token=)[^&\s\"]+")


def conteudo_do_token(token: str) -> dict:
    """Confere a assinatura e a validade do token e devolve o que há dentro dele. A mesma
    conferência do Auth: levanta jwt.InvalidTokenError (ou jwt.ExpiredSignatureError, um caso
    particular dele) quando o token não serve."""
    return jwt.decode(
        token,
        config.JWT_SEGREDO,
        algorithms=[config.JWT_ALGORITMO],
        options={"require": ["sub", "exp"]},  # recusa token sem dono ou sem validade
    )


def dono_do_token(token: str) -> str | None:
    """O "sub" do token, ou None quando o token está ausente, adulterado, vencido ou foi
    assinado com outro segredo (a conexão é recusada com 4401)."""
    try:
        return conteudo_do_token(token)["sub"]
    except jwt.InvalidTokenError:
        return None


def assento_na_partida(estado: dict, sub: str) -> int | None:
    """Assento do dono do token nesta partida, ou None se ele não faz parte dela (4403)."""
    bot = SUB_DE_BOT.fullmatch(sub)
    if bot:
        if bot["partida_id"] != estado["partida_id"]:
            return None
        assento = int(bot["assento"])
        eh_bot = any(j["assento"] == assento and j["bot"] for j in estado["jogadores"])
        return assento if eh_bot else None
    return next((j["assento"] for j in estado["jogadores"] if not j["bot"] and j["usuario_id"] == sub), None)


class SemTokenNoLog(logging.Filter):
    """Troca o valor do token por "***" nas linhas de log, que continuam saindo: o log segue
    mostrando cada conexão, com o caminho e a partida, só sem o token."""

    def filter(self, registro: logging.LogRecord) -> bool:
        mensagem = registro.getMessage()
        if "token=" in mensagem:
            registro.msg = TOKEN_NA_URL.sub(r"\1***", mensagem)
            registro.args = ()
        return True
