"""Estratégia do bot (app/estrategia.py): uma decisão por situação, sempre uma jogada válida.

Nas cartas, a vira padrão dos ajudantes é o 4 de ouros: as manilhas são os 5."""

import random

from app import cartas, estrategia
from app.estrategia import decidir
from tests.estrategia.ajudantes import SEM_BLEFE, SEMPRE_BLEFA, estado, rodada


def carta(estado_):
    """A carta que o bot escolhe neste estado, como (carta, coberta), sem passar pelo truco."""
    acao = estrategia.escolher_carta(estado_)
    return acao["carta"], acao["coberta"]


def tipo(estado_, rng=SEM_BLEFE):
    """O tipo da mensagem que o bot envia neste estado."""
    return decidir(estado_, rng)["tipo"]


# ---------- Quando o bot age ----------


def test_so_age_quando_cabe_a_ele():
    mao = ["4E", "7C", "KO"]
    assert decidir(estado(mao, vez=1), SEM_BLEFE) is None  # vez do adversário
    assert decidir(estado(mao, vez=None), SEM_BLEFE) is None  # pausa entre as mãos
    assert decidir(estado(mao, status="encerrada"), SEM_BLEFE) is None
    assert decidir(estado(mao, truco="A"), SEM_BLEFE) is None  # o próprio time pediu: espera
    # Mão de onze do adversário: ele decide, e ninguém joga carta até lá.
    assert decidir(estado(mao, placar=(5, 11), tipo="mao_de_onze", aguardando=True), SEM_BLEFE) is None
    # A vez é dele e não há nada pendente: joga uma carta da mão.
    assert decidir(estado(mao), SEM_BLEFE)["carta"] in mao


def test_jogada_sempre_valida_em_situacoes_sorteadas():
    """Situações sorteadas (rodada, cartas na mesa, aposta), com as condições do Game para cada
    mensagem (guia da mesa, seções 5.1 e 5.2)."""
    rng = random.Random(2026)
    baralho = [v + n for v in cartas.VALORES for n in cartas.NAIPES]
    for _ in range(300):
        formato = rng.choice(["1x1", "2x2"])
        quantidade = 2 if formato == "1x1" else 4
        meu = rng.randrange(quantidade)
        sorteadas = rng.sample(baralho, 8)
        numero = rng.randint(1, 3)
        anteriores = []
        while len(anteriores) < numero - 1:
            vencedor = rng.choice(["A", "B", "empate"])
            if estrategia.vencedor_da_mao([r["vencedor_time"] for r in anteriores] + [vencedor]) is None:
                anteriores.append(rodada(vencedor=vencedor))
        # Quem jogou antes do bot na rodada em andamento.
        na_mesa = rng.randrange(quantidade)
        jogadas = [((meu - na_mesa + i) % quantidade, None if numero > 1 and rng.random() < 0.3 else sorteadas[3 + i])
                   for i in range(na_mesa)]
        rodadas = anteriores + ([rodada(*jogadas)] if jogadas else [])
        valor = rng.choice([1, 3, 6, 9, 12])
        e = estado(sorteadas[: 4 - numero], vira=sorteadas[7], meu=meu, formato=formato, rodadas=rodadas,
                   valor=valor, tipo=rng.choice(["normal", "normal", "mao_de_ferro"]),
                   ultimo=rng.choice([None, "A", "B"]) if valor > 1 else None, bots=range(quantidade))
        acao = decidir(e, random.Random(rng.random()))
        if acao["tipo"] == "pedir_truco":
            assert estrategia.pode_pedir_truco(e), e
        else:
            assert acao["tipo"] == "jogar_carta"
            assert acao["carta"] in sorteadas[: 4 - numero]
            assert acao["coberta"] is False or numero >= 2


# ---------- Cartas ----------


def test_joga_a_menor_carta_que_vence_a_mesa_e_usa_as_manilhas():
    # A dama do adversário perde para o rei: o bot não gasta o 2.
    assert carta(estado(["2O", "AE", "KC"], rodadas=[rodada((1, "QP"))], meu=0)) == ("KC", False)
    # Contra o 3, só a manilha vence. Com a vira 3, as manilhas são os 4.
    assert carta(estado(["4E", "3P", "KO"], vira="3C", rodadas=[rodada((1, "3O"))])) == ("4E", False)
    # A mesma mão com a vira 7 (manilha Q): nada vence o 3 (3 com 3 empata), e ele descarta o 4.
    assert carta(estado(["4E", "3P", "KO"], vira="7C", rodadas=[rodada((1, "3O"))])) == ("4E", False)
    # Entre manilhas vale o naipe: contra a de copas, só o zap (paus) vence.
    assert carta(estado(["5E", "5P", "3O"], rodadas=[rodada((1, "5C"))])) == ("5P", False)


