"""Início da partida: o Game e o bot.solicitado (docs/guia-backend-lobby.md, seções 3.9 e 6.6)."""

import uuid

import pytest
import redis
from sqlalchemy import text

from app import banco, config
from tests.conftest import eventos_do_stream, erro, esperar


def test_iniciar_pede_a_partida_ao_game_e_grava_o_partida_id(ana, beto, game_falso):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    game_falso.corpo = {"partida_id": "p-123"}

    resposta = ana.post(f"/salas/{sala['id']}/iniciar")  # sem corpo, como a tela

    assert resposta.status_code == 200
    assert resposta.json() == {"partida_id": "p-123"}
    # O corpo enviado ao Game é o da seção 10.3 do guia da mesa.
    assert game_falso.pedidos == [
        {
            "caminho": "/interno/partidas",
            "corpo": {
                "sala_id": sala["id"],
                "assentos": [
                    {"assento": 0, "usuario_id": ana.id, "nome": "Ana", "bot": False},
                    {"assento": 1, "usuario_id": beto.id, "nome": "Beto", "bot": False},
                ],
            },
        }
    ]
    # Os outros jogadores vão para a mesa pelo GET da sala; ela sai da lista.
    depois = beto.get(f"/salas/{sala['id']}").json()
    assert (depois["status"], depois["partida_id"]) == ("em_partida", "p-123")
    assert beto.get("/salas").json() == []


def test_iniciar_publica_um_bot_solicitado_para_cada_bot(ana, beto, broker, game_falso):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 2)
    ana.bot(sala, 1)
    ana.bot(sala, 3)

    partida_id = ana.iniciar(sala)

    assert [a["bot"] for a in game_falso.pedidos[0]["corpo"]["assentos"]] == [False, True, False, True]
    assert eventos_do_stream(broker, "bot.solicitado", quantidade=2) == [
        {"partida_id": partida_id, "assento": 1, "nome": "Bot 1", "nivel": "padrao"},
        {"partida_id": partida_id, "assento": 3, "nome": "Bot 2", "nivel": "padrao"},
    ]


def test_partida_sem_bots_nao_publica_nada(ana, beto, broker):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    ana.iniciar(sala)

    assert eventos_do_stream(broker, "bot.solicitado", espera=0.3) == []


def test_conferencias_na_ordem_do_guia(ana, beto, game_falso):
    sala = ana.criar_sala()

    assert ana.post(f"/salas/{uuid.uuid4()}/iniciar").status_code == 404
    assert erro(beto.post(f"/salas/{sala['id']}/iniciar")) == "apenas_dono"
    resposta = ana.post(f"/salas/{sala['id']}/iniciar")
    assert resposta.status_code == 409
    assert resposta.json() == {"erro": "sala_incompleta", "mensagem": "A partida só começa com todos os assentos ocupados."}

    beto.entrar(sala, 1)
    ana.iniciar(sala)
    assert erro(beto.post(f"/salas/{sala['id']}/iniciar")) == "apenas_dono"  # o dono vem antes
    assert erro(ana.post(f"/salas/{sala['id']}/iniciar")) == "partida_ja_iniciada"
    assert len(game_falso.pedidos) == 1


@pytest.mark.parametrize(
    "falha",
    [
        {"status": 500, "corpo": {"erro": "erro_interno", "mensagem": "..."}},
        {"status": 422, "corpo": {"erro": "dados_invalidos", "mensagem": "..."}},
        {"status": 201, "corpo": {"outro": "campo"}},  # sem partida_id
        {"status": 201, "corpo": b"isto nao e json"},
        {"atraso": 0.5},  # mais que o tempo limite (0.2 s neste teste)
    ],
)
def test_game_que_nao_responde_da_503_e_a_sala_continua_aguardando(ana, beto, broker, game_falso, monkeypatch, falha):
    monkeypatch.setattr(config, "GAME_TEMPO_LIMITE", 0.2)
    sala = ana.criar_sala()
    ana.bot(sala, 1)
    for chave, valor in falha.items():
        setattr(game_falso, chave, valor)

    resposta = ana.post(f"/salas/{sala['id']}/iniciar")

    assert resposta.status_code == 503
    assert resposta.json() == {
        "erro": "game_indisponivel",
        "mensagem": "Não foi possível iniciar a partida agora. Tente de novo em instantes.",
    }
    depois = ana.get(f"/salas/{sala['id']}").json()
    assert (depois["status"], depois["partida_id"]) == ("aguardando", None)
    assert broker.xlen("bot.solicitado") == 0

    # O dono tenta de novo, com o Game de volta.
    game_falso.reiniciar()
    assert ana.post(f"/salas/{sala['id']}/iniciar").status_code == 200


def test_game_fora_do_ar_da_503(ana, beto, monkeypatch):
    monkeypatch.setattr(config, "GAME_URL", "http://127.0.0.1:9")  # porta sem ninguém
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    assert erro(ana.post(f"/salas/{sala['id']}/iniciar")) == "game_indisponivel"


def test_com_o_broker_fora_do_ar_a_partida_comeca_e_o_bot_solicitado_espera_na_fila(cliente, ana, broker):
    entregador = cliente.app.state.entregador
    broker_de_verdade = entregador.broker

    class BrokerForaDoAr:
        def xadd(self, *args, **kwargs):
            raise redis.ConnectionError("broker fora do ar (simulado)")

    def pendentes():
        with banco.engine.connect() as conexao:
            return conexao.execute(text("SELECT count(*) FROM eventos_pendentes")).scalar()

    entregador.broker = BrokerForaDoAr()
    try:
        sala = ana.criar_sala()
        ana.bot(sala, 1)
        partida_id = ana.iniciar(sala)
        assert ana.get(f"/salas/{sala['id']}").json()["status"] == "em_partida"
        assert esperar(lambda: pendentes() == 1)
        assert broker.xlen("bot.solicitado") == 0
    finally:
        entregador.broker = broker_de_verdade

    # Na próxima volta do Entregador (INTERVALO_DE_NOVA_TENTATIVA), o evento sai da fila.
    [evento] = eventos_do_stream(broker, "bot.solicitado")
    assert evento["partida_id"] == partida_id
    assert esperar(lambda: pendentes() == 0)
