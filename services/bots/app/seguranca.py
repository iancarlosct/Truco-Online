"""Token (JWT) que o bot apresenta ao Game ao conectar à mesa.

O serviço de Bots assina o próprio token, sem passar pelo Auth, com o mesmo JWT_SEGREDO dos
outros serviços (docs/guia-backend-mesa.md, seção 10.5):

- HS256;
- "sub" no formato "bot-<partida_id>-<assento>": diz ao Game a partida e o assento do bot. Um
  usuário nunca tem um "sub" assim (o dele é um UUID), então os dois tipos não se confundem;
- "nome", o nome do assento ("Bot 1"), que vem no bot.solicitado;
- "exp", obrigatório como em qualquer token.

O Game aceita esse token só na partida indicada e só num assento que foi criado como bot: com
outra partida ou outro assento, fecha a conexão com 4403.
"""

from datetime import datetime, timedelta, timezone

import jwt  # pacote PyJWT

from app import config


def sub_do_bot(partida_id: str, assento: int) -> str:
    return f"bot-{partida_id}-{assento}"


def token_do_bot(partida_id: str, assento: int, nome: str) -> str:
    """Um token novo para o bot deste assento. O bot assina um a cada conexão."""
    agora = datetime.now(timezone.utc)
    conteudo = {
        "sub": sub_do_bot(partida_id, assento),
        "nome": nome,
        "iat": agora,
        "exp": agora + timedelta(seconds=config.VALIDADE_DO_TOKEN),
    }
    return jwt.encode(conteudo, config.JWT_SEGREDO, algorithm=config.JWT_ALGORITMO)
