"""Truco: pedir, aceitar, correr e aumentar (engine/partida.py)."""

from tests.engine.ajudantes import acao, jogar_em_ordem, nova_partida, recusada

VIRA = "AO"  # manilha 2
MAOS = [["3O", "3E", "4O"], ["4C", "5C", "6C"]]


def pedir(estado, assento):
    return acao(estado, assento, "pedir_truco")


def responder(estado, assento, resposta):
    return acao(estado, assento, "responder_truco", resposta=resposta)


def test_pedido_deixa_o_valor_como_esta_e_fica_pendente():
    estado = pedir(nova_partida(maos=MAOS, vira=VIRA), 0)

    mao = estado["mao_atual"]
    assert mao["valor"] == 1
    assert mao["truco_pendente"] == {"pedido_por_time": "A", "valor_proposto": 3}
    assert mao["vez_assento"] == 0


def test_aceitar_muda_o_valor_e_quem_pediu_nao_pode_pedir_de_novo():
    estado = responder(pedir(nova_partida(maos=MAOS, vira=VIRA), 0), 1, "aceitar")

    mao = estado["mao_atual"]
    assert mao["valor"] == 3
    assert mao["truco_pendente"] is None
    assert mao["ultimo_aumento_time"] == "A"
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")


def test_depois_do_aceite_o_adversario_pede_seis_na_vez_dele():
    estado = responder(pedir(nova_partida(maos=MAOS, vira=VIRA), 0), 1, "aceitar")
    estado = jogar_em_ordem(estado, "4O")  # agora é a vez do assento 1

    estado = pedir(estado, 1)

    assert estado["mao_atual"]["truco_pendente"] == {"pedido_por_time": "B", "valor_proposto": 6}


def test_correr_da_a_quem_pediu_o_valor_de_antes_do_pedido():
    estado = responder(pedir(nova_partida(maos=MAOS, vira=VIRA), 0), 1, "correr")

    assert estado["placar"] == {"A": 1, "B": 0}
    assert estado["mao_atual"]["encerrada"] is True
    assert estado["mao_atual"]["truco_pendente"] is None
    assert estado["mao_atual"]["vez_assento"] is None


def test_aumentar_aceita_o_pedido_e_devolve_um_nivel_acima():
    estado = responder(pedir(nova_partida(maos=MAOS, vira=VIRA), 0), 1, "aumentar")

    mao = estado["mao_atual"]
    assert mao["valor"] == 3
    assert mao["ultimo_aumento_time"] == "A"
    assert mao["truco_pendente"] == {"pedido_por_time": "B", "valor_proposto": 6}

    # Quem pediu o truco corre do seis: o time B ganha os 3 que a mão já valia.
    estado = responder(estado, 0, "correr")
    assert estado["placar"] == {"A": 0, "B": 3}


def test_aumentos_ate_doze_e_depois_nao_ha_mais_pedido():
    estado = pedir(nova_partida(maos=MAOS, vira=VIRA), 0)
    estado = responder(estado, 1, "aumentar")  # 6
    estado = responder(estado, 0, "aumentar")  # 9
    estado = responder(estado, 1, "aumentar")  # 12
    assert estado["mao_atual"]["valor"] == 9
    assert estado["mao_atual"]["truco_pendente"] == {"pedido_por_time": "B", "valor_proposto": 12}
    recusada(estado, 0, {"tipo": "responder_truco", "resposta": "aumentar"}, "acao_invalida")

    estado = responder(estado, 0, "aceitar")
    assert estado["mao_atual"]["valor"] == 12
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")


def test_mao_com_truco_aceito_vale_os_pontos_aceitos():
    estado = responder(pedir(nova_partida(maos=MAOS, vira=VIRA), 0), 1, "aceitar")

    estado = jogar_em_ordem(estado, "3O", "4C", "3E", "5C")

    assert estado["placar"] == {"A": 3, "B": 0}


def test_pedido_fora_da_vez():
    recusada(nova_partida(maos=MAOS, vira=VIRA), 1, {"tipo": "pedir_truco"}, "fora_da_vez")


def test_pedido_repetido_enquanto_o_primeiro_espera_resposta():
    estado = pedir(nova_partida(maos=MAOS, vira=VIRA), 0)
    recusada(estado, 0, {"tipo": "pedir_truco"}, "acao_invalida")


def test_com_truco_pendente_ninguem_joga_carta():
    estado = pedir(nova_partida(maos=MAOS, vira=VIRA), 0)
    recusada(estado, 0, {"tipo": "jogar_carta", "carta": "3O", "coberta": False}, "acao_invalida")


def test_o_proprio_time_nao_responde_ao_pedido():
    estado = pedir(nova_partida(maos=MAOS, vira=VIRA), 0)
    recusada(estado, 0, {"tipo": "responder_truco", "resposta": "aceitar"}, "nao_autorizado")


def test_resposta_sem_pedido_e_resposta_desconhecida():
    estado = nova_partida(maos=MAOS, vira=VIRA)
    recusada(estado, 1, {"tipo": "responder_truco", "resposta": "aceitar"}, "acao_invalida")
    recusada(pedir(estado, 0), 1, {"tipo": "responder_truco", "resposta": "talvez"}, "acao_invalida")


def test_no_2x2_qualquer_um_do_time_responde_e_vale_a_primeira_resposta():
    estado = pedir(nova_partida("2x2"), 0)

    estado = responder(estado, 3, "aceitar")  # o assento 3 é do time B, como o 1

    assert estado["mao_atual"]["valor"] == 3
    recusada(estado, 1, {"tipo": "responder_truco", "resposta": "correr"}, "acao_invalida")
    recusada(estado, 2, {"tipo": "pedir_truco"}, "fora_da_vez")
