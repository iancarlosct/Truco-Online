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

# O mesmo segredo do Auth: é com ele que o Game confere o token sozinho, sem chamar o Auth.
JWT_SEGREDO = obrigatoria("JWT_SEGREDO")
if len(JWT_SEGREDO) < 32:
    raise RuntimeError(
        "JWT_SEGREDO precisa ter pelo menos 32 caracteres. Gere um com: "
        'python3 -c "import secrets; print(secrets.token_hex(32))"'
    )

JWT_ALGORITMO = "HS256"

# ---------- Banco (game-redis) ----------
# O banco do Game é um Redis só dele, com o estado das partidas. Como no Auth, dentro do
# container o serviço lê sempre BANCO_*; o docker-compose diz qual é o banco.

BANCO_HOST = os.environ.get("BANCO_HOST", "game-redis")
BANCO_PORTA = int(os.environ.get("BANCO_PORTA", "6379"))
BANCO_SENHA = obrigatoria("BANCO_SENHA")
# Número do banco lógico dentro do Redis (0 a 15). O serviço usa o 0; os testes, o 1.
BANCO_NUMERO = int(os.environ.get("BANCO_NUMERO", "0"))

# ---------- Broker de eventos (eventos) ----------
# Outro Redis, separado do banco: é o meio de comunicação entre os serviços (Redis Streams).

EVENTOS_HOST = os.environ.get("EVENTOS_HOST", "eventos")
EVENTOS_PORTA = int(os.environ.get("EVENTOS_PORTA", "6379"))
EVENTOS_SENHA = obrigatoria("EVENTOS_SENHA")
EVENTOS_NUMERO = int(os.environ.get("EVENTOS_NUMERO", "0"))

# ---------- Partidas ----------

# Segundos entre o fim de uma mão e a distribuição da próxima (docs/guia-backend-mesa.md, 6.4).
PAUSA_ENTRE_MAOS = 2.0

# Uma partida sem nenhuma mudança por 7 dias é apagada do Redis. Cada jogada renova o prazo.
VALIDADE_DA_PARTIDA = 7 * 24 * 60 * 60  # segundos
