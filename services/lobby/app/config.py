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

# O mesmo segredo do Auth: é com ele que o Lobby confere o token sozinho, sem chamar o Auth.
JWT_SEGREDO = obrigatoria("JWT_SEGREDO")
if len(JWT_SEGREDO) < 32:
    raise RuntimeError(
        "JWT_SEGREDO precisa ter pelo menos 32 caracteres. Gere um com: "
        'python3 -c "import secrets; print(secrets.token_hex(32))"'
    )

JWT_ALGORITMO = "HS256"

# ---------- Banco (lobby-db) ----------

BANCO_HOST = os.environ.get("BANCO_HOST", "lobby-db")
BANCO_PORTA = int(os.environ.get("BANCO_PORTA", "5432"))
BANCO_NOME = obrigatoria("BANCO_NOME")
BANCO_USUARIO = obrigatoria("BANCO_USUARIO")
BANCO_SENHA = obrigatoria("BANCO_SENHA")

# ---------- Serviço Game ----------

# Endereço interno do Game, na rede-servicos. A rota POST /interno/partidas não passa pelo gateway.
GAME_URL = os.environ.get("GAME_URL", "http://game:8000")
# Segundos de espera pela resposta do Game ao iniciar a partida. Depois disso, 503 game_indisponivel.
GAME_TEMPO_LIMITE = 5.0

# ---------- Broker de eventos (eventos) ----------
# O mesmo Redis em que o Game publica. O Lobby lê partida.finalizada e publica bot.solicitado.

EVENTOS_HOST = os.environ.get("EVENTOS_HOST", "eventos")
EVENTOS_PORTA = int(os.environ.get("EVENTOS_PORTA", "6379"))
EVENTOS_SENHA = obrigatoria("EVENTOS_SENHA")
# Número do banco lógico dentro do Redis (0 a 15). O serviço usa o 0; os testes, o 2.
EVENTOS_NUMERO = int(os.environ.get("EVENTOS_NUMERO", "0"))

# Segundos que uma leitura do broker espera por eventos novos antes de voltar (XREADGROUP BLOCK).
ESPERA_POR_EVENTOS = 2.0
# Segundos entre as tentativas quando o broker ou o banco estão fora do ar.
INTERVALO_DE_NOVA_TENTATIVA = 5.0

# ---------- Salas ----------

ASSENTOS_POR_FORMATO = {"1x1": 2, "2x2": 4}
NIVEIS_DE_BOT = {"padrao"}
# Segundos sem GET /api/lobby/salas/{id} até o jogador sentado sair da sala (guia do lobby, 6.5).
PRAZO_PRESENCA = 60
# Tamanho máximo do nome, o mesmo do cadastro no Auth.
NOME_MAX = 20
