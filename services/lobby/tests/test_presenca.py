"""Presença: 60 segundos sem GET da sala tiram o jogador (docs/guia-backend-lobby.md, seção 6.5).

Os testes não esperam 60 segundos: mudam direto no banco a hora do último GET (visto_em)."""

from sqlalchemy import text

from app import banco
from tests.conftest import assento_vazio, envelhecer_presenca


def visto_ha_quantos_segundos(sala_id, usuario_id):
    with banco.engine.connect() as conexao:
        return conexao.execute(
            text("SELECT extract(epoch FROM now() - visto_em) FROM assentos WHERE sala_id = :s AND usuario_id = :u"),
            {"s": sala_id, "u": usuario_id},
        ).scalar()


def test_jogador_ausente_ha_mais_de_60_segundos_sai_da_sala(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    envelhecer_presenca(sala["id"], beto.id, 61)

    # Qualquer requisição aplica a regra; aqui, o GET da dona.
    depois = ana.get(f"/salas/{sala['id']}").json()

    assert depois["status"] == "aguardando"
    assert depois["assentos"][1] == assento_vazio(1)
    beto.criar_sala()  # livre para outra sala


def test_dono_ausente_encerra_a_sala(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    envelhecer_presenca(sala["id"], ana.id, 61)

    depois = beto.get(f"/salas/{sala['id']}").json()

    assert depois["status"] == "encerrada"
    assert depois["assentos"][0] == assento_vazio(0)
    assert beto.get("/salas").json() == []


def test_get_atrasado_do_proprio_jogador_nao_salva_o_assento(ana):
    sala = ana.criar_sala()
    envelhecer_presenca(sala["id"], ana.id, 61)

    # A regra roda antes de renovar a presença: quem volta depois do prazo já saiu.
    assert ana.get(f"/salas/{sala['id']}").json()["status"] == "encerrada"


def test_get_da_sala_renova_a_presenca_e_o_da_lista_nao(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    envelhecer_presenca(sala["id"], beto.id, 50)

    beto.get("/salas")
    assert visto_ha_quantos_segundos(sala["id"], beto.id) >= 50

    beto.get(f"/salas/{sala['id']}")
    assert visto_ha_quantos_segundos(sala["id"], beto.id) < 5


def test_59_segundos_ainda_esta_no_prazo(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    envelhecer_presenca(sala["id"], beto.id, 59)

    assert beto.assento_na(ana.get(f"/salas/{sala['id']}").json()) == 1


def test_bots_e_salas_em_partida_nao_entram_na_regra(ana, beto):
    com_bot = ana.criar_sala()
    ana.bot(com_bot, 1)
    em_partida = beto.criar_sala()
    beto.bot(em_partida, 1)
    beto.iniciar(em_partida)
    envelhecer_presenca(em_partida["id"], beto.id, 3600)

    sala_do_bot = ana.get(f"/salas/{com_bot['id']}").json()
    sala_da_partida = ana.get(f"/salas/{em_partida['id']}").json()

    assert sala_do_bot["assentos"][1]["bot"] is True
    assert sala_da_partida["status"] == "em_partida"
    assert beto.assento_na(sala_da_partida) == 0


def test_o_prazo_comeca_quando_o_jogador_senta_ou_troca_de_assento(ana, beto):
    sala = ana.criar_sala("2x2")
    assert visto_ha_quantos_segundos(sala["id"], ana.id) < 5
    beto.entrar(sala, 1)
    assert visto_ha_quantos_segundos(sala["id"], beto.id) < 5
    envelhecer_presenca(sala["id"], beto.id, 30)

    beto.entrar(sala, 3)

    assert visto_ha_quantos_segundos(sala["id"], beto.id) < 5
