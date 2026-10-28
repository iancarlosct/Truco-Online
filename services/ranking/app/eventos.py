"""Leitura do evento partida.finalizada no broker de eventos: o Redis "eventos", com Redis Streams.

O Ranking só recebe eventos: nenhum serviço o chama para registrar um resultado. O formato é o do
Game (docs/guia-backend-mesa.md, seção 10.4): o stream "partida.finalizada", com o evento em JSON
no campo "dados":

    {"partida_id", "sala_id", "formato",
     "times": {"A": [{"assento", "usuario_id", "nome", "bot"}], "B": [...]},
     "vencedor_time": "A" ou "B", "placar_final": {"A": 12, "B": 7}, "encerrada_em"}

Os nomes dos jogadores vêm do próprio evento; o Ranking não consulta o Auth.

Partidas contra bots contam normalmente para os jogadores humanos (decisão do grupo, P14 do guia
do lobby). Os bots ficam registrados no histórico da partida, mas não entram no ranking.

O Ranking lê com o grupo "ranking". Na primeira vez, o grupo é criado a partir do início do stream
(id "0"): os eventos que o Game publicou antes de o Ranking existir são lidos também. O mesmo
evento pode chegar mais de uma vez (o Game reenvia depois de uma queda, ou o grupo é recriado);
ele conta uma vez só, porque a partida é gravada com o partida_id como chave (banco.py).
"""

import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

import redis
from sqlalchemy.exc import DataError, IntegrityError

from app import banco, config

log = logging.getLogger("uvicorn.error")

STREAM_PARTIDA_FINALIZADA = "partida.finalizada"
GRUPO = "ranking"
# Nome fixo do consumidor dentro do grupo. Depois de um reinício, o Ranking volta com o mesmo nome e
# recebe de novo o que tinha lido sem confirmar. Por isso o serviço roda com um processo só (P18).
CONSUMIDOR = "ranking-1"


def conectar() -> redis.Redis:
    """Cliente do broker de eventos."""
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


# ---------- partida.finalizada ----------


def _texto(valor) -> bool:
    return isinstance(valor, str) and bool(valor)


def _inteiro(valor) -> bool:
    # bool é um caso particular de int no Python: True não vale como assento nem como placar.
    return isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= 32767


def ler_partida_finalizada(dados: dict) -> dict:
    """Confere o evento e o devolve pronto para banco.registrar_partida:
    {partida_id, sala_id, formato, vencedor_time, placar_a, placar_b, encerrada_em,
     jogadores: [{assento, time, usuario_id, nome, bot}]}. Levanta EventoInvalido."""
    partida_id, sala_id, formato = dados.get("partida_id"), dados.get("sala_id"), dados.get("formato")
    if not _texto(partida_id):
        raise EventoInvalido("sem partida_id")
    if sala_id is not None and not isinstance(sala_id, str):
        raise EventoInvalido("sala_id não é texto")
    if not _texto(formato):
        raise EventoInvalido("sem formato")
    if dados.get("vencedor_time") not in ("A", "B"):
        raise EventoInvalido("vencedor_time não é A nem B")
    placar = dados.get("placar_final")
    if not isinstance(placar, dict) or not (_inteiro(placar.get("A")) and _inteiro(placar.get("B"))):
        raise EventoInvalido("placar_final fora do formato")
    try:
        encerrada_em = datetime.fromisoformat(dados["encerrada_em"])
    except (KeyError, TypeError, ValueError) as erro:
        raise EventoInvalido("encerrada_em não é uma data ISO 8601") from erro
    if encerrada_em.tzinfo is None:
        encerrada_em = encerrada_em.replace(tzinfo=timezone.utc)

    times = dados.get("times")
    if not isinstance(times, dict) or not all(isinstance(times.get(time, []), list) for time in ("A", "B")):
        raise EventoInvalido("times fora do formato")
    jogadores = []
    for time in ("A", "B"):
        for jogador in times.get(time, []):
            if not isinstance(jogador, dict):
                raise EventoInvalido("jogador fora do formato")
            usuario_id = jogador.get("usuario_id")
            bot = jogador.get("bot", usuario_id is None)
            if not _inteiro(jogador.get("assento")) or not _texto(jogador.get("nome")) or not isinstance(bot, bool):
                raise EventoInvalido("jogador sem assento, nome ou bot")
            if not bot and not _texto(usuario_id):
                raise EventoInvalido("jogador humano sem usuario_id")
            jogadores.append(
                {
                    "assento": jogador["assento"],
                    "time": time,
                    "usuario_id": None if bot else usuario_id,
                    "nome": jogador["nome"],
                    "bot": bot,
                }
            )
    assentos = [j["assento"] for j in jogadores]
    humanos = [j["usuario_id"] for j in jogadores if not j["bot"]]
    if len(set(assentos)) != len(assentos) or len(set(humanos)) != len(humanos):
        raise EventoInvalido("assento ou jogador repetido")

    return {
        "partida_id": partida_id,
        "sala_id": sala_id,
        "formato": formato,
        "vencedor_time": dados["vencedor_time"],
        "placar_a": placar["A"],
        "placar_b": placar["B"],
        "encerrada_em": encerrada_em,
        "jogadores": jogadores,
    }


def tratar_partida_finalizada(dados: dict) -> None:
    partida = ler_partida_finalizada(dados)
    try:
        nova = banco.registrar_partida(partida)
    except (DataError, IntegrityError) as erro:
        # O banco recusou o conteúdo: tentar de novo daria o mesmo erro e travaria a fila.
        raise EventoInvalido(f"o banco recusou a partida ({erro.orig})") from erro
    if nova:
        log.info("Partida %s registrada no ranking.", partida["partida_id"])
    else:
        log.info("Partida %s já estava registrada: evento repetido ignorado.", partida["partida_id"])


# ---------- Linha de execução do consumidor ----------
# Roda ao lado do servidor, numa linha de execução (thread) própria, desde que o serviço sobe até
# ele parar (main.py). Não pode morrer por causa de um erro: um broker ou um banco fora do ar vira
# um aviso no log e uma nova tentativa depois de INTERVALO_DE_NOVA_TENTATIVA segundos. Com o
# Ranking fora do ar, as partidas continuam (RNF): os eventos esperam no stream.


class Consumidor:
    """Lê um stream do broker como parte de um grupo (XREADGROUP) e confirma cada mensagem
    tratada (XACK). O grupo guarda no broker até onde já leu.

    Ao começar, cria o grupo, se ele ainda não existe, a partir do início do stream (id "0"), e
    relê o que ficou pendente: lido e não confirmado antes de uma queda ou de uma falha no banco.
    Depois, espera os eventos novos (">"). Uma falha ao tratar um evento (o banco fora do ar)
    deixa a mensagem pendente: ela é lida de novo na próxima tentativa."""

    def __init__(self, broker: redis.Redis, stream: str, grupo: str, consumidor: str, tratar: Callable[[dict], None]):
        self.broker = broker
        self.stream = stream
        self.grupo = grupo
        self.consumidor = consumidor
        self.tratar = tratar
        self._parar = threading.Event()
        self._linha: threading.Thread | None = None

    def iniciar(self) -> None:
        self._parar.clear()
        self._linha = threading.Thread(target=self.rodar, name=f"consumidor-{self.stream}", daemon=True)
        self._linha.start()

    def parar(self) -> None:
        self._parar.set()
        if self._linha is not None:
            self._linha.join(timeout=config.ESPERA_POR_EVENTOS + 5)

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
