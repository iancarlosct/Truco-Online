"""Leitura do partida.finalizada: a sala da partida passa a "encerrada" (app/eventos.py).

Os eventos são publicados no broker de teste como o Game publica: no stream "partida.finalizada",
com o evento em JSON no campo "dados". Quem lê é o Consumidor, que roda em paralelo ao teste."""

import json

from tests.conftest import esperar

STREAM = "partida.finalizada"


def finalizada(partida_id, sala_id=None):
    return {
        "partida_id": partida_id,
        "sala_id": sala_id,
        "formato": "1x1",
        "times": {"A": [], "B": []},
        "vencedor_time": "A",
        "placar_final": {"A": 12, "B": 3},
        "encerrada_em": "2026-10-28T14:46:39+00:00",
    }


def publicar(broker, dados):
    texto = dados if isinstance(dados, str) else json.dumps(dados)
    return broker.xadd(STREAM, {"dados": texto})


def nada_pendente(broker):
    """O grupo "lobby" confirmou (XACK) tudo o que leu do stream."""
    grupos = {g["name"]: g for g in broker.xinfo_groups(STREAM)}
    return "lobby" in grupos and grupos["lobby"]["pending"] == 0 and grupos["lobby"]["lag"] == 0


def sala_em_partida(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    return sala, ana.iniciar(sala)


def test_partida_finalizada_encerra_a_sala_e_ela_sai_da_lista(ana, beto, broker):
    sala, partida_id = sala_em_partida(ana, beto)

    publicar(broker, finalizada(partida_id, sala["id"]))

    assert esperar(lambda: ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada")
    depois = ana.get(f"/salas/{sala['id']}").json()
    assert depois["partida_id"] == partida_id  # a sala continua dizendo qual partida teve
    assert beto.get("/salas").json() == []
    assert esperar(lambda: nada_pendente(broker))


def test_o_mesmo_evento_duas_vezes_tem_o_mesmo_efeito(ana, beto, caio, duda, broker):
    sala, partida_id = sala_em_partida(ana, beto)
    outra, _ = sala_em_partida(caio, duda)  # uma segunda partida, ainda em jogo

    publicar(broker, finalizada(partida_id, sala["id"]))
    publicar(broker, finalizada(partida_id, sala["id"]))

    assert esperar(lambda: nada_pendente(broker))
    assert ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada"
    assert ana.get(f"/salas/{outra['id']}").json()["status"] == "em_partida"


def test_partida_sem_sala_e_evento_fora_do_formato_sao_confirmados_sem_travar_a_fila(ana, beto, broker):
    sala, partida_id = sala_em_partida(ana, beto)

    publicar(broker, finalizada("partida-do-script-de-teste"))  # sem sala no Lobby
    publicar(broker, "isto não é json")
    publicar(broker, {"sem": "partida_id"})
    broker.xadd(STREAM, {"outro_campo": "x"})
    publicar(broker, finalizada(partida_id, sala["id"]))  # o que vem depois continua sendo lido

    assert esperar(lambda: ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada")
    assert esperar(lambda: nada_pendente(broker))


def test_evento_publicado_com_o_lobby_parado_e_lido_quando_ele_volta(cliente, ana, beto, broker):
    sala, partida_id = sala_em_partida(ana, beto)
    consumidor = cliente.app.state.consumidor
    consumidor.parar()

    publicar(broker, finalizada(partida_id, sala["id"]))
    assert ana.get(f"/salas/{sala['id']}").json()["status"] == "em_partida"

    consumidor.iniciar()
    assert esperar(lambda: ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada")


def test_evento_lido_e_nao_confirmado_antes_de_uma_queda_e_lido_de_novo(cliente, ana, beto, broker):
    sala, partida_id = sala_em_partida(ana, beto)
    consumidor = cliente.app.state.consumidor
    consumidor.parar()
    publicar(broker, finalizada(partida_id, sala["id"]))
    # Simula a queda: o Lobby (consumidor "lobby-1") leu a mensagem e caiu antes do XACK.
    broker.xreadgroup("lobby", "lobby-1", {STREAM: ">"}, count=10)
    assert broker.xinfo_groups(STREAM)[0]["pending"] == 1

    consumidor.iniciar()

    assert esperar(lambda: ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada")
    assert esperar(lambda: nada_pendente(broker))


def test_o_lobby_nao_le_partida_criada(cliente, broker):
    # Não há grupo do Lobby no stream partida.criada: nada fica pendente para ele (eventos.py).
    broker.xadd("partida.criada", {"dados": json.dumps({"partida_id": "p", "sala_id": None})})

    assert [g["name"] for g in broker.xinfo_groups("partida.criada")] == []
