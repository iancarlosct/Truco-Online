"""Criar, listar e ver uma sala (docs/guia-backend-lobby.md, seções 3.2 a 3.4, 4 e 6.3)."""

import uuid

import pytest

from tests.conftest import assento_vazio, erro


@pytest.mark.parametrize(("formato", "assentos"), [("1x1", 2), ("2x2", 4)])
def test_criar_sala_responde_201_com_o_criador_no_assento_0_como_dono(ana, formato, assentos):
    resposta = ana.post("/salas", {"formato": formato})

    assert resposta.status_code == 201
    sala = resposta.json()
    uuid.UUID(sala["id"])
    assert sala == {
        "id": sala["id"],
        "formato": formato,
        "dono_id": ana.id,
        "status": "aguardando",
        "partida_id": None,
        "assentos": [{"assento": 0, "usuario_id": ana.id, "nome": "Ana", "bot": False}]
        + [assento_vazio(n) for n in range(1, assentos)],
    }


@pytest.mark.parametrize(
    ("corpo", "mensagem"),
    [
        ({"formato": "3x3"}, "Formato de sala inválido."),
        ({"formato": 2}, "Dados inválidos."),  # número no lugar de texto
        ({}, "Dados inválidos."),  # sem o campo
        (None, "Dados inválidos."),  # sem corpo
    ],
)
def test_formato_fora_do_contrato_responde_422(ana, corpo, mensagem):
    resposta = ana.post("/salas", corpo)

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": mensagem}


def test_corpo_que_nao_e_json_responde_422(ana, cliente):
    resposta = cliente.post("/api/lobby/salas", content="oi", headers={**ana.headers, "Content-Type": "application/json"})

    assert resposta.status_code == 422
    assert erro(resposta) == "dados_invalidos"


def test_uma_sala_aberta_por_vez(ana, beto):
    ana.criar_sala()
    sala_do_beto = beto.criar_sala("2x2")

    assert erro(criar := ana.post("/salas", {"formato": "2x2"})) == "ja_esta_em_outra_sala"
    assert criar.status_code == 409
    assert ana.post(f"/salas/{sala_do_beto['id']}/entrar", {"assento": 1}).status_code == 409


def test_sala_em_partida_ou_encerrada_nao_conta_para_a_regra(ana, beto):
    sala = ana.criar_sala()
    beto.entrar(sala, 1)
    ana.iniciar(sala)

    # Quem acabou de começar uma partida pode abrir outra sala, e o dono que sai também.
    outra = ana.criar_sala()
    assert ana.post(f"/salas/{outra['id']}/sair").json()["status"] == "encerrada"
    ana.criar_sala()


def test_lista_tem_so_as_salas_aguardando_da_mais_antiga_para_a_mais_nova(ana, beto, caio, duda):
    assert ana.get("/salas").json() == []

    primeira = ana.criar_sala()
    segunda = beto.criar_sala("2x2")
    cheia = caio.criar_sala()
    duda.entrar(cheia, 1)

    lista = ana.get("/salas")

    assert lista.status_code == 200
    assert [s["id"] for s in lista.json()] == [primeira["id"], segunda["id"], cheia["id"]]  # a cheia também
    assert lista.json()[2]["assentos"][1]["nome"] == "Duda"

    beto.post(f"/salas/{segunda['id']}/sair")  # o dono sai: encerrada
    caio.iniciar(cheia)  # em partida

    assert [s["id"] for s in ana.get("/salas").json()] == [primeira["id"]]


def test_sala_responde_a_quem_nao_esta_nela_link_de_convite(ana, beto):
    sala = ana.criar_sala("2x2")

    resposta = beto.get(f"/salas/{sala['id']}")

    assert resposta.status_code == 200
    assert resposta.json() == sala


def test_sala_encerrada_responde_200_com_o_status_novo(ana, beto):
    sala = ana.criar_sala()
    ana.post(f"/salas/{sala['id']}/sair")

    resposta = beto.get(f"/salas/{sala['id']}")

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "encerrada"
    assert resposta.json()["partida_id"] is None


@pytest.mark.parametrize("sala_id", [str(uuid.uuid4()), "nao-existe"])
def test_sala_que_nunca_existiu_responde_404(ana, sala_id):
    resposta = ana.get(f"/salas/{sala_id}")

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "sala_nao_encontrada", "mensagem": "Sala não encontrada. Ela pode ter sido encerrada."}
