"""Eventos do Lobby no broker de eventos: o Redis "eventos", com Redis Streams.

O formato é o do Game (docs/guia-backend-mesa.md, seção 10.4): um stream por evento, com o nome
do evento, e cada mensagem com um campo só, "dados", com o evento em JSON.

O Lobby PUBLICA bot.solicitado, um para cada assento de bot, quando a partida começa:
    {"partida_id", "assento", "nome", "nivel"}
    O "nome" ("Bot 1") vai junto porque o serviço de Bots precisa dele no token do bot (guia da
    mesa, 10.5). Ninguém consome este evento até a fase 4.

O Lobby LÊ partida.finalizada, com o grupo "lobby": a sala da partida passa a "encerrada" e sai
da lista. O evento pode chegar mais de uma vez; o efeito é o mesmo (banco.encerrar_sala_da_partida).

O Lobby NÃO lê partida.criada. Ele já recebe o partida_id na resposta do POST /interno/partidas
e o grava na mesma transação que passa a sala para "em_partida"; o evento repetiria essa
informação, e poderia até chegar antes do commit. Sem grupo "lobby" nesse stream, nada fica
pendente para ele no broker.

Entrega do bot.solicitado: como no Game, o evento não vai direto ao broker. Ele entra na tabela
eventos_pendentes do lobby-db, na mesma transação que inicia a partida, e o Entregador passa a
fila para o broker. Com o broker fora do ar, a partida começa do mesmo jeito, e os eventos esperam
na fila até ele voltar (P13 do guia do lobby). Se o Lobby cair entre o envio e a retirada da fila,
o evento sai de novo: quem consome precisa ignorar repetidos (pelo partida_id e o assento).
"""

import json
import logging
import threading
from collections.abc import Callable

import redis

from app import banco, config

log = logging.getLogger("uvicorn.error")

STREAM_BOT_SOLICITADO = "bot.solicitado"
STREAM_PARTIDA_FINALIZADA = "partida.finalizada"
GRUPO = "lobby"
# Nome fixo do consumidor dentro do grupo. Depois de um reinício, o Lobby volta com o mesmo nome e
# recebe de novo o que tinha lido sem confirmar. Por isso o serviço roda com um processo só.
CONSUMIDOR = "lobby-1"


def conectar() -> redis.Redis:
    """Cliente do broker. Ele guarda um conjunto de conexões, usado pelas duas linhas de execução
    (Entregador e Consumidor)."""
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


class EventoInvalido(Exception):
    """Mensagem fora do formato. É registrada no log e confirmada (XACK), para não travar a fila."""


def ler_dados(campos: dict | None) -> dict:
    """O evento de uma mensagem do stream: o campo "dados", em JSON."""
    try:
        dados = json.loads(campos["dados"])
    except (KeyError, TypeError, ValueError) as erro:
        raise EventoInvalido("a mensagem não tem o campo dados em JSON") from erro
    if not isinstance(dados, dict):
        raise EventoInvalido("o campo dados não é um objeto JSON")
    return dados


def tratar_partida_finalizada(dados: dict) -> None:
    partida_id = dados.get("partida_id")
    if not isinstance(partida_id, str) or not partida_id:
        raise EventoInvalido("partida.finalizada sem partida_id")
    if banco.encerrar_sala_da_partida(partida_id):
        log.info("Partida %s finalizada: sala encerrada.", partida_id)


# ---------- Linhas de execução ----------
# As duas rodam ao lado do servidor, numa linha de execução (thread) cada, desde que o serviço sobe
# até ele parar (main.py). Nenhuma pode morrer por causa de um erro: um broker ou um banco fora do
# ar vira um aviso no log e uma nova tentativa depois de INTERVALO_DE_NOVA_TENTATIVA segundos.


class LinhaDeExecucao:
    nome = "eventos"

    def __init__(self) -> None:
        self._parar = threading.Event()
        self._linha: threading.Thread | None = None

    def iniciar(self) -> None:
        self._parar.clear()
        self._linha = threading.Thread(target=self.rodar, name=self.nome, daemon=True)
        self._linha.start()

    def parar(self) -> None:
        self._parar.set()
        self.acordar()
        if self._linha is not None:
            self._linha.join(timeout=config.ESPERA_POR_EVENTOS + 5)

    def acordar(self) -> None:
        pass

    def rodar(self) -> None:
        raise NotImplementedError


