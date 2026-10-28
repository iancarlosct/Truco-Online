"""Acesso ao banco do Lobby (container lobby-db). Só este serviço conecta nele.

Usa o SQLAlchemy 2 com o driver psycopg 3, escrevendo o SQL à mão com text(), como o Auth: as
tabelas e as consultas são as da seção 7 do docs/guia-backend-lobby.md. Os dados entram sempre
como parâmetros (:sala, :usuario...), nunca juntando textos, para evitar injeção de SQL.

Tabelas:
    salas              uma linha por sala: formato, dono, status e partida_id.
    assentos           2 ou 4 linhas por sala. Além dos campos do contrato, guardam o nível do bot
                       e a hora do último GET da sala feito pelo jogador sentado (visto_em, a
                       presença). Esses dois não vão nas respostas.
    eventos_pendentes  os bot.solicitado que ainda não chegaram ao broker (eventos.py). Entram na
                       mesma transação que passa a sala para "em_partida": ou os dois ficam
                       gravados, ou nenhum.

Pedidos ao mesmo tempo (guia, 6.8): toda alteração roda numa transação que trava primeiro o
usuário (pg_advisory_xact_lock) e depois a linha da sala (SELECT ... FOR UPDATE). As travas são
soltas sozinhas no fim da transação. Assim duas pessoas não sentam no mesmo assento, e duas abas
do mesmo usuário não o põem em duas salas.
"""

import json
import uuid
from contextlib import contextmanager

from sqlalchemy import URL, Connection, create_engine, text
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

