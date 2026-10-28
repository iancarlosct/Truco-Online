"""GET /api/ranking/jogadores/{id}: estatísticas e últimas partidas (RF18)."""

from datetime import datetime, timezone

from app import config
from tests.conftest import Pessoa, bot, partida, publicar_e_esperar, vitoria


def test_estatisticas_e_ultimas_partidas_da_mais_recente_para_a_mais_antiga(cliente, broker):
    ana, beto, caio = Pessoa("Ana"), Pessoa("Beto"), Pessoa("Caio")
    primeira = vitoria(ana, beto, encerrada_em=datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc))
    segunda = partida(
        [ana.jogador(0), bot(2)],
        [beto.jogador(1), caio.jogador(3)],
        vencedor="B",
        encerrada_em=datetime(2026, 10, 28, 15, 30, tzinfo=timezone.utc),
        placar={"A": 9, "B": 12},
    )
    publicar_e_esperar(broker, primeira, segunda)

    resposta = cliente.get(f"/api/ranking/jogadores/{ana.id}", headers=caio.headers)  # qualquer logado vê

    assert resposta.status_code == 200
    assert resposta.json() == {
        "usuario_id": ana.id,
        "nome": "Ana",
        "posicao": 1,  # Ana, Beto e Caio empatam com uma vitória
        "vitorias": 1,
        "derrotas": 1,
        "partidas": 2,
        "ultimas_partidas": [
            {
                "partida_id": segunda["partida_id"],
                "formato": "2x2",
                "encerrada_em": "2026-10-28T15:30:00+00:00",
                "time": "A",
                "venceu": False,
                "placar_final": {"A": 9, "B": 12},
                "times": {
                    "A": [ana.jogador(0), bot(2)],
                    "B": [beto.jogador(1), caio.jogador(3)],
                },
            },
            {
                "partida_id": primeira["partida_id"],
                "formato": "1x1",
                "encerrada_em": "2026-10-28T14:00:00+00:00",
                "time": "A",
                "venceu": True,
                "placar_final": {"A": 12, "B": 7},
                "times": {"A": [ana.jogador(0)], "B": [beto.jogador(1)]},
            },
        ],
    }


def test_so_as_ultimas_partidas(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    eventos = [vitoria(ana, beto) for _ in range(config.ULTIMAS_PARTIDAS + 2)]
    publicar_e_esperar(broker, *eventos)

    corpo = cliente.get(f"/api/ranking/jogadores/{beto.id}", headers=beto.headers).json()

    assert corpo["partidas"] == config.ULTIMAS_PARTIDAS + 2
    assert corpo["derrotas"] == config.ULTIMAS_PARTIDAS + 2
    assert [p["partida_id"] for p in corpo["ultimas_partidas"]] == [e["partida_id"] for e in reversed(eventos)][
        : config.ULTIMAS_PARTIDAS
    ]


def test_quem_nunca_jogou_responde_404(cliente):
    ana = Pessoa("Ana")

    resposta = cliente.get(f"/api/ranking/jogadores/{ana.id}", headers=ana.headers)

    assert resposta.status_code == 404
    assert resposta.json() == {
        "erro": "jogador_nao_encontrado",
        "mensagem": "Este jogador ainda não tem partidas registradas.",
    }
