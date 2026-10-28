"""POST /interno/partidas, eventos no broker, /saude e erros HTTP."""

import uuid

import pytest
import redis

from tests.app.conftest import ANA, ASSENTOS_1X1, BETO, criar_partida, eventos_do_stream, ler_partida


def test_criar_partida_responde_201_com_o_id_e_a_primeira_mao_distribuida(cliente, banco):
    resposta = cliente.post("/interno/partidas", json={"sala_id": "sala-1", "assentos": ASSENTOS_1X1})

    assert resposta.status_code == 201
    assert set(resposta.json()) == {"partida_id"}
    partida_id = resposta.json()["partida_id"]
    uuid.UUID(partida_id)

    estado = ler_partida(banco, partida_id)
    assert estado["formato"] == "1x1"
    assert estado["sala_id"] == "sala-1"
    assert [j["usuario_id"] for j in estado["jogadores"]] == [ANA, BETO]
    assert estado["mao_atual"]["numero"] == 1
    assert all(len(j["mao"]) == 3 for j in estado["jogadores"])
    assert banco.ttl(f"partida:{partida_id}") > 0  # vence se ficar parada (config.VALIDADE_DA_PARTIDA)


def test_criar_partida_publica_partida_criada(cliente, broker):
    partida_id = criar_partida(cliente)

    [evento] = eventos_do_stream(broker, "partida.criada")

    assert evento["partida_id"] == partida_id
    assert evento["sala_id"] == "sala-1"
    assert evento["formato"] == "1x1"
    assert evento["criada_em"].endswith("+00:00")


def test_partida_2x2_com_bots(cliente, banco):
    assentos = [
        ASSENTOS_1X1[0],
        {"assento": 1, "usuario_id": None, "nome": "Bot 1", "bot": True},
        {"assento": 2, "usuario_id": BETO, "nome": "Beto", "bot": False},
        {"assento": 3, "usuario_id": None, "nome": "Bot 2", "bot": True},
    ]

    estado = ler_partida(banco, criar_partida(cliente, assentos))

    assert estado["formato"] == "2x2"
    assert [j["bot"] for j in estado["jogadores"]] == [False, True, False, True]


@pytest.mark.parametrize(
    ("corpo", "mensagem"),
    [
        ({"assentos": ASSENTOS_1X1[:1]}, "A partida precisa de 2 assentos (1x1) ou 4 (2x2)."),
        (
            {"assentos": [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "assento": 3}]},
            "Os assentos precisam ser numerados de 0 a 1, sem repetir.",
        ),
        (
            {"assentos": [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "usuario_id": ANA}]},
            "O mesmo usuário não pode ocupar dois assentos.",
        ),
        ({"sala_id": "s"}, "Dados inválidos. Confira os campos e tente de novo."),
        ({"assentos": [{"assento": "zero"}]}, "Dados inválidos. Confira os campos e tente de novo."),
    ],
)
def test_corpo_invalido_responde_422_no_formato_do_contrato(cliente, broker, corpo, mensagem):
    resposta = cliente.post("/interno/partidas", json=corpo)

    assert resposta.status_code == 422
    assert resposta.json() == {"erro": "dados_invalidos", "mensagem": mensagem}
    assert broker.xlen("partida.criada") == 0


def test_com_o_broker_fora_do_ar_o_evento_espera_na_fila_e_sai_depois(cliente, banco, broker):
    entregador = cliente.app.state.partidas.entregador
    broker_de_verdade = entregador.broker

    class BrokerForaDoAr:
        async def xadd(self, *args, **kwargs):
            raise redis.ConnectionError("broker fora do ar (simulado)")

    entregador.broker = BrokerForaDoAr()
    try:
        primeira = criar_partida(cliente)
        assert eventos_do_stream(broker, "partida.criada", espera=0.3) == []
        assert banco.llen("eventos:pendentes") == 1
    finally:
        entregador.broker = broker_de_verdade

    # A próxima partida acorda o Entregador, que entrega a fila inteira, na ordem.
    segunda = criar_partida(cliente)
    eventos = eventos_do_stream(broker, "partida.criada", quantidade=2)
    assert [e["partida_id"] for e in eventos] == [primeira, segunda]
    assert banco.llen("eventos:pendentes") == 0


def test_saude_responde_ok(cliente):
    resposta = cliente.get("/saude")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_rota_inexistente_responde_no_formato_do_contrato(cliente):
    resposta = cliente.get("/interno/nao-existe")

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "nao_encontrado", "mensagem": "Endereço não encontrado."}
