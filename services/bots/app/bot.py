"""Um bot numa partida: conecta à mesa do Game como um cliente comum e joga até o fim.

Para o Game, o bot é um jogador como a tela (docs/guia-backend-mesa.md, seções 3 a 6):
- conecta em ws://game:8000/ws/partidas/{partida_id}?token=<jwt>, pela rede interna, sem
  passar pelo gateway, com o token que o próprio serviço assina (seguranca.py);
- recebe só a mensagem "estado" na visão do assento dele (e "erro", se uma ação for recusada);
- envia as mesmas mensagens que a tela envia, escolhidas pela estratégia (estrategia.py).
O bot não acessa o game-redis nem nenhum banco: tudo o que sabe da partida vem pela conexão.

Como ele joga:
1. Conecta. Ao conectar, o Game sempre manda o estado atual. Isso vale para a primeira conexão e
   para uma reconexão, depois de uma queda ou de um reinício do serviço de Bots: o bot retoma a
   partida de onde ela está.
2. A cada estado, pergunta à estratégia o que fazer. Se há algo a fazer, espera de 1 a 2
   segundos (o "pensando", para a tela das pessoas acompanhar cada jogada) e envia.
3. Quando o estado chega com "status": "encerrada", fecha a conexão e termina.

Quedas e recusas (os códigos de fechamento da seção 3.4 do guia):
- 4403 (o bot não pertence à partida) e 4404 (a partida não existe): o bot desiste da partida e
  registra no log. Tentar de novo não mudaria nada.
- 4409 (outra conexão entrou no mesmo assento): o bot sai sem reconectar. Se reconectasse, as
  duas conexões ficariam se derrubando.
- 4401 (token recusado): só acontece com um JWT_SEGREDO diferente do Game. O bot registra o
  erro e continua tentando: corrigido o .env, ele volta a jogar sozinho.
- Qualquer outra queda (o Game reiniciando, a rede): tenta de novo, esperando 1, 2, 4 e 8
  segundos e, daí em diante, 10.
"""

import asyncio
import json
import logging
import random
import urllib.parse

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake

from app import config, estrategia, seguranca

log = logging.getLogger("uvicorn.error")

# Códigos de fechamento do Game (guia da mesa, seção 3.4).
TOKEN_INVALIDO = 4401
FORA_DA_PARTIDA = 4403
PARTIDA_INEXISTENTE = 4404
CONEXAO_SUBSTITUIDA = 4409

# Como o bot terminou (Bot.jogar).
FIM_DA_PARTIDA = "fim_da_partida"
RECUSADO = "recusado"
SUBSTITUIDO = "substituido"

# A estratégia de cada nível de bot. O Lobby só aceita "padrao" (guia do lobby, P7); um nível
# novo é uma função decidir() nova, registrada aqui.
ESTRATEGIAS = {"padrao": estrategia.decidir}


def situacao(estado: dict) -> str:
    """Um retrato do momento da partida: tudo o que a estratégia leva em conta, menos o chat.
    Dois estados com o mesmo retrato pedem a mesma decisão, e o bot age uma vez só em cada
    momento, mesmo que chegue de novo o mesmo estado (depois de uma mensagem no chat, por
    exemplo)."""
    return json.dumps([estado.get("status"), estado.get("placar"), estado.get("mao_atual")], sort_keys=True)


def sorteio_do_bot(partida_id: str, assento: int) -> random.Random:
    """O sorteio de um bot (blefe e atrasos). Com BOTS_SEMENTE, a semente junta o valor dela com
    a partida e o assento: cada bot tem a sua, e ela é a mesma a cada vez que o bot é criado."""
    if config.SEMENTE is None:
        return random.Random()
    return random.Random(f"{config.SEMENTE}-{partida_id}-{assento}")


