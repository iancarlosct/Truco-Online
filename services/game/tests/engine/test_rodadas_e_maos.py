"""Rodadas, mãos, carta coberta e a pausa entre as mãos (engine/regras.py e engine/partida.py)."""

import random

import pytest

from engine import aguardando_proxima_mao, iniciar_proxima_mao
from engine.regras import resultado_da_mao, resultado_da_rodada
from tests.engine.ajudantes import acao, jogar, jogar_em_ordem, nova_partida, recusada

# Vira "AO": a manilha é o 2. Nenhuma das cartas abaixo é manilha, fora quando indicado.
VIRA = "AO"


# ---------- Regras de rodada e de mão ----------


def test_rodada_vencida_pela_carta_mais_forte_e_quem_a_jogou_abre_a_proxima():
    jogadas = [{"assento": 0, "carta": "KO", "coberta": False}, {"assento": 1, "carta": "3C", "coberta": False}]
    assert resultado_da_rodada(jogadas, "2") == ("B", 1)


def test_manilha_ganha_do_3():
    jogadas = [{"assento": 0, "carta": "2O", "coberta": False}, {"assento": 1, "carta": "3P", "coberta": False}]
    assert resultado_da_rodada(jogadas, "2") == ("A", 0)


def test_cartas_de_mesma_forca_empatam_e_quem_abriu_abre_a_proxima():
    jogadas = [{"assento": 1, "carta": "KO", "coberta": False}, {"assento": 0, "carta": "KP", "coberta": False}]
    assert resultado_da_rodada(jogadas, "2") == ("empate", 1)


def test_carta_coberta_perde_para_qualquer_aberta_e_duas_cobertas_empatam():
    contra_o_4 = [{"assento": 0, "carta": "3P", "coberta": True}, {"assento": 1, "carta": "4O", "coberta": False}]
    duas = [{"assento": 0, "carta": "3P", "coberta": True}, {"assento": 1, "carta": "4O", "coberta": True}]

    assert resultado_da_rodada(contra_o_4, "2") == ("B", 1)
    assert resultado_da_rodada(duas, "2") == ("empate", 0)


def test_no_2x2_vale_a_melhor_carta_do_time():
    jogadas = [
        {"assento": 0, "carta": "4O", "coberta": False},
        {"assento": 1, "carta": "KO", "coberta": False},
        {"assento": 2, "carta": "3C", "coberta": False},  # parceiro do 0
        {"assento": 3, "carta": "AO", "coberta": False},
    ]
    assert resultado_da_rodada(jogadas, "2") == ("A", 2)


@pytest.mark.parametrize(
    ("resultados", "vencedor"),
    [
        (["A"], None),
        (["A", "A"], "A"),
        (["A", "B"], None),
        (["A", "B", "B"], "B"),
        (["A", "empate"], "A"),  # 1ª vencida e 2ª empatada: leva quem fez a 1ª
        (["empate"], None),
        (["empate", "B"], "B"),  # 1ª empatada: leva quem vencer a 2ª
        (["empate", "empate"], None),
        (["empate", "empate", "A"], "A"),
        (["A", "B", "empate"], "A"),  # uma para cada e a 3ª empatada: leva quem fez a 1ª
        (["empate", "empate", "empate"], "empate"),  # ninguém pontua
    ],
)
def test_regra_de_empate_da_mao(resultados, vencedor):
    assert resultado_da_mao(resultados) == vencedor


# ---------- Uma mão inteira pelo motor ----------


def test_primeira_mao_comeca_pelo_assento_0_com_3_cartas_para_cada_e_valendo_1():
    estado = nova_partida()
    mao = estado["mao_atual"]

    assert estado["status"] == "em_andamento"
    assert mao["numero"] == 1
    assert mao["vez_assento"] == 0
    assert mao["valor"] == 1
    assert mao["tipo"] == "normal"
    assert mao["rodadas"] == []
    assert all(len(j["mao"]) == 3 for j in estado["jogadores"])
    todas = [carta for j in estado["jogadores"] for carta in j["mao"]] + [mao["vira"]]
    assert len(set(todas)) == 7


