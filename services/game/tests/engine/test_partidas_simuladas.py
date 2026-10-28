"""Partidas completas jogadas pelo motor, do começo aos 12 pontos, com jogadores que escolhem
ao acaso entre as ações que valem: cartas (cobertas ou não), truco, respostas e a decisão da
mão de onze. A cada passo, uma ação que não vale também é tentada, e o estado não pode mudar.
"""

import copy
import random

import pytest

from engine import (
    ErroJogada,
    aguardando_proxima_mao,
    aplicar_acao,
    criar_partida,
    iniciar_proxima_mao,
    visao_do_jogador,
)
from engine.partida import numero_da_proxima_rodada
from engine.regras import outro_time
from tests.engine.ajudantes import ASSENTOS_1X1, ASSENTOS_2X2

LIMITE_DE_PASSOS = 5000


def escolher_acao(estado, rng):
    """(assento, mensagem) de uma ação que vale agora, sorteada como faria um jogador."""
    mao = estado["mao_atual"]
    jogadores = estado["jogadores"]
    if mao["aguardando_decisao_mao_de_onze"]:
        time = "A" if estado["placar"]["A"] == 11 else "B"
        quem = rng.choice([j for j in jogadores if j["time"] == time])
        return quem["assento"], {"tipo": "decidir_mao_de_onze", "jogar": rng.random() < 0.7}
    if mao["truco_pendente"]:
        time = outro_time(mao["truco_pendente"]["pedido_por_time"])
        quem = rng.choice([j for j in jogadores if j["time"] == time])
        respostas = ["aceitar", "aceitar", "correr"]
        if mao["truco_pendente"]["valor_proposto"] < 12:
            respostas.append("aumentar")
        return quem["assento"], {"tipo": "responder_truco", "resposta": rng.choice(respostas)}
    da_vez = next(j for j in jogadores if j["assento"] == mao["vez_assento"])
    pode_pedir = mao["tipo"] == "normal" and mao["valor"] < 12 and mao["ultimo_aumento_time"] != da_vez["time"]
    if pode_pedir and rng.random() < 0.1:
        return da_vez["assento"], {"tipo": "pedir_truco"}
    coberta = numero_da_proxima_rodada(mao) > 1 and rng.random() < 0.15
    return da_vez["assento"], {"tipo": "jogar_carta", "carta": rng.choice(da_vez["mao"]), "coberta": coberta}


def tentar_acao_invalida(estado, rng):
    """Uma ação que não vale agora: carta de outro jogador, jogada fora da vez ou resposta sem
    pedido. Tem que ser recusada sem mudar nada."""
    mao = estado["mao_atual"]
    antes = copy.deepcopy(estado)
    fora_da_vez = [j for j in estado["jogadores"] if j["assento"] != mao["vez_assento"]]
    quem = rng.choice(fora_da_vez)
    mensagem = rng.choice(
        [
            {"tipo": "jogar_carta", "carta": rng.choice(quem["mao"]) if quem["mao"] else "4O", "coberta": False},
            {"tipo": "pedir_truco"},
            {"tipo": "jogar_carta", "carta": mao["vira"], "coberta": False},
        ]
    )
    if not mao["truco_pendente"]:
        mensagem = rng.choice([mensagem, {"tipo": "responder_truco", "resposta": "aceitar"}])
    with pytest.raises(ErroJogada):
        aplicar_acao(estado, quem["assento"], mensagem)
    assert estado == antes


def jogar_partida(assentos, semente):
    rng = random.Random(semente)
    estado = criar_partida(f"sim-{semente}", "sala", assentos, rng)
    for _ in range(LIMITE_DE_PASSOS):
        if estado["status"] == "encerrada":
            return estado
        if aguardando_proxima_mao(estado):
            estado = iniciar_proxima_mao(estado, rng)
            conferir_mao_nova(estado)
            continue
        if estado["mao_atual"]["vez_assento"] is not None and not estado["mao_atual"]["aguardando_decisao_mao_de_onze"]:
            tentar_acao_invalida(estado, rng)
        placar_antes = dict(estado["placar"])
        assento, mensagem = escolher_acao(estado, rng)
        estado = aplicar_acao(estado, assento, mensagem)
        assert all(estado["placar"][t] >= placar_antes[t] for t in "AB")
        assert all(0 <= estado["placar"][t] <= 12 for t in "AB")
        for jogador in estado["jogadores"]:
            visao = visao_do_jogador(estado, jogador["assento"])
            assert visao["meu_assento"] == jogador["assento"]
    raise AssertionError("A partida não terminou.")


def conferir_mao_nova(estado):
    mao = estado["mao_atual"]
    cartas = [carta for j in estado["jogadores"] for carta in j["mao"]] + [mao["vira"]]
    assert len(cartas) == len(set(cartas)) == 3 * len(estado["jogadores"]) + 1
    assert mao["rodadas"] == []
    assert mao["valor"] == 1
    esperado = "normal"
    if 11 in estado["placar"].values():
        esperado = "mao_de_ferro" if estado["placar"]["A"] == estado["placar"]["B"] == 11 else "mao_de_onze"
    assert mao["tipo"] == esperado


@pytest.mark.parametrize("semente", range(25))
@pytest.mark.parametrize("assentos", [ASSENTOS_1X1, ASSENTOS_2X2], ids=["1x1", "2x2"])
def test_partida_completa_ate_12_pontos(assentos, semente):
    estado = jogar_partida(assentos, semente)

    vencedor = estado["vencedor_time"]
    assert estado["status"] == "encerrada"
    assert estado["placar"][vencedor] == 12
    assert estado["placar"][outro_time(vencedor)] < 12
    assert estado["mao_atual"]["vez_assento"] is None
    assert visao_do_jogador(estado, 0)["vencedor_time"] == vencedor
