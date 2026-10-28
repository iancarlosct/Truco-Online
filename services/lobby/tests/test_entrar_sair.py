"""Entrar, trocar de assento e sair (docs/guia-backend-lobby.md, seções 3.5, 3.6, 6.4 e 6.8)."""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.conftest import Jogador, assento_vazio, erro


def test_entrar_senta_o_jogador_com_o_nome_do_token(ana, beto):
    sala = ana.criar_sala("2x2")

    resposta = beto.post(f"/salas/{sala['id']}/entrar", {"assento": 3})

    assert resposta.status_code == 200
    assert resposta.json()["assentos"][3] == {"assento": 3, "usuario_id": beto.id, "nome": "Beto", "bot": False}


def test_trocar_de_assento_vaga_o_antigo_e_o_dono_continua_dono(ana, beto):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 1)

    depois = ana.entrar(sala, 2)  # a dona troca de time

    assert depois["dono_id"] == ana.id
    assert depois["assentos"][0] == assento_vazio(0)
    assert ana.assento_na(depois) == 2
    assert beto.entrar(depois, 3)["assentos"][1] == assento_vazio(1)


def test_pedir_o_proprio_assento_responde_200_sem_mudar_nada(ana):
    sala = ana.criar_sala()

    resposta = ana.post(f"/salas/{sala['id']}/entrar", {"assento": 0})

    assert resposta.status_code == 200
    assert resposta.json() == sala


@pytest.mark.parametrize("corpo", [None, {}, {"assento": "1"}, {"assento": True}, {"assento": 1.5}])
def test_assento_que_nao_e_numero_responde_422(ana, beto, corpo):
    sala = ana.criar_sala()

    resposta = beto.post(f"/salas/{sala['id']}/entrar", corpo)

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": "Dados inválidos."}


def test_corpo_invalido_vem_antes_da_sala_inexistente(beto):
    resposta = beto.post(f"/salas/{uuid.uuid4()}/entrar", {})

    assert resposta.status_code == 422


@pytest.mark.parametrize("assento", [-1, 2, 4])
def test_assento_fora_da_sala_responde_422(ana, beto, assento):
    sala = ana.criar_sala()

    resposta = beto.post(f"/salas/{sala['id']}/entrar", {"assento": assento})

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": "Assento inválido."}


def test_sala_cheia_vem_antes_de_assento_ocupado(ana, beto, caio):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    resposta = caio.post(f"/salas/{sala['id']}/entrar", {"assento": 1})

    assert resposta.status_code == 409
    assert erro(resposta) == "sala_cheia"


def test_assento_ocupado_numa_sala_com_vaga(ana, beto, caio):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 1)

    resposta = caio.post(f"/salas/{sala['id']}/entrar", {"assento": 1})

    assert resposta.status_code == 409
    assert erro(resposta) == "assento_ocupado"
    # Quem já está na sala também não troca para um assento ocupado.
    assert erro(ana.post(f"/salas/{sala['id']}/entrar", {"assento": 1})) == "assento_ocupado"


def test_quem_esta_em_outra_sala_aberta_nao_entra(ana, beto):
    sala = ana.criar_sala()
    beto.criar_sala()

    resposta = beto.post(f"/salas/{sala['id']}/entrar", {"assento": 1})

    assert resposta.status_code == 409
    assert erro(resposta) == "ja_esta_em_outra_sala"


def test_entrar_em_sala_em_partida_responde_409(ana, beto, caio):
    sala = ana.criar_sala("2x2")
    beto.entrar(sala, 1)
    ana.bot(sala, 2)
    ana.bot(sala, 3)
    ana.iniciar(sala)

    # Partida iniciada vem antes de assento inválido e de sala cheia.
    assert erro(caio.post(f"/salas/{sala['id']}/entrar", {"assento": 9})) == "partida_ja_iniciada"


def test_sair_vaga_o_assento(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    resposta = beto.post(f"/salas/{sala['id']}/sair")  # sem corpo, como a tela

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "aguardando"
    assert resposta.json()["assentos"][1] == assento_vazio(1)
    beto.criar_sala()  # livre para outra sala


def test_dono_que_sai_encerra_a_sala(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)

    resposta = ana.post(f"/salas/{sala['id']}/sair")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "encerrada"
    assert resposta.json()["assentos"][0] == assento_vazio(0)
    assert ana.get("/salas").json() == []
    # O GET continua respondendo; as ações respondem 404. Os jogadores ficam livres.
    assert beto.get(f"/salas/{sala['id']}").json()["status"] == "encerrada"
    for acao in ("entrar", "sair", "bot", "iniciar"):
        assert erro(beto.post(f"/salas/{sala['id']}/{acao}", {"assento": 0})) == "sala_nao_encontrada"
    assert ana.delete(f"/salas/{sala['id']}/assentos/1").status_code == 404
    beto.criar_sala()


def test_sair_de_quem_nao_esta_na_sala_responde_409(ana, beto):
    sala = ana.criar_sala()

    resposta = beto.post(f"/salas/{sala['id']}/sair")

    assert resposta.status_code == 409
    assert erro(resposta) == "nao_esta_na_sala"


def test_sair_de_sala_em_partida_responde_409(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    ana.iniciar(sala)

    assert erro(beto.post(f"/salas/{sala['id']}/sair")) == "partida_ja_iniciada"


def test_sair_de_sala_inexistente_responde_404(ana):
    assert ana.post(f"/salas/{uuid.uuid4()}/sair").status_code == 404


def test_dois_jogadores_no_mesmo_assento_ao_mesmo_tempo_so_um_senta(cliente, ana):
    sala = ana.criar_sala("2x2")
    jogadores = [Jogador(cliente, f"Jogador {n}") for n in range(8)]

    with ThreadPoolExecutor(len(jogadores)) as execucao:
        respostas = list(execucao.map(lambda j: j.post(f"/salas/{sala['id']}/entrar", {"assento": 1}), jogadores))

    assert sorted(r.status_code for r in respostas) == [200] + [409] * 7
    assert ana.get(f"/salas/{sala['id']}").json()["assentos"][2] == assento_vazio(2)


def test_duas_abas_criando_sala_ao_mesmo_tempo_criam_uma_so(ana):
    with ThreadPoolExecutor(5) as execucao:
        respostas = list(execucao.map(lambda _: ana.post("/salas", {"formato": "1x1"}), range(5)))

    assert sorted(r.status_code for r in respostas) == [201] + [409] * 4
    assert len(ana.get("/salas").json()) == 1
