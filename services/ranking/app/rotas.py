"""Rotas do Ranking: o ranking geral e o histórico de um jogador (docs/guia-backend-lobby.md, seções
3.10, 4.4 e 6.7).

O gateway repassa o caminho inteiro e sem barra no fim: a tela pede /api/ranking. Por isso o
prefixo completo fica no APIRouter, e a rota do ranking geral é a "" (o próprio prefixo).
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import banco
from app.erros import ErroRanking
from app.seguranca import usuario_logado

rotas = APIRouter(prefix="/api/ranking")

UsuarioId = Annotated[str, Depends(usuario_logado)]


@rotas.get("")
def ranking(usuario_id: UsuarioId):
    """[{posicao, usuario_id, nome, vitorias, partidas}]: os 10 primeiros em vitórias e, se o
    usuário logado estiver abaixo deles, a linha dele no fim. Empates dividem a posição (1, 2, 2,
    4). Sem nenhuma partida registrada, []."""
    return banco.ranking(usuario_id)


@rotas.get("/jogadores/{jogador_id}")
def jogador(jogador_id: str, usuario_id: UsuarioId):
    """Estatísticas e últimas partidas de um jogador (RF18), para qualquer usuário logado:

        {"usuario_id", "nome", "posicao", "vitorias", "derrotas", "partidas",
         "ultimas_partidas": [{"partida_id", "formato", "encerrada_em", "time", "venceu",
                               "placar_final": {"A", "B"},
                               "times": {"A": [{"assento", "usuario_id", "nome", "bot"}], "B": [...]}}]}

    As últimas partidas vêm da mais recente para a mais antiga, no máximo ULTIMAS_PARTIDAS. Quem
    nunca jogou responde 404 jogador_nao_encontrado, como quem não aparece no ranking."""
    dados = banco.jogador(jogador_id)
    if dados is None:
        raise ErroRanking("jogador_nao_encontrado")
    return {
        "usuario_id": dados["usuario_id"],
        "nome": dados["nome"],
        "posicao": dados["posicao"],
        "vitorias": dados["vitorias"],
        "derrotas": dados["partidas"] - dados["vitorias"],
        "partidas": dados["partidas"],
        "ultimas_partidas": [
            {
                "partida_id": partida["partida_id"],
                "formato": partida["formato"],
                "encerrada_em": partida["encerrada_em"],
                "time": partida["time"],
                "venceu": partida["time"] == partida["vencedor_time"],
                "placar_final": {"A": partida["placar_a"], "B": partida["placar_b"]},
                "times": partida["times"],
            }
            for partida in dados["ultimas_partidas"]
        ],
    }
