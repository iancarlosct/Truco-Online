"""Partidas de verdade, do começo ao fim: a sala é criada no Lobby, e quem joga pelos bots é o
serviço bots que está no ar (explicação em conftest.py). A pessoa de teste joga pela mesa do
Game, sem atraso; os bots, com o atraso de 1 a 2 segundos de cada ação, por isso cada partida
leva um ou dois minutos."""

import asyncio

from tests.servico.conftest import (
    LOBBY_URL, PESSOA_ID, PESSOA_NOME, RANKING_URL, esperar, pedir, pendentes,
)
from tests.servico.pessoa import Pessoa, token_de_usuario

TOKEN = token_de_usuario(PESSOA_ID, PESSOA_NOME)


def lobby(metodo: str, caminho: str, corpo: dict | None = None) -> dict:
    status, resposta = pedir(metodo, f"{LOBBY_URL}/api/lobby{caminho}", TOKEN, corpo)
    assert 200 <= status < 300, (status, resposta)
    return resposta


def iniciar_sala(formato: str, assentos_de_bot: list[int]) -> str:
    """Cria a sala (a pessoa fica no assento 0), põe os bots, inicia e devolve o partida_id."""
    # Se um teste anterior parou no meio, a pessoa pode ter ficado sentada numa sala aberta.
    for sala in lobby("GET", "/salas"):
        if any(a["usuario_id"] == PESSOA_ID for a in sala["assentos"]):
            lobby("POST", f"/salas/{sala['id']}/sair")
    sala = lobby("POST", "/salas", {"formato": formato})
    for assento in assentos_de_bot:
        lobby("POST", f"/salas/{sala['id']}/bot", {"assento": assento, "nivel": "padrao"})
    return lobby("POST", f"/salas/{sala['id']}/iniciar")["partida_id"]


def jogar_ate_o_fim(partida_id: str, limite: float) -> Pessoa:
    async def jogar():
        async with Pessoa(partida_id, PESSOA_ID, PESSOA_NOME) as pessoa:
            await pessoa.esperar(lambda p: p.estado["status"] == "encerrada", limite, "a partida terminar")
            return pessoa

    return asyncio.run(jogar())


def test_partida_1x1_de_uma_pessoa_contra_um_bot(sistema_no_ar, broker_do_sistema):
    partida_id = iniciar_sala("1x1", [1])

    pessoa = jogar_ate_o_fim(partida_id, 300)

    assert pessoa.estado["vencedor_time"] in ("A", "B")
    assert 12 in pessoa.estado["placar"].values()
    assert pessoa.jogadas_de(1) >= 1 and pessoa.erros == []
    # No fim, o bot sai da mesa e confirma o pedido no broker.
    esperar(lambda: not pendentes(broker_do_sistema, partida_id), 15, "o bot confirmar o pedido")
    # A partida entra no ranking da pessoa; o bot fica só no histórico da partida.
    def registrada():
        status, jogador = pedir("GET", f"{RANKING_URL}/api/ranking/jogadores/{PESSOA_ID}", TOKEN)
        partidas = jogador.get("ultimas_partidas", []) if status == 200 else []
        return next((p for p in partidas if p["partida_id"] == partida_id), None)

    partida = esperar(registrada, 15, "o Ranking registrar a partida")
    assert partida["times"]["B"] == [{"assento": 1, "usuario_id": None, "nome": "Bot 1", "bot": True}]
    _status, ranking = pedir("GET", f"{RANKING_URL}/api/ranking", TOKEN)
    assert any(linha["usuario_id"] == PESSOA_ID for linha in ranking)
    assert all(linha["usuario_id"] for linha in ranking)  # nenhuma linha de bot


def test_partida_2x2_de_uma_pessoa_com_tres_bots(sistema_no_ar, broker_do_sistema):
    # A pessoa no assento 0 e um bot de parceiro no 2: o bot deixa o truco e a mão de onze para
    # ela. No time B, dois bots: responde o do assento 1.
    partida_id = iniciar_sala("2x2", [1, 2, 3])

    pessoa = jogar_ate_o_fim(partida_id, 420)

    assert pessoa.estado["vencedor_time"] in ("A", "B")
    assert all(pessoa.jogadas_de(assento) >= 1 for assento in (1, 2, 3))
    assert pessoa.erros == []
    esperar(lambda: not pendentes(broker_do_sistema, partida_id), 15, "os bots confirmarem os pedidos")
