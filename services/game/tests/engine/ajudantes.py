"""Ajudantes dos testes do motor: partidas com as cartas escolhidas e atalhos para as ações."""

import copy
import random

import pytest

from engine import ErroJogada, aplicar_acao, criar_partida, iniciar_proxima_mao

ASSENTOS_1X1 = [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": False},
    {"assento": 1, "usuario_id": "u-beto", "nome": "Beto", "bot": False},
]
ASSENTOS_2X2 = [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": False},
    {"assento": 1, "usuario_id": "u-beto", "nome": "Beto", "bot": False},
    {"assento": 2, "usuario_id": "u-caio", "nome": "Caio", "bot": False},
    {"assento": 3, "usuario_id": None, "nome": "Bot 1", "bot": True},
]


def nova_partida(formato="1x1", maos=None, vira=None, placar=None, semente=0):
    """Partida no começo de uma mão, com o assento 0 jogando primeiro. Com placar, distribui a
    mão a partir dele (o tipo da mão sai do placar: 11 é mão de onze, 11 a 11 é mão de ferro).
    Com maos e vira, troca as cartas sorteadas pelas escolhidas: maos tem as cartas de cada
    assento, na ordem dos assentos."""
    rng = random.Random(semente)
    estado = criar_partida("p1", "sala-1", ASSENTOS_1X1 if formato == "1x1" else ASSENTOS_2X2, rng)
    if placar:
        estado["placar"] = dict(placar)
        estado["mao_atual"]["encerrada"] = True
        estado = iniciar_proxima_mao(estado, rng)
        estado["mao_atual"]["pe"] = len(estado["jogadores"]) - 1
        estado["mao_atual"]["vez_assento"] = 0
    if maos:
        for jogador, cartas in zip(estado["jogadores"], maos):
            jogador["mao"] = list(cartas)
    if vira:
        estado["mao_atual"]["vira"] = vira
    return estado


def acao(estado, assento, tipo, **campos):
    return aplicar_acao(estado, assento, {"tipo": tipo, **campos})


def jogar(estado, assento, carta, coberta=False):
    return acao(estado, assento, "jogar_carta", carta=carta, coberta=coberta)


def jogar_em_ordem(estado, *cartas):
    """Joga as cartas na ordem, cada uma pelo assento que tem a vez."""
    for carta in cartas:
        estado = jogar(estado, estado["mao_atual"]["vez_assento"], carta)
    return estado


def recusada(estado, assento, mensagem, codigo):
    """Confere que a ação é recusada com o código esperado e sem mudar o estado."""
    antes = copy.deepcopy(estado)
    with pytest.raises(ErroJogada) as erro:
        aplicar_acao(estado, assento, mensagem)
    assert erro.value.codigo == codigo
    assert erro.value.mensagem
    assert estado == antes
    return erro.value
