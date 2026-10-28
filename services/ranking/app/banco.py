"""Acesso ao banco do Ranking (container ranking-db). Só este serviço conecta nele.

Usa o SQLAlchemy 2 com o driver psycopg 3, escrevendo o SQL à mão com text(), como o Auth e o
Lobby. Os dados entram sempre como parâmetros, nunca juntando textos.

Tabelas (as da seção 7.3 do docs/guia-backend-lobby.md, com o histórico a mais):
    partidas       uma linha por partida.finalizada registrada. A chave é o partida_id: é ela que
                   faz o mesmo evento, entregue duas vezes, contar uma vez só (no lugar da tabela
                   partidas_contadas do guia).
    participantes  quem jogou cada partida, em que assento e time, bots inclusive (usuario_id
                   nulo). É o histórico de GET /api/ranking/jogadores/{id}.
    jogadores      vitórias e partidas de cada jogador humano, somadas a cada partida registrada,
                   com o nome mais recente. Bots não têm linha aqui, então não aparecem no ranking.
"""

from datetime import timezone

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app import config

# O engine guarda um conjunto de conexões abertas e reaproveita cada uma entre as requisições.
engine = create_engine(
    URL.create(
        "postgresql+psycopg",
        username=config.BANCO_USUARIO,
        password=config.BANCO_SENHA,
        host=config.BANCO_HOST,
        port=config.BANCO_PORTA,
        database=config.BANCO_NOME,
    ),
    pool_pre_ping=True,  # descarta conexões que caíram (se o banco reiniciou, por exemplo)
    connect_args={"connect_timeout": 5},  # segundos; sem isso, um banco fora do ar trava a rota
)


# ---------- Criação das tabelas ----------

# Criadas pelo próprio serviço, toda vez que ele sobe, com "IF NOT EXISTS" (a mesma escolha do
# Auth; explicação em services/auth/app/banco.py). Os nomes são TEXT, sem limite de tamanho: eles
# vêm do evento do Game, e um nome maior que o esperado não pode travar a leitura dos eventos.
SQL_CRIAR_TABELAS = [
    """
    CREATE TABLE IF NOT EXISTS partidas (
        partida_id    TEXT        PRIMARY KEY,
        sala_id       TEXT,
        formato       TEXT        NOT NULL,
        vencedor_time TEXT        NOT NULL CHECK (vencedor_time IN ('A', 'B')),
        placar_a      SMALLINT    NOT NULL,
        placar_b      SMALLINT    NOT NULL,
        encerrada_em  TIMESTAMPTZ NOT NULL,
        registrada_em TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS participantes (
        partida_id TEXT     NOT NULL REFERENCES partidas (partida_id),
        assento    SMALLINT NOT NULL,
        time       TEXT     NOT NULL CHECK (time IN ('A', 'B')),
        usuario_id TEXT,
        nome       TEXT     NOT NULL,
        bot        BOOLEAN  NOT NULL,
        PRIMARY KEY (partida_id, assento)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jogadores (
        usuario_id TEXT    PRIMARY KEY,
        nome       TEXT    NOT NULL,
        vitorias   INTEGER NOT NULL DEFAULT 0,
        partidas   INTEGER NOT NULL DEFAULT 0
    )
    """,
    # Histórico de um jogador: as partidas em que ele aparece.
    "CREATE INDEX IF NOT EXISTS participantes_usuario ON participantes (usuario_id) WHERE usuario_id IS NOT NULL",
]


def criar_tabelas() -> None:
    # engine.begin() abre uma transação e confirma (commit) ao sair do bloco.
    with engine.begin() as conexao:
        for comando in SQL_CRIAR_TABELAS:
            conexao.execute(text(comando))


# ---------- Registro de uma partida ----------


