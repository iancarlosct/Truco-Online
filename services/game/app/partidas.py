"""Camada de serviço da mesa: liga o motor de regras (engine) ao Redis, às conexões WebSocket e
aos eventos.

Uma mudança por vez em cada partida: toda alteração acontece com a trava da partida
(asyncio.Lock) fechada: lê o estado do Redis, aplica a ação no motor, grava e envia o novo
estado a todos os conectados, cada um com a sua visão. Dois jogadores que enviam no mesmo
instante (os dois parceiros respondendo a um truco, por exemplo) são atendidos um depois do
outro, e o segundo já encontra o estado do primeiro (docs/guia-backend-mesa.md, seção 6.5).

LIMITAÇÃO: um processo só (P21 do guia da mesa). As conexões abertas, as travas e a espera
entre as mãos ficam na memória deste processo. Com dois processos (uvicorn --workers 2, ou
duas réplicas do container), jogadores da mesma partida poderiam cair em processos diferentes,
deixar de receber o estado uns dos outros e alterar a partida ao mesmo tempo. Para ter vários
processos seria preciso, por exemplo, avisar as mudanças pelo pub/sub do Redis e trocar o
asyncio.Lock por uma trava no Redis. O estado em si já fica no Redis: ele sobrevive a um
reinício do serviço, e os jogadores reconectam sozinhos.
"""

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone

from fastapi import WebSocket

import engine
from app import banco, config, eventos

log = logging.getLogger("uvicorn.error")

# Códigos de fechamento da conexão (guia da mesa, seção 3.4). Com eles a tela não tenta
# conectar de novo.
TOKEN_INVALIDO = 4401
FORA_DA_PARTIDA = 4403
PARTIDA_INEXISTENTE = 4404
# O mesmo jogador abriu a partida em outra conexão (outra aba, por exemplo): vale a mais
# recente, e a anterior é fechada com este código (P19).
CONEXAO_SUBSTITUIDA = 4409


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mensagem_de_erro(codigo: str, mensagem: str) -> dict:
    return {"tipo": "erro", "codigo": codigo, "mensagem": mensagem}


async def enviar(websocket: WebSocket, mensagem: dict) -> None:
    """Envia a mensagem a uma conexão. Se ela acabou de cair, o erro é ignorado: a falha de um
    jogador não pode impedir o envio aos outros, e quem tira a conexão da lista é o laço de
    leitura dela (rotas.py)."""
    try:
        await websocket.send_json(mensagem)
    except Exception as erro:
        log.debug("Envio para uma conexão que caiu: %r", erro)


async def fechar(websocket: WebSocket, codigo: int, motivo: str) -> None:
    try:
        await websocket.close(code=codigo, reason=motivo)
    except Exception as erro:
        log.debug("Fechamento de uma conexão que já tinha caído: %r", erro)


