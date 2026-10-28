"""Cartas do truco paulista, do ponto de vista do bot: a manilha e a força de cada carta.

O serviço de Bots não importa nada do Game (nem o motor de regras): este arquivo é a cópia
própria do que o bot precisa saber sobre as cartas, escrita a partir das regras do guia da mesa
(docs/guia-backend-mesa.md, seções 4.2 e 10.2).

Uma carta é um texto com o valor seguido do naipe, em maiúsculas: "7O" é o 7 de ouros e "QC" a
dama de copas. É o mesmo código que chega na mensagem "estado".
"""

# Valores, do mais fraco para o mais forte. O baralho não tem 8, 9 e 10.
VALORES = ("4", "5", "6", "7", "Q", "J", "K", "A", "2", "3")

# Naipes, do mais fraco para o mais forte. O naipe só conta entre as manilhas:
# paus (o zap) > copas > espadas > ouros.
NAIPES = ("O", "E", "C", "P")

# Força de uma carta jogada coberta: perde para qualquer carta aberta.
FORCA_COBERTA = -1


def manilha(vira: str) -> str:
    """Valor da manilha: o seguinte ao da vira, na ordem de VALORES. Depois do 3 volta para o 4.
    Exemplo: com a vira "7O", as manilhas são as quatro damas (Q)."""
    return VALORES[(VALORES.index(vira[:-1]) + 1) % len(VALORES)]


def eh_manilha(carta: str, valor_da_manilha: str) -> bool:
    return carta[:-1] == valor_da_manilha


def forca(carta: str, valor_da_manilha: str) -> int:
    """Força da carta nesta mão: quanto maior, mais forte. Vai de 0 (o 4) a 13 (o zap).

    - Cartas comuns: a posição do valor em VALORES (4 = 0, 5 = 1, ..., 3 = 9). O naipe não conta:
      dois reis têm a mesma força e empatam.
    - Manilhas: acima de todas as comuns, de 10 (ouros) a 13 (paus, o zap). Duas manilhas nunca
      empatam, porque cada naipe tem uma força.
    """
    valor, naipe = carta[:-1], carta[-1]
    if valor == valor_da_manilha:
        return len(VALORES) + NAIPES.index(naipe)
    return VALORES.index(valor)


def forca_da_jogada(jogada: dict, valor_da_manilha: str) -> int:
    """Força de uma carta que está na mesa, como vem no "estado": {"assento", "carta", "coberta"}.
    A coberta chega com "carta": null e não vale nada."""
    if jogada.get("coberta") or not jogada.get("carta"):
        return FORCA_COBERTA
    return forca(jogada["carta"], valor_da_manilha)


def pontos(carta: str, valor_da_manilha: str) -> int:
    """Quanto a carta ajuda a ganhar uma rodada, numa escala simples que o bot usa para dar uma
    nota à mão (estrategia.nota_da_mao):

        zap (manilha de paus)          5
        outra manilha                  4
        3                              3
        2                              2
        ás (A)                         1
        o resto (4, 5, 6, 7, Q, J, K)  0

    Só as cartas altas contam: com um rei ou menos, ganhar a rodada depende de sorte.
    """
    if eh_manilha(carta, valor_da_manilha):
        return 5 if carta[-1] == "P" else 4
    return {"3": 3, "2": 2, "A": 1}.get(carta[:-1], 0)
