"""O serviço reiniciando no meio de uma partida e o mesmo pedido de bot chegando mais de uma vez.

Aqui o Gerenciador roda dentro do teste, lendo o broker de teste (banco lógico 4), e as partidas
são criadas direto no Game, com o Game de verdade (explicação em conftest.py)."""

import asyncio
import logging

from fastapi.testclient import TestClient

from app import eventos
from app.main import app
from tests.servico.conftest import PESSOA_ID, PESSOA_NOME, criar_partida_no_game, pendentes, publicar_pedido
from tests.servico.pessoa import Pessoa, esperando_por

ASSENTOS = [
    {"assento": 0, "usuario_id": PESSOA_ID, "nome": PESSOA_NOME, "bot": False},
    {"assento": 1, "usuario_id": None, "nome": "Bot 1", "bot": True},
]


class Servico:
    """Um serviço de Bots dentro do teste: o Gerenciador e a tarefa que lê os pedidos. parar()
    faz o mesmo que o serviço desligando: os bots param sem confirmar os pedidos."""

    def __init__(self):
        self.gerenciador = eventos.Gerenciador(eventos.conectar())
        self._leitura = asyncio.create_task(self.gerenciador.rodar())

    async def parar(self):
        self._leitura.cancel()
        await asyncio.gather(self._leitura, return_exceptions=True)
        await self.gerenciador.encerrar()
        await self.gerenciador.broker.aclose()


def tudo_lido(broker):
    """O grupo "bots" já recebeu todas as mensagens do stream."""
    return broker.xinfo_groups(eventos.STREAM)[0]["lag"] == 0


def test_o_bot_volta_a_jogar_depois_de_um_reinicio_do_servico(sistema_no_ar, broker):
    async def cenario():
        partida_id = criar_partida_no_game(ASSENTOS)
        publicar_pedido(broker, partida_id, 1, "Bot 1")
        servico = Servico()
        async with Pessoa(partida_id, PESSOA_ID, PESSOA_NOME, agressiva=False) as pessoa:
            await pessoa.esperar(lambda p: p.jogadas_de(1) >= 2, 20, "o bot jogar duas cartas")

            # O serviço cai: o bot sai da mesa, e o pedido dele continua pendente no broker.
            await servico.parar()
            assert len(pendentes(broker)) == 1
            await pessoa.esperar(lambda p: esperando_por(p.estado, 1), 20, "a partida parar na vez do bot")
            antes = pessoa.jogadas_de(1)
            await asyncio.sleep(1)
            assert pessoa.jogadas_de(1) == antes and esperando_por(pessoa.estado, 1)

            # O serviço volta: lê o pedido pendente, e o bot reconecta e continua de onde parou.
            servico = Servico()
            await pessoa.esperar(lambda p: p.jogadas_de(1) > antes, 20, "o bot voltar a jogar")
            assert list(servico.gerenciador.ativos) == [(partida_id, 1)]

            # Daí em diante a pessoa acelera a partida, e o bot joga até o fim e confirma o pedido.
            pessoa.agressiva = True
            await pessoa.esperar(lambda p: p.estado["status"] == "encerrada", 90, "a partida terminar")
            await pessoa.esperar(lambda p: not servico.gerenciador.ativos and not pendentes(broker), 10, "o bot sair")
            assert pessoa.erros == []
        await servico.parar()

    asyncio.run(cenario())


def test_o_mesmo_pedido_repetido_nao_cria_outro_bot(sistema_no_ar, broker, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    async def cenario():
        partida_id = criar_partida_no_game(ASSENTOS)
        for _ in range(3):  # o mesmo pedido, três vezes (o Lobby reenvia se cair na entrega)
            publicar_pedido(broker, partida_id, 1, "Bot 1")
        servico = Servico()
        async with Pessoa(partida_id, PESSOA_ID, PESSOA_NOME, agressiva=False) as pessoa:
            # Um bot só: os repetidos foram confirmados na hora, e só o primeiro fica pendente
            # enquanto o bot joga.
            await pessoa.esperar(lambda p: tudo_lido(broker) and len(pendentes(broker)) == 1, 5, "os repetidos serem confirmados")
            await pessoa.esperar(lambda p: p.jogadas_de(1) >= 1, 20, "o bot jogar")
            assert list(servico.gerenciador.ativos) == [(partida_id, 1)]
            primeiro = servico.gerenciador.ativos[(partida_id, 1)].bot

            # Repetido no meio da partida: continua o mesmo bot.
            publicar_pedido(broker, partida_id, 1, "Bot 1")
            await pessoa.esperar(lambda p: tudo_lido(broker) and len(pendentes(broker)) == 1, 5, "o repetido ser confirmado")
            assert servico.gerenciador.ativos[(partida_id, 1)].bot is primeiro

            pessoa.agressiva = True
            await pessoa.esperar(lambda p: p.estado["status"] == "encerrada", 90, "a partida terminar")
            await pessoa.esperar(lambda p: not servico.gerenciador.ativos and not pendentes(broker), 10, "o bot sair")

            # Repetido depois do fim: confirmado sem bot novo.
            publicar_pedido(broker, partida_id, 1, "Bot 1")
            await pessoa.esperar(lambda p: "já terminou: pedido repetido" in caplog.text and not pendentes(broker), 5, "o repetido ser ignorado")
            assert not servico.gerenciador.ativos
            assert pessoa.erros == []
        await servico.parar()
        assert caplog.text.count("começou a jogar") == 1

    asyncio.run(cenario())


def test_saude(broker):
    with TestClient(app) as cliente:
        resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "bots_ativos": 0}
