"""Leitura do partida.finalizada: idempotente pelo partida_id, inclusive para os eventos que o Game
publicou antes de o Ranking subir (app/eventos.py)."""

import json

import pytest

from tests.conftest import (
    STREAM,
    Pessoa,
    esperar,
    partida,
    partidas_registradas,
    publicar,
    publicar_e_esperar,
    tudo_lido,
    vitoria,
)


def linha_de(cliente, pessoa):
    linhas = cliente.get("/api/ranking", headers=pessoa.headers).json()
    return next(((l["vitorias"], l["partidas"]) for l in linhas if l["usuario_id"] == pessoa.id), None)


def test_o_mesmo_partida_finalizada_entregue_varias_vezes_conta_uma_vez(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    evento = vitoria(ana, beto)

    publicar_e_esperar(broker, evento, evento)
    publicar_e_esperar(broker, evento)  # mais tarde, de novo (o Game reenviou depois de uma queda)

    assert broker.xlen(STREAM) == 3
    assert partidas_registradas() == 1
    assert linha_de(cliente, ana) == (1, 1)
    assert linha_de(cliente, beto) == (0, 1)


def test_ao_subir_le_os_eventos_publicados_antes_sem_duplicar(cliente, broker, consumidor):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    primeira, segunda = vitoria(ana, beto), vitoria(beto, ana)
    # O Ranking ainda não existe: o Game publica três eventos (um repetido) e não há grupo.
    consumidor.parar()
    broker.delete(STREAM)
    publicar(broker, primeira, segunda, primeira)
    assert broker.xinfo_groups(STREAM) == []

    consumidor.iniciar()  # o Ranking sobe

    assert esperar(lambda: tudo_lido(broker))
    assert partidas_registradas() == 2
    assert linha_de(cliente, ana) == (1, 2)

    # O grupo some (o broker perdeu os dados dele) e tudo é lido de novo, desde o início:
    # nenhuma partida conta duas vezes.
    consumidor.parar()
    broker.xgroup_destroy(STREAM, "ranking")
    consumidor.iniciar()
    assert esperar(lambda: tudo_lido(broker))
    assert partidas_registradas() == 2
    assert linha_de(cliente, ana) == (1, 2)


def test_evento_lido_e_nao_confirmado_antes_de_uma_queda_e_lido_de_novo(cliente, broker, consumidor):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    publicar_e_esperar(broker, vitoria(ana, beto))
    consumidor.parar()
    publicar(broker, vitoria(ana, beto))
    # Simula a queda: o Ranking leu a mensagem e caiu antes de gravar e confirmar.
    broker.xreadgroup("ranking", "ranking-1", {STREAM: ">"}, count=10)

    consumidor.iniciar()

    assert esperar(lambda: tudo_lido(broker))
    assert linha_de(cliente, ana) == (2, 2)


@pytest.mark.parametrize(
    "estragar",
    [
        lambda e: "isto não é json",
        lambda e: {**e, "partida_id": None},
        lambda e: {**e, "vencedor_time": "C"},
        lambda e: {**e, "placar_final": {"A": "doze"}},
        lambda e: {**e, "encerrada_em": "ontem"},
        lambda e: {**e, "times": {"A": [{"assento": 0, "usuario_id": None, "nome": "Ana", "bot": False}], "B": []}},
        lambda e: {**e, "times": {"A": [e["times"]["A"][0]], "B": [{**e["times"]["A"][0], "assento": 1}]}},
    ],
)
def test_evento_fora_do_formato_e_confirmado_sem_contar_e_sem_travar_a_fila(cliente, broker, estragar):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    estragado = estragar(vitoria(beto, ana))

    publicar_e_esperar(broker, estragado, vitoria(ana, beto))  # o que vem depois continua sendo lido

    assert partidas_registradas() == 1
    assert linha_de(cliente, ana) == (1, 1)


def test_mensagem_sem_o_campo_dados_e_confirmada(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    broker.xadd(STREAM, {"outro": "campo"})

    publicar_e_esperar(broker, vitoria(ana, beto))

    assert linha_de(cliente, ana) == (1, 1)


def test_evento_do_script_de_teste_sem_sala_conta(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    evento = vitoria(ana, beto)
    evento["sala_id"] = None  # partida criada pelo scripts/partida_de_teste.py do Game

    publicar_e_esperar(broker, json.dumps(evento))

    assert linha_de(cliente, ana) == (1, 1)


def test_evento_com_data_sem_fuso_vale_como_utc(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    evento = partida([ana.jogador(0)], [beto.jogador(1)])
    evento["encerrada_em"] = "2026-10-28T14:00:00"

    publicar_e_esperar(broker, evento)

    historico = cliente.get(f"/api/ranking/jogadores/{ana.id}", headers=ana.headers).json()
    assert historico["ultimas_partidas"][0]["encerrada_em"] == "2026-10-28T14:00:00+00:00"