def registrar_partida(partida: dict) -> bool:
    """Grava uma partida.finalizada já conferida (eventos.ler_partida_finalizada) e soma, para
    cada jogador humano, 1 em partidas e, se o time dele venceu, 1 em vitórias. Tudo numa
    transação só: ou a partida entra inteira, ou nada muda.

    Devolve False quando a partida já estava registrada: o evento é repetido e não conta de novo."""
    with engine.begin() as conexao:
        nova = conexao.execute(
            text(
                "INSERT INTO partidas (partida_id, sala_id, formato, vencedor_time, placar_a, placar_b, encerrada_em) "
                "VALUES (:partida_id, :sala_id, :formato, :vencedor_time, :placar_a, :placar_b, :encerrada_em) "
                # Duas entregas do mesmo evento ao mesmo tempo: a segunda espera o commit da
                # primeira e não insere nada.
                "ON CONFLICT (partida_id) DO NOTHING RETURNING partida_id"
            ),
            {chave: partida[chave] for chave in ("partida_id", "sala_id", "formato", "vencedor_time", "placar_a", "placar_b", "encerrada_em")},
        ).first()
        if nova is None:
            return False
        conexao.execute(
            text(
                "INSERT INTO participantes (partida_id, assento, time, usuario_id, nome, bot) "
                "VALUES (:partida_id, :assento, :time, :usuario_id, :nome, :bot)"
            ),
            [{"partida_id": partida["partida_id"], **jogador} for jogador in partida["jogadores"]],
        )
        for jogador in partida["jogadores"]:
            if jogador["bot"]:
                continue  # bots não entram no ranking
            conexao.execute(
                text(
                    "INSERT INTO jogadores (usuario_id, nome, vitorias, partidas) VALUES (:usuario_id, :nome, :vitoria, 1) "
                    "ON CONFLICT (usuario_id) DO UPDATE SET nome = EXCLUDED.nome, "
                    "vitorias = jogadores.vitorias + EXCLUDED.vitorias, partidas = jogadores.partidas + 1"
                ),
                {
                    "usuario_id": jogador["usuario_id"],
                    "nome": jogador["nome"],
                    "vitoria": 1 if jogador["time"] == partida["vencedor_time"] else 0,
                },
            )
    return True


# ---------- Consultas ----------

# Posição de cada jogador. RANK() dá a mesma posição a quem empata em vitórias e pula as
# posições divididas (1, 2, 2, 4). ROW_NUMBER() numera as linhas sem repetir: é ele que corta as
# 10 primeiras. Dentro de um empate, a ordem é alfabética pelo nome (P5 do guia), e o id desempata
# nomes iguais, para a ordem não mudar de uma consulta para a outra.
SQL_CLASSIFICACAO = """
    SELECT RANK() OVER (ORDER BY vitorias DESC) AS posicao,
           ROW_NUMBER() OVER (ORDER BY vitorias DESC, lower(nome), usuario_id) AS linha,
           usuario_id, nome, vitorias, partidas
    FROM jogadores
"""


def ranking(usuario_id: str) -> list[dict]:
    """As TAMANHO_DO_RANKING primeiras linhas e, se o usuário logado estiver abaixo delas, também a
    linha dele, no fim: [{posicao, usuario_id, nome, vitorias, partidas}]. Quem nunca jogou não
    tem linha em jogadores, então não aparece."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                f"WITH classificacao AS ({SQL_CLASSIFICACAO}) "
                "SELECT posicao, usuario_id, nome, vitorias, partidas FROM classificacao "
                "WHERE linha <= :tamanho OR usuario_id = :usuario ORDER BY linha"
            ),
            {"tamanho": config.TAMANHO_DO_RANKING, "usuario": usuario_id},
        ).mappings()
        return [dict(linha) for linha in linhas]


def jogador(usuario_id: str) -> dict | None:
    """Estatísticas e últimas partidas do jogador, ou None se ele nunca jogou (formato na rota)."""
    with engine.connect() as conexao:
        linha = conexao.execute(
            text(
                f"WITH classificacao AS ({SQL_CLASSIFICACAO}) "
                "SELECT posicao, usuario_id, nome, vitorias, partidas FROM classificacao WHERE usuario_id = :usuario"
            ),
            {"usuario": usuario_id},
        ).mappings().first()
        if linha is None:
            return None
        partidas = [
            dict(p)
            for p in conexao.execute(
                text(
                    "SELECT p.partida_id, p.formato, p.encerrada_em, p.vencedor_time, p.placar_a, p.placar_b, eu.time "
                    "FROM participantes eu JOIN partidas p ON p.partida_id = eu.partida_id "
                    "WHERE eu.usuario_id = :usuario "
                    "ORDER BY p.encerrada_em DESC, p.partida_id LIMIT :limite"
                ),
                {"usuario": usuario_id, "limite": config.ULTIMAS_PARTIDAS},
            ).mappings()
        ]
        participantes = conexao.execute(
            text(
                "SELECT partida_id, assento, time, usuario_id, nome, bot FROM participantes "
                "WHERE partida_id = ANY(:partidas) ORDER BY assento"
            ),
            {"partidas": [p["partida_id"] for p in partidas]},
        ).mappings()
        times = {p["partida_id"]: {"A": [], "B": []} for p in partidas}
        for participante in participantes:
            times[participante["partida_id"]][participante["time"]].append(
                {chave: participante[chave] for chave in ("assento", "usuario_id", "nome", "bot")}
            )
    for partida in partidas:
        partida["encerrada_em"] = partida["encerrada_em"].astimezone(timezone.utc).isoformat()
        partida["times"] = times[partida["partida_id"]]
    return {**linha, "ultimas_partidas": partidas}


def banco_disponivel() -> bool:
    """Confere se o banco responde. Usada pela rota /saude."""
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
