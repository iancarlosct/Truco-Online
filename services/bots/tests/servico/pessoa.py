"""A pessoa dos testes: conecta à mesa do Game com um token de usuário e joga sem atraso.

Ela escolhe as cartas como o bot (estrategia.escolher_carta), mas responde pelo time dela, sem a
regra do parceiro, e tem dois jeitos de jogar:
- agressiva: pede truco sempre que pode, aumenta sempre que pode e joga toda mão de onze. As
  apostas sobem, e a partida acaba em poucas mãos;
- calma: nunca pede truco, aceita todo pedido e joga toda mão de onze. A partida anda devagar,
  o que dá tempo de mexer no serviço no meio dela.
"""

import asyncio
import json
import urllib.parse
from datetime import datetime, timedelta, timezone

import jwt
from websockets.asyncio.client import connect

from app import config, estrategia
from app.bot import situacao

GAME_WS_URL = config.GAME_WS_URL


def token_de_usuario(usuario_id: str, nome: str) -> str:
    """Um token como o do Auth (sub com o id do usuário, nome e exp), assinado com o mesmo
    JWT_SEGREDO. O Lobby e o Game conferem só o token: não perguntam ao Auth."""
    conteudo = {"sub": usuario_id, "nome": nome, "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(conteudo, config.JWT_SEGREDO, algorithm="HS256")


def time_do_assento(assento: int) -> str:
    return "A" if assento % 2 == 0 else "B"


def esperando_por(estado: dict, assento: int) -> bool:
    """Se a partida está parada à espera do jogador deste assento (sem parceiro para responder
    por ele, como no 1x1)."""
    mao = estado["mao_atual"]
    time = time_do_assento(assento)
    if estado["status"] != "em_andamento" or mao["vez_assento"] is None:
        return False
    if mao["aguardando_decisao_mao_de_onze"]:
        return estado["placar"][time] == 11
    if mao["truco_pendente"]:
        return mao["truco_pendente"]["pedido_por_time"] != time
    return mao["vez_assento"] == assento


class Pessoa:
    """Use com "async with": conecta e joga numa tarefa à parte, até sair do bloco."""

    def __init__(self, partida_id: str, usuario_id: str, nome: str, agressiva: bool = True):
        self.partida_id = partida_id
        self.token = token_de_usuario(usuario_id, nome)
        self.agressiva = agressiva
        self.estado: dict | None = None
        self.erros: list[dict] = []
        self._jogadas: set[tuple[int, int, int]] = set()  # (mão, rodada, assento) de cada carta vista

    async def __aenter__(self):
        endereco = f"{GAME_WS_URL}/ws/partidas/{urllib.parse.quote(self.partida_id)}?token={self.token}"
        self.conexao = await connect(endereco, proxy=None)
        self._tarefa = asyncio.create_task(self._jogar())
        return self

    async def __aexit__(self, *erro):
        self._tarefa.cancel()
        await asyncio.gather(self._tarefa, return_exceptions=True)
        await self.conexao.close()

    def jogadas_de(self, assento: int) -> int:
        """Quantas cartas o jogador do assento jogou desde que a pessoa conectou."""
        return sum(1 for _mao, _rodada, quem in self._jogadas if quem == assento)

    async def esperar(self, condicao, limite: float, motivo: str = "a condição") -> None:
        """Espera condicao(pessoa) ficar verdadeira; falha depois de "limite" segundos."""
        try:
            async with asyncio.timeout(limite):
                while not (self.estado and condicao(self)):
                    if self._tarefa.done():
                        self._tarefa.result()  # a conexão caiu: mostra o motivo
                        raise AssertionError("a conexão da pessoa terminou")
                    await asyncio.sleep(0.05)
        except TimeoutError:
            raise AssertionError(f"{motivo} não aconteceu em {limite} s; último estado: {self.estado}") from None

    async def _jogar(self):
        agiu_em = None
        async for texto in self.conexao:
            mensagem = json.loads(texto)
            if mensagem["tipo"] == "erro":
                self.erros.append(mensagem)
                continue
            self.estado = mensagem
            mao = mensagem["mao_atual"]
            for indice, rodada in enumerate(mao["rodadas"]):
                for jogada in rodada["jogadas"]:
                    self._jogadas.add((mao["numero"], indice, jogada["assento"]))
            acao = self.decidir(mensagem)
            if acao and situacao(mensagem) != agiu_em:
                agiu_em = situacao(mensagem)
                await self.conexao.send(json.dumps(acao))

    def decidir(self, estado: dict) -> dict | None:
        mao = estado["mao_atual"]
        time = estrategia.meu_time(estado)
        if estado["status"] != "em_andamento" or mao["vez_assento"] is None:
            return None
        if mao["aguardando_decisao_mao_de_onze"]:
            return {"tipo": "decidir_mao_de_onze", "jogar": True} if estado["placar"][time] == 11 else None
        pedido = mao["truco_pendente"]
        if pedido:
            if pedido["pedido_por_time"] == time:
                return None
            aumenta = self.agressiva and pedido["valor_proposto"] < 12
            return {"tipo": "responder_truco", "resposta": "aumentar" if aumenta else "aceitar"}
        if mao["vez_assento"] != estado["meu_assento"]:
            return None
        if self.agressiva and estrategia.pode_pedir_truco(estado):
            return {"tipo": "pedir_truco"}
        return estrategia.escolher_carta(estado)
