"""Mão de onze, mão de ferro e fim da partida (engine/partida.py)."""

from engine import aguardando_proxima_mao, visao_do_jogador
from tests.engine.ajudantes import acao, jogar_em_ordem, nova_partida, recusada

VIRA = "AO"  # manilha 2
MAOS = [["3O", "3E", "4O"], ["4C", "5C", "6C"]]  # o assento 0 (time A) vence em duas rodadas


def decidir(estado, assento, jogar):
    return acao(estado, assento, "decidir_mao_de_onze", jogar=jogar)


def test_um_time_com_11_e_mao_de_onze_aguardando_a_decisao_valendo_1():
    mao = nova_partida(placar={"A": 11, "B": 4})["mao_atual"]

    assert mao["tipo"] == "mao_de_onze"
    assert mao["aguardando_decisao_mao_de_onze"] is True
    assert mao["valor"] == 1


def test_antes_da_decisao_ninguem_joga_e_so_o_time_com_11_decide():
    estado = nova_partida(maos=MAOS, vira=VIRA, placar={"A": 11, "B": 4})

    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "3O", "coberta": False}, "acao_invalida")
    recusada(estado, 1, {"tipo": "decidir_mao_de_onze", "jogar": True}, "nao_autorizado")
    recusada(estado, 0, {"tipo": "decidir_mao_de_onze", "jogar": "sim"}, "acao_invalida")


def test_jogar_a_mao_de_onze_vale_3_e_sem_truco():
    estado = decidir(nova_partida(maos=MAOS, vira=VIRA, placar={"A": 11, "B": 4}), 0, True)

    assert estado["mao_atual"]["valor"] == 3
    assert estado["mao_atual"]["aguardando_decisao_mao_de_onze"] is False
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")
    recusada(estado, 0, {"tipo": "decidir_mao_de_onze", "jogar": True}, "acao_invalida")


def test_correr_da_mao_de_onze_da_1_ponto_ao_adversario():
    estado = decidir(nova_partida(maos=MAOS, vira=VIRA, placar={"A": 4, "B": 11}), 1, False)

    assert estado["placar"] == {"A": 5, "B": 11}
    assert aguardando_proxima_mao(estado)


def test_time_com_11_que_perde_a_mao_de_onze_da_3_ao_adversario():
    estado = decidir(nova_partida(maos=MAOS, vira=VIRA, placar={"A": 4, "B": 11}), 1, True)

    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    assert estado["placar"] == {"A": 7, "B": 11}


def test_vencer_a_mao_de_onze_encerra_a_partida_com_o_placar_em_12():
    estado = decidir(nova_partida(maos=MAOS, vira=VIRA, placar={"A": 11, "B": 4}), 0, True)

    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    assert estado["placar"] == {"A": 12, "B": 4}  # 11 + 3, sem passar de 12
    assert estado["status"] == "encerrada"
    assert estado["vencedor_time"] == "A"
    assert estado["mao_atual"]["vez_assento"] is None
    assert not aguardando_proxima_mao(estado)
    # Depois do fim, só o chat vale.
    recusada(estado, 1, {"tipo": "jogar_carta", "carta": "6C", "coberta": False}, "acao_invalida")
    assert acao(estado, 1, "chat", texto="gg")["chat"][-1] == {"de": "Beto", "texto": "gg"}


def test_no_2x2_o_time_com_11_ve_a_mao_do_parceiro_e_o_adversario_nao():
    estado = nova_partida("2x2", placar={"A": 11, "B": 4})
    maos = {j["assento"]: j["mao"] for j in estado["jogadores"]}

    for assento, parceiro in [(0, 2), (2, 0)]:
        visao = visao_do_jogador(estado, assento)
        item = next(j for j in visao["jogadores"] if j["assento"] == parceiro)
        assert item["mao"] == maos[parceiro]
        assert item["qtd_cartas"] == 3
    for assento in (1, 3):
        visao = visao_do_jogador(estado, assento)
        com_mao = [j["assento"] for j in visao["jogadores"] if "mao" in j]
        assert com_mao == [assento]

    # Qualquer um dos dois parceiros decide, e vale a primeira decisão.
    estado = decidir(estado, 2, True)
    recusada(estado, 0, {"tipo": "decidir_mao_de_onze", "jogar": False}, "acao_invalida")


def test_mao_de_ferro_so_marca_o_tipo_e_bloqueia_o_truco():
    estado = nova_partida(maos=MAOS, vira=VIRA, placar={"A": 11, "B": 11})
    mao = estado["mao_atual"]

    assert mao["tipo"] == "mao_de_ferro"
    assert mao["aguardando_decisao_mao_de_onze"] is False
    assert mao["valor"] == 1
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")
    # As cartas continuam à vista para o dono, e a mão vale 1: quem vencer chega a 12.
    assert visao_do_jogador(estado, 0)["jogadores"][0]["mao"] == MAOS[0]

    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    assert estado["placar"] == {"A": 12, "B": 11}
    assert estado["status"] == "encerrada"
    assert estado["vencedor_time"] == "A"
