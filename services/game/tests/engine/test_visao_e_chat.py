"""Visão de cada jogador (engine/visao.py), chat e criação da partida."""

import random

import pytest

from engine import AssentosInvalidos, criar_partida, visao_do_jogador
from tests.engine.ajudantes import ASSENTOS_1X1, ASSENTOS_2X2, acao, jogar, jogar_em_ordem, nova_partida, recusada

VIRA = "AO"


def test_visao_tem_exatamente_os_campos_do_protocolo():
    visao = visao_do_jogador(nova_partida(), 1)

    assert set(visao) == {"tipo", "partida_id", "formato", "status", "meu_assento", "jogadores", "placar", "mao_atual", "chat"}
    assert visao["tipo"] == "estado"
    assert visao["meu_assento"] == 1
    assert set(visao["mao_atual"]) == {
        "numero", "pe", "vira", "valor", "tipo", "truco_pendente", "ultimo_aumento_time",
        "aguardando_decisao_mao_de_onze", "rodadas", "vez_assento",
    }


def test_so_o_proprio_jogador_recebe_a_mao_e_todos_recebem_qtd_cartas():
    estado = nova_partida("2x2")

    visao = visao_do_jogador(estado, 2)

    for item in visao["jogadores"]:
        assert item["qtd_cartas"] == 3
        assert "usuario_id" not in item
        assert ("mao" in item) == (item["assento"] == 2)
    assert visao["jogadores"][2]["mao"] == estado["jogadores"][2]["mao"]
    assert visao["jogadores"][3] == {"assento": 3, "nome": "Bot 1", "time": "B", "bot": True, "qtd_cartas": 3}


def test_carta_coberta_vai_sem_o_valor_para_todos_e_em_todas_as_rodadas():
    estado = nova_partida(maos=[["4O", "7O", "QO"], ["3C", "3E", "5C"]], vira=VIRA)
    estado = jogar_em_ordem(estado, "4O", "3C")
    estado = jogar(estado, 1, "3E", coberta=True)
    estado = jogar(estado, 0, "QO")  # fecha a 2ª rodada: a coberta fica numa rodada antiga
    estado = jogar(estado, 0, "7O")

    for assento in (0, 1):
        rodadas = visao_do_jogador(estado, assento)["mao_atual"]["rodadas"]
        assert rodadas[1]["jogadas"][0] == {"assento": 1, "carta": None, "coberta": True}
        assert rodadas[0]["jogadas"][1] == {"assento": 1, "carta": "3C", "coberta": False}
    # O estado guardado continua com a carta de verdade.
    assert estado["mao_atual"]["rodadas"][1]["jogadas"][0]["carta"] == "3E"


def test_vencedor_time_so_aparece_com_a_partida_encerrada():
    estado = nova_partida()
    assert "vencedor_time" not in visao_do_jogador(estado, 0)

    estado["status"] = "encerrada"
    estado["vencedor_time"] = "B"
    assert visao_do_jogador(estado, 0)["vencedor_time"] == "B"


def test_mexer_na_visao_nao_muda_o_estado():
    estado = nova_partida()
    visao = visao_do_jogador(estado, 0)

    visao["jogadores"][0]["mao"].clear()
    visao["placar"]["A"] = 99

    assert len(estado["jogadores"][0]["mao"]) == 3
    assert estado["placar"]["A"] == 0


# ---------- Chat ----------


def test_chat_limpa_as_pontas_corta_em_200_e_guarda_as_50_ultimas():
    estado = nova_partida()
    estado = acao(estado, 0, "chat", texto="  oi  ")
    assert estado["chat"] == [{"de": "Ana", "texto": "oi"}]

    estado = acao(estado, 1, "chat", texto="x" * 300)
    assert estado["chat"][-1]["texto"] == "x" * 200

    for numero in range(60):
        estado = acao(estado, 0, "chat", texto=str(numero))
    assert len(estado["chat"]) == 50
    assert estado["chat"][-1]["texto"] == "59"


@pytest.mark.parametrize("texto", ["", "   ", None, 12])
def test_chat_vazio_ou_fora_do_formato_e_recusado(texto):
    recusada(nova_partida(), 0, {"tipo": "chat", "texto": texto}, "acao_invalida")


# ---------- Criação da partida ----------


def test_partida_criada_com_os_times_pelos_assentos_e_bot_sem_usuario():
    estado = criar_partida("p2", "sala-2", ASSENTOS_2X2, random.Random(3))

    assert estado["formato"] == "2x2"
    assert [j["time"] for j in estado["jogadores"]] == ["A", "B", "A", "B"]
    assert estado["jogadores"][3]["bot"] is True
    assert estado["jogadores"][3]["usuario_id"] is None
    assert estado["sala_id"] == "sala-2"


def test_assentos_fora_de_ordem_sao_ordenados_pelo_numero():
    estado = criar_partida("p3", None, list(reversed(ASSENTOS_1X1)), random.Random(3))
    assert [j["nome"] for j in estado["jogadores"]] == ["Ana", "Beto"]


@pytest.mark.parametrize(
    "assentos",
    [
        ASSENTOS_1X1[:1],
        ASSENTOS_2X2[:3],
        [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "assento": 2}],
        [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "usuario_id": "u-ana"}],
        [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "usuario_id": None}],
        [ASSENTOS_1X1[0], {"assento": 1, "usuario_id": "u-x", "nome": "Bot 1", "bot": True}],
        [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "nome": "   "}],
        [ASSENTOS_1X1[0], {**ASSENTOS_1X1[1], "nome": "x" * 21}],
    ],
)
def test_assentos_invalidos_sao_recusados(assentos):
    with pytest.raises(AssentosInvalidos):
        criar_partida("p4", None, assentos, random.Random(3))
