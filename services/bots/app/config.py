"""Configurações do serviço, lidas das variáveis de ambiente.

No Docker Compose elas são definidas no docker-compose.yml, a partir do arquivo .env da raiz do
repositório. Nenhum segredo fica escrito no código.
"""

import os


def obrigatoria(nome: str) -> str:
    """Valor de uma variável de ambiente que precisa existir. Sem ela, o serviço nem sobe."""
    valor = os.environ.get(nome, "")
    if not valor:
        raise RuntimeError(
            f"A variável de ambiente {nome} não foi definida. Confira o .env (modelo no .env.example)."
        )
    return valor


# ---------- Token (JWT) ----------

# O mesmo segredo do Auth: é com ele que o serviço de Bots assina o token de cada bot, e que o
# Game o confere (docs/guia-backend-mesa.md, seção 10.5). O Auth não participa.
JWT_SEGREDO = obrigatoria("JWT_SEGREDO")
if len(JWT_SEGREDO) < 32:
    raise RuntimeError(
        "JWT_SEGREDO precisa ter pelo menos 32 caracteres. Gere um com: "
        'python3 -c "import secrets; print(secrets.token_hex(32))"'
    )

JWT_ALGORITMO = "HS256"
# Validade do token do bot, em segundos. O Game só confere o token ao conectar, e o bot assina
# um novo a cada conexão: não precisa durar mais que isso.
VALIDADE_DO_TOKEN = 10 * 60

# ---------- Serviço Game ----------

# Endereço interno do WebSocket do Game, na rede-servicos. O bot não passa pelo gateway.
GAME_WS_URL = os.environ.get("GAME_WS_URL", "ws://game:8000")

# ---------- Broker de eventos (eventos) ----------
# O mesmo Redis em que o Lobby publica o bot.solicitado. O serviço de Bots só lê dele.

EVENTOS_HOST = os.environ.get("EVENTOS_HOST", "eventos")
EVENTOS_PORTA = int(os.environ.get("EVENTOS_PORTA", "6379"))
EVENTOS_SENHA = obrigatoria("EVENTOS_SENHA")
# Número do banco lógico dentro do Redis (0 a 15). O serviço usa o 0; os testes, o 4.
EVENTOS_NUMERO = int(os.environ.get("EVENTOS_NUMERO", "0"))

# Segundos que uma leitura do broker espera por eventos novos antes de voltar (XREADGROUP BLOCK).
ESPERA_POR_EVENTOS = 2.0
# Segundos entre as tentativas quando o broker está fora do ar.
INTERVALO_DE_NOVA_TENTATIVA = 5.0

# ---------- Bots ----------

# Segundos de espera antes de cada ação, sorteados entre os dois valores: o bot parece um
# jogador pensando, e a tela das pessoas acompanha cada jogada. Os testes usam 0.
ATRASO_MINIMO = 1.0
ATRASO_MAXIMO = 2.0

# Espera entre as tentativas de reconexão ao Game: 1, 2, 4 e 8 segundos e, daí em diante, 10.
# É o mesmo ritmo da tela (frontend/js/ws.js).
RECONEXAO_INICIAL = 1.0
RECONEXAO_MAXIMA = 10.0

# Semente do sorteio dos bots (blefe e atrasos). Vazia, cada bot sorteia de um jeito diferente a
# cada partida. Com um valor, o mesmo bot (mesma partida e assento) repete as mesmas escolhas
# diante das mesmas situações, o que ajuda a reproduzir um teste.
SEMENTE = os.environ.get("BOTS_SEMENTE", "") or None