class Entregador(LinhaDeExecucao):
    """Passa os eventos de eventos_pendentes para o broker, na ordem em que entraram. Acorda na
    hora quando a rota avisa que gravou um evento (acordar) e, de qualquer jeito, a cada
    INTERVALO_DE_NOVA_TENTATIVA segundos, para tentar de novo depois de uma falha."""

    nome = "entregador-de-eventos"

    def __init__(self, broker: redis.Redis) -> None:
        super().__init__()
        self.broker = broker
        self._acordar = threading.Event()

    def acordar(self) -> None:
        self._acordar.set()

    def entregar_pendentes(self) -> None:
        """Publica cada evento da fila e só então o tira dela."""
        while (evento := banco.proximo_evento()) is not None:
            self.broker.xadd(evento["nome"], {"dados": evento["dados"]})
            banco.apagar_evento(evento["id"])

    def rodar(self) -> None:
        while not self._parar.is_set():
            self._acordar.clear()
            try:
                self.entregar_pendentes()
            except Exception as erro:  # sem esta linha de execução, nenhum evento sai
                log.warning(
                    "Eventos não entregues ao broker (%r). Nova tentativa em %s s.",
                    erro,
                    config.INTERVALO_DE_NOVA_TENTATIVA,
                )
            self._acordar.wait(config.INTERVALO_DE_NOVA_TENTATIVA)


class Consumidor(LinhaDeExecucao):
    """Lê um stream do broker como parte de um grupo (XREADGROUP) e confirma cada mensagem
    tratada (XACK). O grupo guarda no broker até onde já leu: o que chegar com o serviço fora do
    ar espera no stream.

    Ao começar, cria o grupo, se ele ainda não existe, a partir do início do stream (id "0"), e
    relê o que ficou pendente: lido e não confirmado antes de uma queda ou de uma falha no banco.
    Depois, espera os eventos novos (">"). Uma falha ao tratar um evento (o banco fora do ar)
    deixa a mensagem pendente: ela é lida de novo na próxima tentativa."""

    def __init__(self, broker: redis.Redis, stream: str, grupo: str, consumidor: str, tratar: Callable[[dict], None]):
        super().__init__()
        self.broker = broker
        self.stream = stream
        self.grupo = grupo
        self.consumidor = consumidor
        self.tratar = tratar
        self.nome = f"consumidor-{stream}"

    def criar_grupo(self) -> None:
        try:
            self.broker.xgroup_create(self.stream, self.grupo, id="0", mkstream=True)
        except redis.ResponseError as erro:
            if "BUSYGROUP" not in str(erro):  # BUSYGROUP: o grupo já existe
                raise

    def ler(self, a_partir_de: str) -> int:
        """Lê e trata um lote: "0" para os pendentes deste consumidor, ">" para os novos (esperando
        até ESPERA_POR_EVENTOS segundos). Devolve quantas mensagens vieram."""
        espera = None if a_partir_de == "0" else max(1, int(config.ESPERA_POR_EVENTOS * 1000))
        resposta = self.broker.xreadgroup(self.grupo, self.consumidor, {self.stream: a_partir_de}, count=50, block=espera)
        mensagens = [mensagem for _stream, lista in resposta or [] for mensagem in lista]
        for id_mensagem, campos in mensagens:
            try:
                self.tratar(ler_dados(campos))
            except EventoInvalido as problema:
                log.warning("Evento %s de %s ignorado: %s.", id_mensagem, self.stream, problema)
            self.broker.xack(self.stream, self.grupo, id_mensagem)
        return len(mensagens)

    def rodar(self) -> None:
        while not self._parar.is_set():
            try:
                self.criar_grupo()
                while self.ler("0"):
                    pass  # pendentes, até acabarem
                while not self._parar.is_set():
                    self.ler(">")
            except Exception as erro:
                log.warning(
                    "Leitura de %s interrompida (%r). Nova tentativa em %s s.",
                    self.stream,
                    erro,
                    config.INTERVALO_DE_NOVA_TENTATIVA,
                )
                self._parar.wait(config.INTERVALO_DE_NOVA_TENTATIVA)
