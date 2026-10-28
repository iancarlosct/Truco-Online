"""Cartas: a manilha, a força e os pontos que o bot usa na nota da mão (app/cartas.py)."""

from app.cartas import FORCA_COBERTA, forca, forca_da_jogada, manilha, pontos


def test_manilha_e_o_valor_seguinte_ao_da_vira():
    assert manilha("7O") == "Q"
    assert manilha("KC") == "A"
    assert manilha("3P") == "4"  # depois do 3 volta para o 4


def test_manilhas_pelo_naipe_acima_de_todas_e_comuns_pelo_valor():
    # Vira 4: as manilhas são os 5.
    ordem = ["4O", "QE", "AC", "2P", "3O", "5O", "5E", "5C", "5P"]
    forcas = [forca(carta, "5") for carta in ordem]
    assert forcas == sorted(forcas) and len(set(forcas)) == len(forcas)
    assert forca("KO", "5") == forca("KP", "5")  # fora das manilhas o naipe não conta
    assert forca_da_jogada({"assento": 1, "carta": None, "coberta": True}, "5") == FORCA_COBERTA < forca("4O", "5")


def test_pontos_das_cartas():
    assert [pontos(c, "Q") for c in ["QP", "QO", "3E", "2C", "AO", "KP", "4C"]] == [5, 4, 3, 2, 1, 0, 0]
    assert pontos("3O", "3") == 4  # o 3 que é manilha vale como manilha
