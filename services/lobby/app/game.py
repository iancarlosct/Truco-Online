"""Chamada ao serviço Game: POST /interno/partidas (docs/guia-backend-mesa.md, seção 10.3).

A rota é interna: fica fora do gateway, e o Lobby a alcança pela rede-servicos, em GAME_URL
(http://game:8000). O corpo é {"sala_id", "assentos": [{"assento", "usuario_id", "nome", "bot"}]},
e o Game responde 201 com {"partida_id"}.
"""

import json
import logging
import urllib.error
import urllib.request

from app import config

log = logging.getLogger("uvicorn.error")


class GameIndisponivel(Exception):
    """O Game não criou a partida: fora do ar, demorou mais que GAME_TEMPO_LIMITE, respondeu com
    erro ou com uma resposta sem partida_id. A rota responde 503 game_indisponivel."""


def criar_partida(sala_id: str, assentos: list[dict]) -> str:
    """Pede a partida ao Game e devolve o partida_id."""
    pedido = urllib.request.Request(
        f"{config.GAME_URL}/interno/partidas",
        data=json.dumps({"sala_id": sala_id, "assentos": assentos}).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=config.GAME_TEMPO_LIMITE) as resposta:
            partida_id = json.load(resposta).get("partida_id")
    except urllib.error.HTTPError as erro:
        # O Game respondeu com erro. Um 422 aqui seria um defeito do Lobby (ele só manda salas
        # completas, sem o mesmo usuário em dois assentos): o detalhe fica no log.
        log.warning("O Game recusou a partida da sala %s: HTTP %s %s", sala_id, erro.code, erro.read(500))
        raise GameIndisponivel from erro
    except (OSError, ValueError, AttributeError) as erro:
        # Fora do ar, tempo esgotado (TimeoutError é um OSError), ou resposta que não é um JSON
        # com partida_id.
        log.warning("O Game não criou a partida da sala %s: %r", sala_id, erro)
        raise GameIndisponivel from erro
    if not isinstance(partida_id, str) or not partida_id:
        log.warning("O Game respondeu sem partida_id para a sala %s.", sala_id)
        raise GameIndisponivel
    return partida_id
