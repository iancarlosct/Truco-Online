"""Configurações do serviço, lidas das variáveis de ambiente.

No Docker Compose elas são definidas no docker-compose.yml, a partir do arquivo .env da raiz do
repositório. Nenhum segredo fica escrito no código.
"""

import os
from datetime import timedelta


def obrigatoria(nome: str) -> str:
    """Valor de uma variável de ambiente que precisa existir. Sem ela, o serviço nem sobe."""
    valor = os.environ.get(nome, "")
    if not valor:
        raise RuntimeError(
            f"A variável de ambiente {nome} não foi definida. Confira o .env (modelo no .env.example)."
        )
    return valor


# ---------- Token (JWT) ----------

# Segredo que assina os tokens. Lobby, Game e Ranking usam o mesmo valor para conferir os
# tokens sozinhos, sem chamar o Auth.
JWT_SEGREDO = obrigatoria("JWT_SEGREDO")
if len(JWT_SEGREDO) < 32:
    # Com menos de 32 caracteres a assinatura fica fraca (e o PyJWT avisa com
    # InsecureKeyLengthWarning). Melhor recusar logo do que descobrir depois.
    raise RuntimeError(
        "JWT_SEGREDO precisa ter pelo menos 32 caracteres. Gere um com: "
        'python3 -c "import secrets; print(secrets.token_hex(32))"'
    )

JWT_ALGORITMO = "HS256"
JWT_VALIDADE = timedelta(hours=24)

# ---------- Banco (auth-db) ----------

BANCO_HOST = os.environ.get("BANCO_HOST", "auth-db")
BANCO_PORTA = int(os.environ.get("BANCO_PORTA", "5432"))
BANCO_NOME = obrigatoria("BANCO_NOME")
BANCO_USUARIO = obrigatoria("BANCO_USUARIO")
BANCO_SENHA = obrigatoria("BANCO_SENHA")
