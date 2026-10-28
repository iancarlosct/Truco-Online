"""Ações do dono: bot e remover assento (docs/guia-backend-lobby.md, seções 3.7, 3.8 e 6.2)."""

import pytest

from tests.conftest import assento_vazio, erro


def test_bot_ocupa_o_assento_sem_usuario_e_com_o_menor_numero_livre(ana):
    sala = ana.criar_sala("2x2")

    sala = ana.bot(sala, 2)
    assert sala["assentos"][2] == {"assento": 2, "usuario_id": None, "nome": "Bot 1", "bot": True}
    sala = ana.bot(sala, 1)
    assert sala["assentos"][1]["nome"] == "Bot 2"

    # Se o "Bot 1" sai, o próximo bot volta a ser "Bot 1".
    ana.delete(f"/salas/{sala['id']}/assentos/2")
    sala = ana.bot(sala, 3)
    assert sala["assentos"][3]["nome"] == "Bot 1"


def test_bot_sem_nivel_vale_padrao(ana):
    sala = ana.criar_sala()

    resposta = ana.post(f"/salas/{sala['id']}/bot", {"assento": 1})

    assert resposta.status_code == 200
    assert resposta.json()["assentos"][1]["bot"] is True


def test_nivel_de_bot_invalido_responde_422(ana):
    sala = ana.criar_sala()

    resposta = ana.post(f"/salas/{sala['id']}/bot", {"assento": 1, "nivel": "dificil"})

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": "Nível de bot inválido."}


@pytest.mark.parametrize(("corpo", "mensagem"), [({"nivel": "padrao"}, "Dados inválidos."), ({"assento": 5}, "Assento inválido.")])
def test_bot_com_assento_faltando_ou_fora_da_sala_responde_422(ana, corpo, mensagem):
    sala = ana.criar_sala()

    resposta = ana.post(f"/salas/{sala['id']}/bot", corpo)

    assert resposta.status_code == 422
    assert resposta.json()["mensagem"] == mensagem


def test_bot_em_assento_ocupado_responde_409(ana, beto):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 1)

    assert erro(ana.post(f"/salas/{sala['id']}/bot", {"assento": 1})) == "assento_ocupado"
    assert erro(ana.post(f"/salas/{sala['id']}/bot", {"assento": 0})) == "assento_ocupado"


def test_so_o_dono_poe_bot_e_isso_vem_antes_de_partida_iniciada(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    resposta = beto.post(f"/salas/{sala['id']}/bot", {"assento": 1})
    assert resposta.status_code == 403
    assert resposta.json() == {"erro": "apenas_dono", "mensagem": "Só o dono da sala pode fazer isso."}

    ana.iniciar(sala)
    assert erro(beto.post(f"/salas/{sala['id']}/bot", {"assento": 1})) == "apenas_dono"
    assert erro(ana.post(f"/salas/{sala['id']}/bot", {"assento": 1})) == "partida_ja_iniciada"


def test_dono_tira_jogador_e_bot(ana, beto):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 1)
    ana.bot(sala, 2)

    resposta = ana.delete(f"/salas/{sala['id']}/assentos/1")
    assert resposta.status_code == 200
    assert resposta.json()["assentos"][1] == assento_vazio(1)
    # O Beto descobre no próximo GET (não está mais sentado) e fica livre para outra sala.
    assert beto.assento_na(beto.get(f"/salas/{sala['id']}").json()) is None
    beto.criar_sala()

    resposta = ana.delete(f"/salas/{sala['id']}/assentos/2")
    assert resposta.json()["assentos"][2] == assento_vazio(2)


def test_tirar_de_assento_vazio_responde_409(ana):
    sala = ana.criar_sala()

    resposta = ana.delete(f"/salas/{sala['id']}/assentos/1")

    assert resposta.status_code == 409
    assert resposta.json() == {"erro": "assento_vazio", "mensagem": "Este assento já está vazio."}


def test_dono_nao_tira_a_si_mesmo(ana):
    sala = ana.criar_sala()

    resposta = ana.delete(f"/salas/{sala['id']}/assentos/0")

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": "Para sair da sala, use o botão Sair da sala."}


@pytest.mark.parametrize(("assento", "mensagem"), [("abc", "Dados inválidos."), ("2", "Assento inválido."), ("-1", "Assento inválido.")])
def test_assento_do_caminho_invalido_responde_422(ana, assento, mensagem):
    sala = ana.criar_sala()

    resposta = ana.delete(f"/salas/{sala['id']}/assentos/{assento}")

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": mensagem}


def test_so_o_dono_tira_e_nao_com_a_partida_iniciada(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    assert erro(beto.delete(f"/salas/{sala['id']}/assentos/0")) == "apenas_dono"
    ana.iniciar(sala)
    assert erro(ana.delete(f"/salas/{sala['id']}/assentos/1")) == "partida_ja_iniciada"