def test_rodada_nova_so_entra_na_lista_com_a_primeira_carta():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)

    estado = jogar_em_ordem(estado, "KO", "3C")

    mao = estado["mao_atual"]
    assert len(mao["rodadas"]) == 1
    assert mao["rodadas"][0]["vencedor_time"] == "B"
    assert mao["rodadas"][0]["vencedor_assento"] == 1
    assert mao["vez_assento"] == 1  # quem venceu a rodada abre a próxima

    estado = jogar(estado, 1, "4C")
    assert len(estado["mao_atual"]["rodadas"]) == 2
    assert estado["mao_atual"]["rodadas"][1] == {
        "jogadas": [{"assento": 1, "carta": "4C", "coberta": False}],
        "vencedor_time": None,
        "vencedor_assento": None,
    }
    assert estado["mao_atual"]["vez_assento"] == 0


def test_mao_vencida_em_duas_rodadas_soma_o_valor_e_para_esperando_a_proxima():
    estado = nova_partida(maos=[["3O", "3E", "4O"], ["4C", "5C", "6C"]], vira=VIRA)

    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    mao = estado["mao_atual"]
    assert estado["placar"] == {"A": 1, "B": 0}
    assert mao["vez_assento"] is None
    assert mao["encerrada"] is True
    assert aguardando_proxima_mao(estado)
    # Durante a pausa, só o chat vale.
    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "4O", "coberta": False}, "acao_invalida")
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")
    assert acao(estado, 1, "chat", texto="boa")["chat"] == [{"de": "Beto", "texto": "boa"}]


def test_proxima_mao_passa_o_pe_adiante_e_volta_a_valer_1():
    estado = nova_partida(maos=[["3O", "3E", "4O"], ["4C", "5C", "6C"]], vira=VIRA)
    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    estado = iniciar_proxima_mao(estado, random.Random(5))

    mao = estado["mao_atual"]
    assert mao["numero"] == 2
    assert mao["pe"] == 0
    assert mao["vez_assento"] == 1
    assert mao["valor"] == 1
    assert mao["rodadas"] == []
    assert mao["encerrada"] is False
    assert estado["placar"] == {"A": 1, "B": 0}
    assert all(len(j["mao"]) == 3 for j in estado["jogadores"])


def test_iniciar_proxima_mao_so_vale_com_a_mao_encerrada():
    with pytest.raises(ValueError):
        iniciar_proxima_mao(nova_partida(), random.Random(1))


def test_primeira_empatada_quem_abriu_abre_a_segunda_e_quem_vencer_leva():
    estado = nova_partida(maos=[["KO", "4O", "5O"], ["KC", "3C", "6C"]], vira=VIRA)

    estado = jogar_em_ordem(estado, "KO", "KC")
    assert estado["mao_atual"]["rodadas"][0]["vencedor_time"] == "empate"
    assert estado["mao_atual"]["rodadas"][0]["vencedor_assento"] is None
    assert estado["mao_atual"]["vez_assento"] == 0

    estado = jogar_em_ordem(estado, "4O", "3C")
    assert estado["placar"] == {"A": 0, "B": 1}
    assert len(estado["mao_atual"]["rodadas"]) == 2


def test_primeira_vencida_e_segunda_empatada_encerra_sem_a_terceira():
    estado = nova_partida(maos=[["3O", "KO", "4O"], ["4C", "KC", "5C"]], vira=VIRA)

    estado = jogar_em_ordem(estado, "3O", "4C", "KO", "KC")

    assert estado["placar"] == {"A": 1, "B": 0}
    assert estado["mao_atual"]["encerrada"] is True
    assert len(estado["jogadores"][0]["mao"]) == 1


def test_tres_rodadas_empatadas_ninguem_pontua():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["KC", "7C", "QC"]], vira=VIRA)

    estado = jogar_em_ordem(estado, "KO", "KC", "7O", "7C", "QO", "QC")

    assert [r["vencedor_time"] for r in estado["mao_atual"]["rodadas"]] == ["empate"] * 3
    assert estado["placar"] == {"A": 0, "B": 0}
    assert aguardando_proxima_mao(estado)