def test_descarta_a_mais_fraca_quando_o_parceiro_ja_esta_ganhando():
    # 2x2, bot no assento 2: o parceiro (0) jogou um 3, e o adversário (1), um rei.
    e = estado(["5P", "AE", "6C"], meu=2, formato="2x2", rodadas=[rodada((0, "3P"), (1, "KC"))])
    assert carta(e) == ("6C", False)


def test_abrindo_a_rodada():
    mao = ["6O", "2E", "AC"]
    assert carta(estado(mao)) == ("2E", False)  # primeira rodada: a mais forte
    ganhou = [rodada((0, "3E"), (1, "4C"), vencedor="A")]
    assert carta(estado(mao[:2], rodadas=ganhou)) == ("6O", False)  # já ganhou uma: guarda a forte
    empatou = [rodada((0, "3E"), (1, "3C"), vencedor="empate")]
    assert carta(estado(mao[:2], rodadas=empatou)) == ("2E", False)  # esta rodada decide: a forte


def test_carta_coberta_so_a_partir_da_segunda_rodada():
    # Nada vence o zap do adversário: na primeira rodada o descarte vai aberto...
    primeira = estado(["6O", "7E", "QC"], rodadas=[rodada((1, "5P"))])
    assert carta(primeira) == ("6O", False)
    # ...e na segunda, coberto.
    perdeu = rodada((1, "3E"), (0, "4C"), vencedor="B")
    segunda = estado(["6O", "7E"], rodadas=[perdeu, rodada((1, "5P"))])
    assert carta(segunda) == ("6O", True)
    # Depois de uma recusa do Game, a jogada segura vai sempre aberta.
    assert decidir(segunda, SEM_BLEFE, seguro=True)["coberta"] is False


# ---------- Truco ----------


def test_pede_truco_com_mao_forte_e_nao_com_mao_fraca():
    assert decidir(estado(["5P", "3E", "4C"]), SEM_BLEFE) == {"tipo": "pedir_truco"}  # zap + 3 = 8
    assert decidir(estado(["5O", "2E", "4C"]), SEM_BLEFE) == {"tipo": "pedir_truco"}  # manilha + 2 = 6
    assert tipo(estado(["3O", "AE", "4C"])) == "jogar_carta"  # 3 + ás = 4
    # Já ganhou uma rodada e tem um 3: 3 + 3 = 6.
    ganhou = [rodada((0, "2E"), (1, "4C"), vencedor="A")]
    assert decidir(estado(["3O", "6C"], rodadas=ganhou), SEM_BLEFE) == {"tipo": "pedir_truco"}
    # Para pedir seis (a mão já vale 3), só com a mão muito forte.
    assert tipo(estado(["5O", "2E", "4C"], valor=3, ultimo="B")) == "jogar_carta"
    assert decidir(estado(["5P", "3E", "4C"], valor=3, ultimo="B"), SEM_BLEFE) == {"tipo": "pedir_truco"}


def test_pede_truco_quando_ja_sabe_que_leva_a_mao():
    # A primeira empatou, então a segunda decide. O bot é o último a jogá-la, e o rei dele vence a
    # dama da mesa: a mão é dele, mesmo com uma nota baixa.
    empatou = rodada((1, "7E"), (0, "7C"), vencedor="empate")
    e = estado(["KO", "6E"], rodadas=[empatou, rodada((1, "QP"))])
    assert estrategia.nota_da_mao(e) == estrategia.NOTA_GARANTIDA
    assert decidir(e, SEM_BLEFE) == {"tipo": "pedir_truco"}


def test_blefe_so_na_primeira_carta_e_com_a_chance_sorteada():
    fraca = ["4E", "7C", "KO"]
    assert decidir(estado(fraca), SEMPRE_BLEFA) == {"tipo": "pedir_truco"}
    assert tipo(estado(fraca)) == "jogar_carta"
    perdeu = rodada((0, "4C"), (1, "3E"), vencedor="B")
    assert tipo(estado(fraca[:2], rodadas=[perdeu, rodada((1, "6O"))]), SEMPRE_BLEFA) == "jogar_carta"
    # Com a mesma semente, o bot toma as mesmas decisões.
    sorteio = [tipo(estado(fraca), random.Random(semente)) for semente in range(40)]
    assert sorteio == [tipo(estado(fraca), random.Random(semente)) for semente in range(40)]
    assert "pedir_truco" in sorteio and "jogar_carta" in sorteio


