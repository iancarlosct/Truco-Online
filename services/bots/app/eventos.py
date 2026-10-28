"""Pedidos de bot: o evento bot.solicitado, lido do broker de eventos (o Redis "eventos").

O Lobby publica um bot.solicitado para cada assento de bot quando a partida começa
(docs/guia-backend-lobby.md, seção 11.3), no stream "bot.solicitado", com o evento em JSON no
campo "dados":

    {"partida_id": "84ab7cf6-...", "assento": 2, "nome": "Bot 1", "nivel": "padrao"}

O serviço de Bots lê o stream com o grupo "bots" e, para cada pedido, põe um bot para jogar
naquela partida e naquele assento (bot.py). Todos os bots, de todas as partidas, rodam neste
mesmo processo, cada um numa tarefa do asyncio.

Sem banco: o próprio broker guarda quais bots estão jogando
----------------------------------------------------------
O grupo de consumo do Redis Streams lembra, para cada mensagem entregue, se ela já foi
confirmada (XACK). O serviço usa isso como a lista dos bots ativos:
- o pedido chega, o bot começa a jogar, e a mensagem fica SEM confirmar (pendente);
- só quando o bot termina (a partida acabou, ou o Game recusou o bot) a mensagem é confirmada.
Se o serviço cair ou reiniciar no meio de uma partida, as mensagens dos bots que estavam
jogando continuam pendentes. Ao subir, o serviço lê primeiro os seus pendentes (XREADGROUP com o
id "0") e põe esses bots para jogar de novo. Eles reconectam ao Game, que manda o estado atual, e
a partida continua de onde parou.

O nome do consumidor dentro do grupo é fixo ("bots-1"): é com ele que o serviço reencontra os
seus pendentes depois de um reinício. Por isso o serviço roda com um processo só.

Pedidos repetidos
-----------------
O mesmo bot.solicitado pode chegar mais de uma vez: o Lobby o publica de novo se cair entre o
envio e a retirada da fila dele. O bot é identificado pelo partida_id e pelo assento:
- se esse bot já está jogando, a mensagem repetida é confirmada e ignorada;
- se esse bot já terminou, também (o serviço lembra os últimos que terminaram).
A lista dos que terminaram fica na memória e se perde num reinício. Um pedido repetido que chegue
depois disso põe um bot que conecta, recebe o estado "encerrada" e sai na hora, sem jogar nada.

Mensagens fora do formato vão para o log e são confirmadas, para não travar a fila. O grupo é
criado a partir do início do stream (id "0"): os pedidos publicados antes de o serviço existir
também são atendidos (numa partida que já terminou, o bot só entra e sai).
"""

import asyncio
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass

import redis.asyncio as redis

from app import config
from app.bot import ESTRATEGIAS, Bot

log = logging.getLogger("uvicorn.error")

STREAM = "bot.solicitado"
GRUPO = "bots"
CONSUMIDOR = "bots-1"
# Quantos bots que já terminaram o serviço lembra, para ignorar os pedidos repetidos deles.
LEMBRAR_ENCERRADOS = 10_000


def conectar() -> redis.Redis:
    """Cliente do broker. Ele guarda um conjunto de conexões: a leitura dos pedidos, as
    confirmações dos bots e a /saude usam cada uma a sua."""
    return redis.Redis(
        host=config.EVENTOS_HOST,
        port=config.EVENTOS_PORTA,
        password=config.EVENTOS_SENHA,
        db=config.EVENTOS_NUMERO,
        decode_responses=True,  # devolve texto (str) em vez de bytes
        socket_connect_timeout=5,
        # Maior que ESPERA_POR_EVENTOS: o XREADGROUP fica esse tempo esperando resposta.
        socket_timeout=config.ESPERA_POR_EVENTOS + 5,
    )


class PedidoInvalido(Exception):
    """Mensagem fora do formato. É registrada no log e confirmada (XACK), para não travar a fila."""


@dataclass(frozen=True)
class Pedido:
    partida_id: str
    assento: int
    nome: str
    nivel: str

    @property
    def chave(self) -> tuple[str, int]:
        """O que identifica um bot: dois pedidos com a mesma chave são o mesmo bot."""
        return (self.partida_id, self.assento)


def ler_pedido(campos: dict | None) -> Pedido:
    """O pedido de uma mensagem do stream. Uma mensagem pendente apagada do stream chega sem
    campos (None) e também é inválida."""
    try:
        dados = json.loads(campos["dados"])
    except (KeyError, TypeError, ValueError) as erro:
        raise PedidoInvalido("a mensagem não tem o campo dados em JSON") from erro
    if not isinstance(dados, dict):
        raise PedidoInvalido("o campo dados não é um objeto JSON")
    partida_id, assento = dados.get("partida_id"), dados.get("assento")
    if not isinstance(partida_id, str) or not partida_id.strip():
        raise PedidoInvalido("bot.solicitado sem partida_id")
    if not isinstance(assento, int) or isinstance(assento, bool) or not 0 <= assento <= 3:
        raise PedidoInvalido("bot.solicitado sem um assento de 0 a 3")
    nome = dados.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        nome = "Bot"  # o nome só vai no token; o Game mostra o nome que recebeu do Lobby
    nivel = dados.get("nivel", "padrao")
    if nivel not in ESTRATEGIAS:
        log.warning("Nível de bot desconhecido (%r) na partida %s: o bot joga no nível padrao.", nivel, partida_id)
        nivel = "padrao"
    return Pedido(partida_id, assento, nome.strip(), nivel)


@dataclass
class Ativo:
    """Um bot jogando: a mensagem do pedido (pendente até ele terminar) e a tarefa dele."""

    id_mensagem: str
    bot: Bot
    tarefa: asyncio.Task


