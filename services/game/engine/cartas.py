"""Cartas do truco paulista: o baralho de 40 cartas, a manilha e a força de cada carta.

Uma carta é um texto com o valor seguido do naipe, em maiúsculas: "7O" é o 7 de ouros e "QC" a
dama de copas (docs/guia-backend-mesa.md, seção 4.2). É o mesmo código que a tela usa para
achar a imagem da carta.
"""

import random

# Valores, do mais fraco para o mais forte. O baralho não tem 8, 9 e 10.
VALORES = ("4", "5", "6", "7", "Q", "J", "K", "A", "2", "3")

# Naipes, do mais fraco para o mais forte. O naipe só desempata as manilhas:
# paus (o zap) > copas > espadas > ouros (o pica-fumo).
NAIPES = ("O", "E", "C", "P")

# Força de uma carta jogada coberta: menor que a de qualquer carta aberta.
FORCA_COBERTA = -1


def baralho_embaralhado(rng: random.Random) -> list[str]:
    """As 40 cartas, em ordem aleatória."""
    cartas = [valor + naipe for valor in VALORES for naipe in NAIPES]
    rng.shuffle(cartas)
    return cartas


def manilha(vira: str) -> str:
    """Valor da manilha: o seguinte ao da vira, na ordem de VALORES. Depois do 3 volta para o 4."""
    return VALORES[(VALORES.index(vira[:-1]) + 1) % len(VALORES)]


def forca(carta: str, valor_da_manilha: str) -> int:
    """Força da carta numa mão com esta manilha: quanto maior, mais forte.

    As quatro manilhas ficam acima de todas as outras cartas e não empatam entre si (vale o
    naipe). Fora das manilhas o naipe não conta: dois reis, por exemplo, têm a mesma força.
    """
    valor, naipe = carta[:-1], carta[-1]
    if valor == valor_da_manilha:
        return len(VALORES) + NAIPES.index(naipe)
    return VALORES.index(valor)