# Criadas pelo próprio serviço, toda vez que ele sobe, com "IF NOT EXISTS": na primeira vez cria,
# nas outras não faz nada e não mexe nos dados. É a mesma escolha do Auth (explicação completa em
# services/auth/app/banco.py): uma mudança de estrutura pede um ALTER TABLE à mão ou recriar o
# banco (docker compose down -v, que apaga as salas).
SQL_CRIAR_TABELAS = [
    """
    CREATE TABLE IF NOT EXISTS salas (
        id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
        formato    TEXT        NOT NULL CHECK (formato IN ('1x1', '2x2')),
        dono_id    TEXT        NOT NULL,
        status     TEXT        NOT NULL DEFAULT 'aguardando'
                               CHECK (status IN ('aguardando', 'em_partida', 'encerrada')),
        partida_id TEXT        UNIQUE,
        criada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS assentos (
        sala_id    UUID        NOT NULL REFERENCES salas (id),
        assento    SMALLINT    NOT NULL CHECK (assento BETWEEN 0 AND 3),
        usuario_id TEXT,
        nome       VARCHAR(20),
        bot        BOOLEAN     NOT NULL DEFAULT false,
        nivel      TEXT,
        visto_em   TIMESTAMPTZ,
        PRIMARY KEY (sala_id, assento)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS eventos_pendentes (
        id        BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        nome      TEXT        NOT NULL,
        dados     TEXT        NOT NULL,  -- o evento em JSON, exatamente como vai para o broker
        criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # A lista mostra só as salas abertas, da mais antiga para a mais nova.
    "CREATE INDEX IF NOT EXISTS salas_aguardando ON salas (criada_em) WHERE status = 'aguardando'",
    # Regra de uma sala por vez: em que salas o usuário está sentado.
    "CREATE INDEX IF NOT EXISTS assentos_usuario ON assentos (usuario_id) WHERE usuario_id IS NOT NULL",
]


def criar_tabelas() -> None:
    # engine.begin() abre uma transação e confirma (commit) ao sair do bloco.
    with engine.begin() as conexao:
        for comando in SQL_CRIAR_TABELAS:
            conexao.execute(text(comando))


# ---------- Transação de uma alteração ----------


@contextmanager
def transacao(usuario_id: str):
    """Transação de uma alteração pedida por um usuário (criar, entrar, sair, bot, DELETE,
    iniciar). Começa travando pelo usuário: dois pedidos dele esperam um pelo outro, o que
    protege a regra de uma sala por vez, que envolve salas diferentes. A sala é travada depois,
    por buscar_sala(..., travar=True). O commit acontece ao sair do bloco, antes de a rota
    responder; um erro no meio desfaz tudo (rollback)."""
    with engine.begin() as conexao:
        conexao.execute(text("SELECT pg_advisory_xact_lock(hashtext(:usuario))"), {"usuario": usuario_id})
        yield conexao


# ---------- Leitura ----------
# Uma sala é devolvida como dicionário: {id, formato, dono_id, status, partida_id, assentos}, com
# os assentos em ordem: [{assento, usuario_id, nome, bot, nivel}]. O id vem do Postgres como
# uuid.UUID; quem responde à tela o converte com str().

COLUNAS_DA_SALA = "s.id, s.formato, s.dono_id, s.status, s.partida_id"
COLUNAS_DO_ASSENTO = "a.assento, a.usuario_id, a.nome, a.bot, a.nivel"


def buscar_sala(conexao: Connection, sala_id: uuid.UUID, travar: bool = False) -> dict | None:
    """A sala com os assentos, ou None. Com travar=True, trava a linha da sala até o fim da
    transação: outro pedido para a mesma sala espera esta transação terminar."""
    sql = f"SELECT {COLUNAS_DA_SALA} FROM salas s WHERE s.id = :sala"
    if travar:
        sql += " FOR UPDATE"
    sala = conexao.execute(text(sql), {"sala": sala_id}).mappings().first()
    if sala is None:
        return None
    assentos = conexao.execute(
        text(f"SELECT {COLUNAS_DO_ASSENTO} FROM assentos a WHERE a.sala_id = :sala ORDER BY a.assento"),
        {"sala": sala_id},
    ).mappings()
    return {**sala, "assentos": [dict(a) for a in assentos]}


def salas_aguardando() -> list[dict]:
    """As salas "aguardando", da mais antiga para a mais nova, numa consulta só."""
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                f"SELECT {COLUNAS_DA_SALA}, {COLUNAS_DO_ASSENTO} "
                "FROM salas s JOIN assentos a ON a.sala_id = s.id "
                "WHERE s.status = 'aguardando' "
                "ORDER BY s.criada_em, s.id, a.assento"
            )
        ).mappings()
        salas: dict[uuid.UUID, dict] = {}  # o dicionário mantém a ordem de chegada
        for linha in linhas:
            sala = salas.setdefault(
                linha["id"],
                {chave: linha[chave] for chave in ("id", "formato", "dono_id", "status", "partida_id")}
                | {"assentos": []},
            )
            sala["assentos"].append({chave: linha[chave] for chave in ("assento", "usuario_id", "nome", "bot", "nivel")})
    return list(salas.values())


def sala_aberta_do_usuario(conexao: Connection, usuario_id: str) -> uuid.UUID | None:
    """Id da sala "aguardando" em que o usuário está sentado. Pela regra, há no máximo uma."""
    return conexao.execute(
        text(
            "SELECT a.sala_id FROM assentos a JOIN salas s ON s.id = a.sala_id "
            "WHERE s.status = 'aguardando' AND a.usuario_id = :usuario LIMIT 1"
        ),
        {"usuario": usuario_id},
    ).scalar()


# ---------- Alterações (sempre dentro de uma transação aberta pela rota) ----------


def inserir_sala(conexao: Connection, formato: str, dono: dict) -> uuid.UUID:
    """Cria a sala com os assentos vazios e senta o dono no assento 0. Devolve o id."""
    sala_id = conexao.execute(
        text("INSERT INTO salas (formato, dono_id) VALUES (:formato, :dono) RETURNING id"),
        {"formato": formato, "dono": dono["id"]},
    ).scalar_one()
    conexao.execute(
        text("INSERT INTO assentos (sala_id, assento) VALUES (:sala, :assento)"),
        [{"sala": sala_id, "assento": numero} for numero in range(config.ASSENTOS_POR_FORMATO[formato])],
    )
    sentar(conexao, sala_id, 0, dono)
    return sala_id


def sentar(conexao: Connection, sala_id: uuid.UUID, assento: int, usuario: dict) -> None:
    """Senta o jogador, com o nome do token. O prazo da presença começa agora (guia, P9)."""
    conexao.execute(
        text(
            "UPDATE assentos SET usuario_id = :usuario, nome = :nome, bot = false, nivel = NULL, "
            "visto_em = now() WHERE sala_id = :sala AND assento = :assento"
        ),
        {"sala": sala_id, "assento": assento, "usuario": usuario["id"], "nome": usuario["nome"]},
    )


def por_bot(conexao: Connection, sala_id: uuid.UUID, assento: int, nome: str, nivel: str) -> None:
    """Bot no assento: usuario_id nulo, bot verdadeiro, o nome "Bot N" e o nível."""
    conexao.execute(
        text(
            "UPDATE assentos SET usuario_id = NULL, nome = :nome, bot = true, nivel = :nivel, "
            "visto_em = NULL WHERE sala_id = :sala AND assento = :assento"
        ),
        {"sala": sala_id, "assento": assento, "nome": nome, "nivel": nivel},
    )


def vagar(conexao: Connection, sala_id: uuid.UUID, assento: int) -> None:
    conexao.execute(
        text(
            "UPDATE assentos SET usuario_id = NULL, nome = NULL, bot = false, nivel = NULL, "
            "visto_em = NULL WHERE sala_id = :sala AND assento = :assento"
        ),
        {"sala": sala_id, "assento": assento},
    )


def marcar_em_partida(conexao: Connection, sala_id: uuid.UUID, partida_id: str) -> None:
    conexao.execute(
        text("UPDATE salas SET status = 'em_partida', partida_id = :partida WHERE id = :sala"),
        {"sala": sala_id, "partida": partida_id},
    )


def encerrar_sala(conexao: Connection, sala_id: uuid.UUID) -> None:
    """O dono saiu (pelo /sair ou pela presença): a sala some da lista e para de aceitar ações."""
    conexao.execute(text("UPDATE salas SET status = 'encerrada' WHERE id = :sala"), {"sala": sala_id})


def renovar_presenca(conexao: Connection, sala_id: uuid.UUID, usuario_id: str) -> None:
    """O jogador sentado pediu a sala: o prazo de 60 segundos recomeça."""
    conexao.execute(
        text("UPDATE assentos SET visto_em = now() WHERE sala_id = :sala AND usuario_id = :usuario"),
        {"sala": sala_id, "usuario": usuario_id},
    )


# ---------- Presença ----------


def ausentes(conexao: Connection) -> list[dict]:
    """Jogadores sentados em salas "aguardando" sem pedir a sala há mais de PRAZO_PRESENCA
    segundos: [{sala_id, dono_id, assento, usuario_id}].

    Trava as salas deles até o fim da transação. Uma sala que outra transação está alterando
    (SKIP LOCKED) fica para a próxima conferência, em vez de fazer este pedido esperar: a
    conferência roda no começo de toda requisição, e um /iniciar esperando o Game seguraria todas.
    O now() do Postgres é a hora do começo da transação; para comparar com 60 segundos, basta."""
    return [
        dict(linha)
        for linha in conexao.execute(
            text(
                "SELECT a.sala_id, s.dono_id, a.assento, a.usuario_id "
                "FROM assentos a JOIN salas s ON s.id = a.sala_id "
                "WHERE s.status = 'aguardando' AND a.usuario_id IS NOT NULL "
                "AND a.visto_em < now() - make_interval(secs => :prazo) "
                "ORDER BY a.sala_id, a.assento "
                "FOR UPDATE OF s SKIP LOCKED"
            ),
            {"prazo": config.PRAZO_PRESENCA},
        ).mappings()
    ]


# ---------- Eventos ----------


def guardar_evento(conexao: Connection, nome: str, dados: dict) -> None:
    """Põe um evento na fila de entrega ao broker, dentro da transação da rota."""
    conexao.execute(
        text("INSERT INTO eventos_pendentes (nome, dados) VALUES (:nome, :dados)"),
        {"nome": nome, "dados": json.dumps(dados, ensure_ascii=False)},
    )


def proximo_evento() -> dict | None:
    """O evento mais antigo da fila: {id, nome, dados (texto em JSON)}, ou None com a fila vazia."""
    with engine.connect() as conexao:
        linha = conexao.execute(
            text("SELECT id, nome, dados FROM eventos_pendentes ORDER BY id LIMIT 1")
        ).mappings().first()
    return dict(linha) if linha else None


def apagar_evento(evento_id: int) -> None:
    with engine.begin() as conexao:
        conexao.execute(text("DELETE FROM eventos_pendentes WHERE id = :id"), {"id": evento_id})


def encerrar_sala_da_partida(partida_id: str) -> bool:
    """partida.finalizada: a sala da partida passa a "encerrada". Devolve True se mudou alguma.

    Idempotente pelo partida_id: o mesmo evento de novo não acha mais a sala "em_partida" e não
    muda nada. Uma partida que não saiu de uma sala (a do script de teste do Game) também não."""
    with engine.begin() as conexao:
        resultado = conexao.execute(
            text("UPDATE salas SET status = 'encerrada' WHERE partida_id = :partida AND status = 'em_partida'"),
            {"partida": partida_id},
        )
    return resultado.rowcount > 0


def banco_disponivel() -> bool:
    """Confere se o banco responde. Usada pela rota /saude."""
    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