class Bot:
    """O bot de um assento numa partida. Bot.jogar() roda até a partida terminar."""

    def __init__(self, partida_id: str, assento: int, nome: str, nivel: str = "padrao"):
        self.partida_id = partida_id
        self.assento = assento
        self.nome = nome
        self.decidir = ESTRATEGIAS[nivel]
        self.rng = sorteio_do_bot(partida_id, assento)
        self.acoes = 0  # mensagens enviadas ao Game: aparece no log do fim e nos testes
        self._estado: dict | None = None  # o último estado recebido
        self._agiu_em: str | None = None  # situação em que o bot enviou a última ação
        self._recusa_em: str | None = None  # situação em que o Game recusou uma ação
        self._tentativas = 0  # quedas seguidas, para a espera crescente

    def __str__(self) -> str:
        return f"{self.nome} (partida {self.partida_id}, assento {self.assento})"

    def endereco(self) -> str:
        """A URL da mesa, com um token novo."""
        token = seguranca.token_do_bot(self.partida_id, self.assento, self.nome)
        return f"{config.GAME_WS_URL}/ws/partidas/{urllib.parse.quote(self.partida_id, safe='')}?token={token}"

    async def jogar(self) -> str:
        """Joga até o fim e devolve como terminou: FIM_DA_PARTIDA, RECUSADO ou SUBSTITUIDO. Quedas
        de conexão não terminam o bot: ele espera e conecta de novo."""
        while True:
            try:
                # proxy=None: a conexão é direta, pela rede do Docker, mesmo que o ambiente
                # defina um proxy.
                async with connect(self.endereco(), proxy=None, open_timeout=10, close_timeout=3) as conexao:
                    await self._jogar_conectado(conexao)
                log.info("%s: partida encerrada, o bot saiu da mesa (%s ações).", self, self.acoes)
                return FIM_DA_PARTIDA
            except ConnectionClosed as fechamento:
                codigo = fechamento.rcvd.code if fechamento.rcvd else None
                if codigo in (FORA_DA_PARTIDA, PARTIDA_INEXISTENTE):
                    log.warning("%s: o Game recusou o bot (%s %s). O bot desiste desta partida.", self, codigo, fechamento.rcvd.reason)
                    return RECUSADO
                if codigo == CONEXAO_SUBSTITUIDA:
                    log.warning("%s: outra conexão entrou no mesmo assento (4409). O bot sai sem reconectar.", self)
                    return SUBSTITUIDO
                if codigo == TOKEN_INVALIDO:
                    log.error("%s: o Game recusou o token do bot (4401). Confira se o JWT_SEGREDO é o mesmo do Game.", self)
                else:
                    log.info("%s: a conexão com o Game caiu (%s).", self, fechamento)
            except (OSError, InvalidHandshake) as erro:  # OSError inclui o TimeoutError
                log.info("%s: sem conexão com o Game (%r).", self, erro)
            except Exception:
                # Um defeito do próprio bot (na estratégia, por exemplo) não pode derrubar o
                # serviço: vai para o log, e o bot tenta de novo como depois de uma queda.
                log.exception("%s: erro inesperado. Nova tentativa em seguida.", self)
            espera = min(config.RECONEXAO_MAXIMA, config.RECONEXAO_INICIAL * 2**self._tentativas)
            self._tentativas += 1
            await asyncio.sleep(espera)

    async def _jogar_conectado(self, conexao: ClientConnection) -> None:
        """Joga enquanto a conexão está aberta. Volta quando a partida termina; uma queda levanta
        ConnectionClosed."""
        # Conexão nova: o que o bot fez antes não conta. Se a última ação se perdeu na queda, o
        # estado continua o mesmo, e ele precisa agir de novo.
        self._estado = self._agiu_em = self._recusa_em = None
        while True:
            self._tratar(await conexao.recv())
            if self._estado is None:
                continue
            self._tentativas = 0  # conectou e recebeu o estado: a próxima queda recomeça do 1 s
            while True:
                if self._estado.get("status") == "encerrada":
                    return
                momento = situacao(self._estado)
                if momento == self._agiu_em:
                    break  # já agiu neste momento: espera o próximo estado
                acao = self.decidir(self._estado, self.rng, seguro=momento == self._recusa_em)
                if acao is None:
                    break  # não cabe ao bot fazer nada agora
                await self._pensar(conexao)
                if situacao(self._estado) != momento:
                    continue  # a partida mudou enquanto o bot pensava: decide de novo
                await conexao.send(json.dumps(acao))
                self._agiu_em = momento
                self.acoes += 1
                break

    async def _pensar(self, conexao: ClientConnection) -> None:
        """O atraso antes de cada ação. Enquanto espera, o bot continua lendo o que o Game manda,
        e o estado pode mudar."""
        relogio = asyncio.get_running_loop()
        fim = relogio.time() + self.rng.uniform(config.ATRASO_MINIMO, config.ATRASO_MAXIMO)
        while (resta := fim - relogio.time()) > 0:
            try:
                async with asyncio.timeout(resta):
                    texto = await conexao.recv()  # interromper o recv() não perde mensagem
            except TimeoutError:
                return
            self._tratar(texto)

    def _tratar(self, texto: str | bytes) -> None:
        """Guarda o estado recebido. Um "erro" quer dizer que o Game recusou a última ação, o que
        não deveria acontecer: a estratégia só escolhe jogadas válidas. Na primeira recusa num
        momento da partida, o bot tenta de novo uma jogada simples (carta aberta, sem truco)."""
        try:
            mensagem = json.loads(texto)
        except ValueError:
            log.warning("%s: mensagem do Game que não é JSON, ignorada.", self)
            return
        if not isinstance(mensagem, dict):
            return
        if mensagem.get("tipo") == "estado":
            self._estado = mensagem
        elif mensagem.get("tipo") == "erro":
            log.warning("%s: o Game recusou a ação (%s: %s).", self, mensagem.get("codigo"), mensagem.get("mensagem"))
            if self._estado is not None and self._recusa_em != (momento := situacao(self._estado)):
                self._recusa_em = momento
                self._agiu_em = None