def test_nao_pede_truco_quando_o_game_nao_deixa():
    forte = ["5P", "5C", "3E"]
    assert tipo(estado(forte, valor=3, ultimo="A"), SEMPRE_BLEFA) == "jogar_carta"  # o time dele fez o último aumento
    assert tipo(estado(forte, valor=12, ultimo="B"), SEMPRE_BLEFA) == "jogar_carta"  # já vale 12
    assert tipo(estado(forte, placar=(11, 11), tipo="mao_de_ferro"), SEMPRE_BLEFA) == "jogar_carta"
    assert tipo(estado(forte, placar=(11, 4), tipo="mao_de_onze"), SEMPRE_BLEFA) == "jogar_carta"


def test_respostas_ao_truco():
    assert decidir(estado(["5P", "3E", "4C"], vez=1, truco="B"), SEM_BLEFE)["resposta"] == "aumentar"
    # Na aposta de 12 não há como aumentar: aceita.
    doze = estado(["5P", "3E", "4C"], vez=1, truco="B", valor=9, ultimo="A")
    assert decidir(doze, SEM_BLEFE)["resposta"] == "aceitar"
    assert decidir(estado(["3O", "6E", "4C"], vez=1, truco="B"), SEM_BLEFE)["resposta"] == "aceitar"
    assert decidir(estado(["KO", "6E", "4C"], vez=1, truco="B"), SEM_BLEFE)["resposta"] == "correr"
    # Perdeu a primeira rodada: um 3 sozinho já não basta.
    perdeu = [rodada((1, "2E"), (0, "4C"), vencedor="B")]
    assert decidir(estado(["3O", "6E"], vez=1, truco="B", rodadas=perdeu), SEM_BLEFE)["resposta"] == "correr"


# ---------- Mão de onze ----------


def test_mao_de_onze_pela_forca_da_mao():
    def decisao(mao, **extra):
        e = estado(mao, placar=(11, 7), tipo="mao_de_onze", aguardando=True, **extra)
        return decidir(e, SEM_BLEFE)

    assert decisao(["5O", "AE", "6C"]) == {"tipo": "decidir_mao_de_onze", "jogar": True}  # 4 + 1
    assert decisao(["3O", "AE", "6C"]) == {"tipo": "decidir_mao_de_onze", "jogar": False}  # 3 + 1
    # No 2x2 conta também a mão do parceiro (os dois bots, e decide o de menor assento).
    com_parceiro = dict(formato="2x2", bots={0, 2}, mao_parceiro=["5P", "2O", "7E"])
    assert decisao(["3O", "AE", "6C"], **com_parceiro)["jogar"] is True  # zap + 3 + 2


# ---------- O time no 2x2 ----------


def test_com_parceiro_humano_o_bot_deixa_o_truco_e_a_mao_de_onze_para_ele():
    forte = ["5P", "3E", "4C"]
    # Bot no assento 2, parceiro humano no 0.
    assert decidir(estado(forte, meu=2, vez=1, formato="2x2", truco="B", bots={2}), SEM_BLEFE) is None
    onze = estado(forte, meu=2, formato="2x2", bots={2}, placar=(11, 3), tipo="mao_de_onze", aguardando=True)
    assert decidir(onze, SEM_BLEFE) is None
    # Na própria vez, o bot joga normalmente: pede truco com a mão forte.
    assert decidir(estado(forte, meu=2, formato="2x2", bots={2}), SEM_BLEFE) == {"tipo": "pedir_truco"}


def test_com_parceiro_bot_responde_so_o_de_menor_assento():
    forte = ["5P", "3E", "4C"]
    # Bots nos assentos 1 e 3 (time B); o time A pediu truco.
    do_1 = estado(forte, meu=1, vez=0, formato="2x2", truco="A", bots={1, 3})
    do_3 = estado(forte, meu=3, vez=0, formato="2x2", truco="A", bots={1, 3})
    assert decidir(do_1, SEM_BLEFE) == {"tipo": "responder_truco", "resposta": "aumentar"}
    assert decidir(do_3, SEM_BLEFE) is None
