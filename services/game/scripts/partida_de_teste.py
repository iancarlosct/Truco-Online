"""SÓ PARA DESENVOLVIMENTO: cria uma partida 1x1 entre dois usuários de teste, sem o Lobby.

Faz o papel do Lobby para testar a mesa e o Game sem criar sala. Roda dentro do container do
Game, que enxerga o gateway e a rota interna:

    docker compose exec game python scripts/partida_de_teste.py
    docker compose exec game python scripts/partida_de_teste.py --porta 8080   # GATEWAY_PORTA

1. Cadastra os dois usuários no Auth, pelo gateway (se já existem, só faz o login).
2. Cria a partida em POST /interno/partidas, a mesma rota que o Lobby chama.
3. Imprime o que abrir no navegador: a mesa de cada jogador, com o e-mail e a senha.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

# O gateway visto de dentro da rede do Docker: atende sempre na porta 80 do container, qualquer
# que seja a GATEWAY_PORTA do computador.
GATEWAY = "http://gateway"
# O próprio Game, de dentro do container dele. A rota interna não passa pelo gateway.
GAME = "http://127.0.0.1:8000"

SENHA = "truco123"
JOGADORES = [
    {"nome": "Ana Teste", "email": "ana.teste@truco.dev"},
    {"nome": "Beto Teste", "email": "beto.teste@truco.dev"},
]


def chamar(metodo: str, url: str, corpo: dict | None = None) -> tuple[int, dict]:
    """Faz a requisição e devolve (status, corpo em JSON), inclusive nas respostas de erro."""
    pedido = urllib.request.Request(
        url,
        data=json.dumps(corpo).encode() if corpo is not None else None,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=metodo,
    )
    try:
        with urllib.request.urlopen(pedido, timeout=10) as resposta:
            return resposta.status, json.load(resposta)
    except urllib.error.HTTPError as erro:
        return erro.code, json.load(erro)


def usuario_de_teste(jogador: dict) -> dict:
    """Cadastra (409 = já existe, tudo bem) e faz o login. Devolve o usuário: {id, nome, email}."""
    status, corpo = chamar("POST", f"{GATEWAY}/api/auth/cadastro", {**jogador, "senha": SENHA})
    if status not in (201, 409):
        sys.exit(f"Cadastro de {jogador['email']} falhou ({status}): {corpo}")
    status, corpo = chamar("POST", f"{GATEWAY}/api/auth/login", {"email": jogador["email"], "senha": SENHA})
    if status != 200:
        sys.exit(
            f"Login de {jogador['email']} falhou ({status}): {corpo}\n"
            f"O e-mail já existe com outra senha? Este script usa a senha {SENHA!r}."
        )
    return corpo["usuario"]


def main() -> None:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--porta", type=int, default=80, help="GATEWAY_PORTA do .env (padrão: 80)")
    porta = argumentos.parse_args().porta

    try:
        usuarios = [usuario_de_teste(jogador) for jogador in JOGADORES]
        status, corpo = chamar(
            "POST",
            f"{GAME}/interno/partidas",
            {
                "sala_id": None,  # sem Lobby, não há sala
                "assentos": [
                    {"assento": assento, "usuario_id": u["id"], "nome": u["nome"], "bot": False}
                    for assento, u in enumerate(usuarios)
                ],
            },
        )
    except urllib.error.URLError as erro:
        sys.exit(f"Não foi possível chamar o gateway ou o Game ({erro.reason}). Eles estão no ar? docker compose ps")
    if status != 201:
        sys.exit(f"O Game recusou a partida ({status}): {corpo}")
    partida_id = corpo["partida_id"]

    # localhost e 127.0.0.1 são endereços diferentes para o navegador: cada um guarda a sua
    # sessão (localStorage). Assim os dois jogadores cabem na mesma janela, em abas separadas.
    sufixo = "" if porta == 80 else f":{porta}"
    print(f"\nPartida 1x1 criada: {partida_id}\n")
    for usuario, host, assento in zip(usuarios, ["localhost", "127.0.0.1"], [0, 1]):
        print(f"Assento {assento}, {usuario['nome']} ({usuario['email']}, senha {SENHA}):")
        print(f"  1. Entre em   http://{host}{sufixo}/")
        print(f"  2. Depois abra http://{host}{sufixo}/mesa.html?partida={partida_id}\n")
    print("Os dois endereços são diferentes de propósito: cada um guarda a sessão de um jogador.")


if __name__ == "__main__":
    main()