def test_no_2x2_a_vez_anda_pela_numeracao_dos_assentos():
    estado = nova_partida("2x2", maos=[["4O", "5O", "6O"], ["4C", "5C", "6C"], ["3O", "7O", "QO"], ["4E", "5E", "6E"]], vira=VIRA)

    vezes = []
    for carta in ["4O", "4C", "3O", "4E"]:
        vezes.append(estado["mao_atual"]["vez_assento"])
        estado = jogar(estado, vezes[-1], carta)

    assert vezes == [0, 1, 2, 3]
    assert estado["mao_atual"]["rodadas"][0]["vencedor_time"] == "A"
    assert estado["mao_atual"]["rodadas"][0]["vencedor_assento"] == 2  # o 3O do assento 2 venceu
    assert estado["mao_atual"]["vez_assento"] == 2


def test_no_2x2_o_vencedor_da_rodada_e_o_assento_da_carta_mais_forte():
    # Os dois do time A jogam cartas que vencem as do B. Com a vira K, a manilha é o ás: vence o
    # ás do assento 0, não o 3 do parceiro, jogado depois.
    estado = nova_partida("2x2", maos=[["AO", "5O", "6O"], ["4C", "5C", "6C"], ["3O", "7O", "QO"], ["4E", "5E", "6E"]], vira="KO")
    estado = jogar_em_ordem(estado, "AO", "4C", "3O", "4E")
    rodada = estado["mao_atual"]["rodadas"][0]
    assert (rodada["vencedor_time"], rodada["vencedor_assento"]) == ("A", 0)

    # Mesma força nos dois parceiros: vale a carta jogada primeiro, que também abre a próxima.
    estado = nova_partida("2x2", maos=[["KO", "5O", "6O"], ["4C", "5C", "6C"], ["KC", "7O", "QO"], ["4E", "5E", "6E"]], vira=VIRA)
    estado = jogar_em_ordem(estado, "KO", "4C", "KC", "4E")
    assert estado["mao_atual"]["rodadas"][0]["vencedor_assento"] == 0
    assert estado["mao_atual"]["vez_assento"] == 0


# ---------- Jogadas recusadas ----------


def test_jogada_fora_da_vez():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)
    recusada(estado, 1, {"tipo": "jogar_carta", "carta": "3C", "coberta": False}, "fora_da_vez")


def test_clique_duplo_a_segunda_jogada_e_fora_da_vez():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)
    estado = jogar(estado, 0, "KO")
    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "7O", "coberta": False}, "fora_da_vez")


def test_carta_que_nao_esta_na_mao():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)
    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "3C", "coberta": False}, "carta_invalida")


@pytest.mark.parametrize(
    "mensagem",
    [
        None,
        "jogar_carta",
        [],
        {},
        {"tipo": "desconhecido"},
        {"tipo": ["jogar_carta"]},
        {"tipo": "jogar_carta"},  # sem a carta
        {"tipo": "jogar_carta", "carta": 7, "coberta": False},
        {"tipo": "jogar_carta", "carta": "KO", "coberta": "sim"},
    ],
)
def test_mensagem_fora_do_formato_e_acao_invalida(mensagem):
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)
    recusada(estado, 0, mensagem, "acao_invalida")


# ---------- Carta coberta ----------


def test_coberta_so_a_partir_da_segunda_rodada():
    estado = nova_partida(maos=[["KO", "7O", "QO"], ["3C", "4C", "5C"]], vira=VIRA)
    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "KO", "coberta": True}, "carta_invalida")

    estado = jogar_em_ordem(estado, "KO", "3C")
    estado = jogar(estado, 1, "4C", coberta=True)

    assert estado["mao_atual"]["rodadas"][1]["jogadas"] == [{"assento": 1, "carta": "4C", "coberta": True}]


def test_coberta_nao_vale_nada_na_rodada():
    estado = nova_partida(maos=[["4O", "7O", "QO"], ["3C", "3E", "5C"]], vira=VIRA)
    estado = jogar_em_ordem(estado, "4O", "3C")  # B vence a 1ª e abre a 2ª
    estado = jogar(estado, 1, "3E", coberta=True)
    estado = jogar(estado, 0, "QO")

    assert estado["mao_atual"]["rodadas"][1]["vencedor_time"] == "A"