class Partidas:
    """As partidas deste processo: travas, conexões abertas e a espera entre as mãos. Uma só
    instância, criada quando o serviço sobe (main.py)."""

    def __init__(self, banco_redis, entregador: eventos.Entregador, rng: random.Random | None = None):
        self.banco = banco_redis
        self.entregador = entregador
        # Sorteio das cartas: SystemRandom usa a fonte de aleatoriedade do sistema operacional,
        # e ninguém consegue prever as próximas mãos a partir das anteriores.
        self.rng = rng or random.SystemRandom()
        self._travas: dict[str, asyncio.Lock] = {}
        self._conexoes: dict[str, dict[int, WebSocket]] = {}  # partida_id -> {assento: conexão}
        self._proximas_maos: dict[str, asyncio.Task] = {}  # partida_id -> espera da próxima mão
        self._fechamentos: set[asyncio.Task] = set()  # conexões substituídas sendo fechadas

    def _trava(self, partida_id: str) -> asyncio.Lock:
        return self._travas.setdefault(partida_id, asyncio.Lock())

    # ---------- Criação ----------

    async def criar(self, sala_id: str | None, assentos: list[dict]) -> str:
        """Cria a partida já com a primeira mão distribuída e devolve o partida_id. Levanta
        engine.AssentosInvalidos quando os assentos não formam uma mesa válida."""
        partida_id = str(uuid.uuid4())
        estado = engine.criar_partida(partida_id, sala_id, assentos, self.rng)
        estado["criada_em"] = agora()
        await banco.salvar_partida(self.banco, estado, [eventos.partida_criada(estado)])
        self.entregador.acordar()
        return partida_id

    async def buscar(self, partida_id: str) -> dict | None:
        return await banco.buscar_partida(self.banco, partida_id)

    # ---------- Conexões ----------

    async def entrar(self, partida_id: str, assento: int, websocket: WebSocket) -> bool:
        """Guarda a conexão do assento e envia a ela o estado atual. Vale também como
        reconexão, depois de uma queda ou de um F5. Se o assento já tinha uma conexão aberta,
        a nova a substitui, e a anterior é fechada com 4409. Devolve False se a partida não
        existe mais (a conexão é fechada com 4404)."""
        async with self._trava(partida_id):
            estado = await banco.buscar_partida(self.banco, partida_id)
            if estado is None:
                await fechar(websocket, PARTIDA_INEXISTENTE, "partida inexistente")
                return False
            da_partida = self._conexoes.setdefault(partida_id, {})
            anterior = da_partida.get(assento)
            da_partida[assento] = websocket
            if anterior is not None:
                # Fechada em segundo plano: se a conexão anterior caiu sem avisar (o celular
                # trocou de rede, por exemplo), o fechamento espera vários segundos pela
                # resposta do outro lado, e a partida não pode ficar travada esse tempo todo.
                fechamento = asyncio.create_task(fechar(anterior, CONEXAO_SUBSTITUIDA, "conexão substituída"))
                self._fechamentos.add(fechamento)
                fechamento.add_done_callback(self._fechamentos.discard)
            await enviar(websocket, engine.visao_do_jogador(estado, assento))
            # Depois de um reinício do serviço, a partida pode ter ficado parada no fim de uma
            # mão, sem ninguém para distribuir a próxima.
            if engine.aguardando_proxima_mao(estado):
                self._agendar_proxima_mao(partida_id)
            return True

    def sair(self, partida_id: str, assento: int, websocket: WebSocket) -> None:
        """Tira a conexão da lista quando ela cai. A partida continua guardada e espera o
        jogador voltar (P20). Só remove se a conexão guardada ainda for esta: o jogador pode
        já ter conectado de novo."""
        da_partida = self._conexoes.get(partida_id)
        if da_partida and da_partida.get(assento) is websocket:
            del da_partida[assento]
            if not da_partida:
                del self._conexoes[partida_id]

    # ---------- Ações ----------

    async def receber(self, partida_id: str, assento: int, websocket: WebSocket, texto: str | None) -> None:
        """Trata uma mensagem do jogador. Ação válida: grava e envia o novo estado a todos.
        Ação recusada ou mensagem malformada: só quem enviou recebe o erro, e nada muda."""
        try:
            mensagem = json.loads(texto)
        except (TypeError, ValueError, RecursionError):
            await enviar(websocket, mensagem_de_erro("acao_invalida", "A mensagem não é um JSON válido."))
            return

        async with self._trava(partida_id):
            estado = await banco.buscar_partida(self.banco, partida_id)
            if estado is None:
                await fechar(websocket, PARTIDA_INEXISTENTE, "partida inexistente")
                return
            try:
                novo = engine.aplicar_acao(estado, assento, mensagem)
            except engine.ErroJogada as recusa:
                await enviar(websocket, mensagem_de_erro(recusa.codigo, recusa.mensagem))
                if engine.aguardando_proxima_mao(estado):
                    self._agendar_proxima_mao(partida_id)
                return

            novos_eventos = []
            if novo["status"] == "encerrada" and estado["status"] != "encerrada":
                novo["encerrada_em"] = agora()
                novos_eventos.append(eventos.partida_finalizada(novo))
            await banco.salvar_partida(self.banco, novo, novos_eventos)
            if novos_eventos:
                self.entregador.acordar()
            await self._transmitir(novo)
            if engine.aguardando_proxima_mao(novo):
                self._agendar_proxima_mao(partida_id)

    async def _transmitir(self, estado: dict) -> None:
        """Envia o estado a todos os conectados da partida, cada um com a sua visão."""
        for assento, websocket in list(self._conexoes.get(estado["partida_id"], {}).items()):
            await enviar(websocket, engine.visao_do_jogador(estado, assento))

    # ---------- Pausa entre as mãos ----------
    # O estado do fim da mão sai na hora (com "vez_assento": null e o placar novo). A mão
    # seguinte é distribuída PAUSA_ENTRE_MAOS segundos depois, numa tarefa à parte: o servidor
    # continua atendendo todas as partidas (e o chat desta) durante a espera.

    def _agendar_proxima_mao(self, partida_id: str) -> None:
        tarefa = self._proximas_maos.get(partida_id)
        if tarefa is not None and not tarefa.done():
            return  # já agendada
        tarefa = asyncio.create_task(self._distribuir_proxima_mao(partida_id))
        self._proximas_maos[partida_id] = tarefa
        tarefa.add_done_callback(lambda concluida: self._fim_da_espera(partida_id, concluida))

    async def _distribuir_proxima_mao(self, partida_id: str) -> None:
        await asyncio.sleep(config.PAUSA_ENTRE_MAOS)
        async with self._trava(partida_id):
            estado = await banco.buscar_partida(self.banco, partida_id)
            if estado is None or not engine.aguardando_proxima_mao(estado):
                return
            novo = engine.iniciar_proxima_mao(estado, self.rng)
            await banco.salvar_partida(self.banco, novo)
            await self._transmitir(novo)

    def _fim_da_espera(self, partida_id: str, tarefa: asyncio.Task) -> None:
        if self._proximas_maos.get(partida_id) is tarefa:
            del self._proximas_maos[partida_id]
        if not tarefa.cancelled() and tarefa.exception() is not None:
            # A partida fica parada no fim da mão até alguém conectar ou agir de novo, quando a
            # espera é agendada outra vez.
            log.error("Falha ao distribuir a próxima mão da partida %s", partida_id, exc_info=tarefa.exception())

    async def encerrar(self) -> None:
        """Para as tarefas em andamento quando o serviço desliga."""
        for tarefa in [*self._proximas_maos.values(), *self._fechamentos]:
            tarefa.cancel()