class Gerenciador:
    """Lê os pedidos de bot e cuida dos bots que estão jogando. Uma instância só, criada quando
    o serviço sobe (main.py)."""

    def __init__(self, broker: redis.Redis, consumidor: str = CONSUMIDOR):
        self.broker = broker
        self.consumidor = consumidor
        self.ativos: dict[tuple[str, int], Ativo] = {}
        self._encerrados: OrderedDict[tuple[str, int], None] = OrderedDict()

    async def rodar(self) -> None:
        """Roda desde que o serviço sobe até ele parar. Um broker fora do ar vira um aviso no log
        e uma nova tentativa depois de INTERVALO_DE_NOVA_TENTATIVA segundos; os bots que já estão
        jogando continuam."""
        while True:
            try:
                await self._criar_grupo()
                await self._retomar_pendentes()
                while True:
                    await self._ler(">")  # pedidos novos
            except Exception as erro:
                log.warning(
                    "Leitura de %s interrompida (%r). Nova tentativa em %s s.",
                    STREAM,
                    erro,
                    config.INTERVALO_DE_NOVA_TENTATIVA,
                )
                await asyncio.sleep(config.INTERVALO_DE_NOVA_TENTATIVA)

    async def encerrar(self) -> None:
        """Para todos os bots quando o serviço desliga, SEM confirmar os pedidos: eles continuam
        pendentes no broker, e os bots voltam a jogar quando o serviço subir de novo."""
        tarefas = [ativo.tarefa for ativo in self.ativos.values()]
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)

    # ---------- Leitura do stream ----------

    async def _criar_grupo(self) -> None:
        try:
            await self.broker.xgroup_create(STREAM, GRUPO, id="0", mkstream=True)
        except redis.ResponseError as erro:
            if "BUSYGROUP" not in str(erro):  # BUSYGROUP: o grupo já existe
                raise

    async def _retomar_pendentes(self) -> None:
        """Os pedidos que este consumidor recebeu e não confirmou: os bots que estavam jogando
        antes de um reinício. Lidos em lotes, do mais antigo ao mais novo: com um id no lugar de
        ">", o XREADGROUP devolve os pendentes com id maior que ele."""
        ultimo = "0"
        while mensagens := await self._ler(ultimo):
            ultimo = mensagens[-1][0]

    async def _ler(self, a_partir_de: str) -> list:
        """Lê e trata um lote: um id para os pendentes, ">" para os novos (esperando até
        ESPERA_POR_EVENTOS segundos). Devolve as mensagens lidas."""
        espera = max(1, int(config.ESPERA_POR_EVENTOS * 1000)) if a_partir_de == ">" else None
        resposta = await self.broker.xreadgroup(GRUPO, self.consumidor, {STREAM: a_partir_de}, count=50, block=espera)
        mensagens = [mensagem for _stream, lista in resposta or [] for mensagem in lista]
        for id_mensagem, campos in mensagens:
            await self._tratar(id_mensagem, campos)
        return mensagens

    async def _tratar(self, id_mensagem: str, campos: dict | None) -> None:
        try:
            pedido = ler_pedido(campos)
        except PedidoInvalido as problema:
            log.warning("Pedido de bot %s ignorado: %s.", id_mensagem, problema)
            await self.broker.xack(STREAM, GRUPO, id_mensagem)
            return
        ativo = self.ativos.get(pedido.chave)
        if ativo is not None:
            if ativo.id_mensagem != id_mensagem:
                log.info("%s já está jogando: pedido repetido %s ignorado.", ativo.bot, id_mensagem)
                await self.broker.xack(STREAM, GRUPO, id_mensagem)
            return  # a própria mensagem do bot, relida dos pendentes: nada a fazer
        if pedido.chave in self._encerrados:
            log.info("O bot da partida %s, assento %s, já terminou: pedido repetido %s ignorado.", *pedido.chave, id_mensagem)
            await self.broker.xack(STREAM, GRUPO, id_mensagem)
            return
        bot = Bot(pedido.partida_id, pedido.assento, pedido.nome, pedido.nivel)
        tarefa = asyncio.create_task(self._cuidar(pedido.chave, id_mensagem, bot), name=f"bot-{pedido.partida_id}-{pedido.assento}")
        self.ativos[pedido.chave] = Ativo(id_mensagem, bot, tarefa)
        log.info("%s começou a jogar.", bot)

    # ---------- Cada bot ----------

    async def _cuidar(self, chave: tuple[str, int], id_mensagem: str, bot: Bot) -> None:
        """Roda o bot e, quando ele termina, confirma o pedido. Se a tarefa for cancelada (o
        serviço desligando), o pedido fica pendente."""
        try:
            await bot.jogar()
        except Exception:
            # Bot.jogar() não deveria levantar nada. Sem confirmar, o bot volta no próximo reinício.
            log.exception("%s parou por um erro inesperado.", bot)
            return
        finally:
            self.ativos.pop(chave, None)
        self._encerrados[chave] = None
        if len(self._encerrados) > LEMBRAR_ENCERRADOS:
            self._encerrados.popitem(last=False)
        try:
            await self.broker.xack(STREAM, GRUPO, id_mensagem)
        except Exception as erro:
            # Fica pendente: na próxima leitura dos pendentes (depois de uma falha do broker ou de
            # um reinício), o pedido é reconhecido como de um bot que já terminou, ou o bot entra
            # na partida encerrada e sai na hora. Nos dois casos, é confirmado.
            log.warning("Não foi possível confirmar o pedido %s de %s (%r).", id_mensagem, bot, erro)
