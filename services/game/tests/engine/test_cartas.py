"""Baralho, manilha e força das cartas (engine/cartas.py)."""

import random

import pytest

from engine.cartas import VALORES, baralho_embaralhado, forca, manilha


def test_baralho_tem_as_40_cartas_sem_8_9_e_10():
    baralho = baralho_embaralhado(random.Random(1))

    assert len(baralho) == 40
    assert len(set(baralho)) == 40
    assert {carta[:-1] for carta in baralho} == set(VALORES)
    assert {carta[-1] for carta in baralho} == {"P", "C", "E", "O"}


@pytest.mark.parametrize(
    ("vira", "valor_da_manilha"),
    [("4O", "5"), ("7C", "Q"), ("QP", "J"), ("KE", "A"), ("2O", "3"), ("3P", "4")],
)
def test_manilha_e_o_valor_seguinte_ao_da_vira(vira, valor_da_manilha):
    assert manilha(vira) == valor_da_manilha


def test_manilhas_ganham_de_todas_e_o_naipe_desempata():
    # Vira 4: a manilha é o 5. Paus (zap) > copas > espadas > ouros (pica-fumo) > o 3, a
    # carta comum mais forte.
    ordem = ["5P", "5C", "5E", "5O", "3P"]
    forcas = [forca(carta, "5") for carta in ordem]

    assert forcas == sorted(forcas, reverse=True)
    assert len(set(forcas)) == len(forcas)


def test_cartas_comuns_valem_pelo_valor_e_o_naipe_nao_conta():
    assert forca("KC", "5") == forca("KO", "5")
    forcas = [forca(valor + "O", "5") for valor in VALORES if valor != "5"]
    assert forcas == sorted(forcas)
