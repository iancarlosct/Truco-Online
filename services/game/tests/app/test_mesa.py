"""WebSocket da mesa: recusas, visão de cada jogador, ações, reconexão, conexão substituída,
pausa entre as mãos e fim da partida (docs/guia-backend-mesa.md)."""

import logging
from datetime import timedelta

import pytest
from starlette.websockets import WebSocketDisconnect

from app.seguranca import SemTokenNoLog
from tests.app.conftest import (
    ANA,
    ASSENTOS_1X1,
    BETO,
    CAIO,
    conectar,
    criar_partida,
    eventos_do_stream,
    ler_partida,
    preparar_partida,
    token,
)

VIRA = "AO"  # manilha 2
MAOS = [["3O", "3E", "4O"], ["4C", "5C", "6C"]]  # Ana (assento 0) vence em duas rodadas


def fechamento(cliente, partida_id, **conexao):
    """Conecta e devolve o código e o motivo com que o servidor fechou a conexão."""
    with conectar(cliente, partida_id, **conexao) as ws:
        with pytest.raises(WebSocketDisconnect) as fechou:
            ws.receive_json()
    return fechou.value.code, fechou.value.reason


def jogar(ws, carta, coberta=False):
    ws.send_json({"tipo": "jogar_carta", "carta": carta, "coberta": coberta})


# ---------- Recusas: 4401, 4403 e 4404 ----------


@pytest.mark.parametrize(
    "token_pronto",
    [
        "isto-nao-e-um-token",
        token(ANA, validade=timedelta(seconds=-1)),  # vencido
        token(ANA, segredo="outro-segredo-" + "x" * 32),
    ],
    ids=["malformado", "vencido", "outro-segredo"],
)
def test_token_invalido_fecha_com_4401(cliente, token_pronto):
    partida_id = criar_partida(cliente)
    assert fechamento(cliente, partida_id, token_pronto=token_pronto) == (4401, "token inválido")


def test_o_token_nao_aparece_no_log_da_conexao():
    # A mesma linha que o Uvicorn escreve a cada conexão WebSocket.
    registro = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 0, '%s - "WebSocket %s" [accepted]',
        ("172.18.0.5:41234", "/ws/partidas/p1?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbmEifQ.assinatura"), None,
    )
    assert SemTokenNoLog().filter(registro) is True
    assert registro.getMessage() == '172.18.0.5:41234 - "WebSocket /ws/partidas/p1?token=***" [accepted]'


def test_sem_token_fecha_com_4401(cliente):
    partida_id = criar_partida(cliente)
    with cliente.websocket_connect(f"/ws/partidas/{partida_id}") as ws:
        with pytest.raises(WebSocketDisconnect) as fechou:
            ws.receive_json()
    assert fechou.value.code == 4401


def test_partida_inexistente_fecha_com_4404(cliente):
    assert fechamento(cliente, "nao-existe", sub=ANA) == (4404, "partida inexistente")


def test_usuario_fora_da_partida_fecha_com_4403(cliente):
    partida_id = criar_partida(cliente)
    assert fechamento(cliente, partida_id, sub=CAIO) == (4403, "não pertence à partida")


# ---------- Visão de cada jogador ----------


def test_ao_conectar_cada_um_recebe_o_estado_na_sua_visao(cliente, banco):
    partida_id = criar_partida(cliente)
    estado = ler_partida(banco, partida_id)

    with conectar(cliente, partida_id, BETO) as ws:
        visao = ws.receive_json()

    assert visao["tipo"] == "estado"
    assert visao["status"] == "em_andamento"
    assert visao["meu_assento"] == 1
    assert visao["jogadores"][1]["mao"] == estado["jogadores"][1]["mao"]
    assert "mao" not in visao["jogadores"][0]
    assert visao["jogadores"][0]["qtd_cartas"] == 3
    assert visao["mao_atual"]["vez_assento"] == 0
    assert visao["chat"] == []


# ---------- Ações ----------


def test_jogada_valida_vai_para_todos_e_a_recusada_so_para_quem_enviou(cliente, banco):
    partida_id = criar_partida(cliente)
    preparar_partida(banco, partida_id, MAOS, VIRA)

    with conectar(cliente, partida_id, ANA) as ana, conectar(cliente, partida_id, BETO) as beto:
        ana.receive_json()
        beto.receive_json()

        jogar(beto, "4C")  # fora da vez
        assert beto.receive_json() == {"tipo": "erro", "codigo": "fora_da_vez", "mensagem": "Não é a sua vez."}

        jogar(ana, "3O")
        para_ana, para_beto = ana.receive_json(), beto.receive_json()
        # A próxima mensagem da Ana é o estado depois da jogada: o erro do Beto não chegou a ela.
        assert para_ana["tipo"] == para_beto["tipo"] == "estado"
        assert para_ana["mao_atual"]["rodadas"] == [
            {"jogadas": [{"assento": 0, "carta": "3O", "coberta": False}], "vencedor_time": None, "vencedor_assento": None}
        ]
        assert para_ana["jogadores"][0]["mao"] == ["3E", "4O"]
        assert para_beto["jogadores"][0] == {"assento": 0, "nome": "Ana", "time": "A", "bot": False, "qtd_cartas": 2}
        assert para_beto["mao_atual"]["vez_assento"] == 1


def test_mensagem_malformada_recebe_erro_e_a_conexao_continua(cliente):
    partida_id = criar_partida(cliente)

    with conectar(cliente, partida_id, ANA) as ws:
        ws.receive_json()
        ws.send_text("isto não é json")
        assert ws.receive_json() == {
            "tipo": "erro",
            "codigo": "acao_invalida",
            "mensagem": "A mensagem não é um JSON válido.",
        }
        ws.send_json({"tipo": "inventado"})
        assert ws.receive_json()["codigo"] == "acao_invalida"
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["codigo"] == "acao_invalida"

        ws.send_json({"tipo": "chat", "texto": "  ainda estou aqui  "})
        assert ws.receive_json()["chat"] == [{"de": "Ana", "texto": "ainda estou aqui"}]


def test_fim_da_mao_sai_na_hora_e_a_proxima_mao_vem_depois_da_pausa(cliente, banco, monkeypatch):
    # Pausa maior que a dos outros testes, para dar tempo de tentar jogar durante ela.
    monkeypatch.setattr("app.config.PAUSA_ENTRE_MAOS", 0.5)
    partida_id = criar_partida(cliente)
    preparar_partida(banco, partida_id, MAOS, VIRA)

    with conectar(cliente, partida_id, ANA) as ana, conectar(cliente, partida_id, BETO) as beto:
        ana.receive_json()
        beto.receive_json()
        for ws, carta in [(ana, "3O"), (beto, "4C"), (ana, "3E")]:
            jogar(ws, carta)
            ana.receive_json()
            beto.receive_json()
        jogar(beto, "5C")

        fim_da_mao, fim_para_beto = ana.receive_json(), beto.receive_json()
        for visao in (fim_da_mao, fim_para_beto):
            assert visao["placar"] == {"A": 1, "B": 0}
            assert visao["mao_atual"]["vez_assento"] is None
            assert len(visao["mao_atual"]["rodadas"]) == 2
            assert visao["mao_atual"]["rodadas"][1]["vencedor_time"] == "A"

        # Durante a pausa, jogar é recusado.
        jogar(ana, "4O")
        assert ana.receive_json()["mensagem"] == "A mão terminou. Aguarde a próxima."

        proxima = ana.receive_json()
        assert proxima["mao_atual"]["numero"] == 2
        assert proxima["mao_atual"]["rodadas"] == []
        assert proxima["mao_atual"]["vez_assento"] == 1  # o pé passou para o assento 0
        assert len(proxima["jogadores"][0]["mao"]) == 3
        assert beto.receive_json()["mao_atual"]["numero"] == 2


def test_fim_da_partida_sai_na_hora_com_o_vencedor_e_publica_partida_finalizada(cliente, banco, broker):
    partida_id = criar_partida(cliente)
    preparar_partida(banco, partida_id, MAOS, VIRA, placar={"A": 10, "B": 4})

    with conectar(cliente, partida_id, ANA) as ana, conectar(cliente, partida_id, BETO) as beto:
        ana.receive_json()
        beto.receive_json()
        ana.send_json({"tipo": "pedir_truco"})
        ana.receive_json()
        beto.receive_json()
        beto.send_json({"tipo": "responder_truco", "resposta": "aceitar"})
        assert ana.receive_json()["mao_atual"]["valor"] == 3
        beto.receive_json()
        for ws, carta in [(ana, "3O"), (beto, "4C"), (ana, "3E"), (beto, "5C")]:
            jogar(ws, carta)
            ultimo = ana.receive_json()
            beto.receive_json()

        assert ultimo["status"] == "encerrada"
        assert ultimo["vencedor_time"] == "A"
        assert ultimo["placar"] == {"A": 12, "B": 4}
        assert ultimo["mao_atual"]["vez_assento"] is None
        assert ultimo["mao_atual"]["numero"] == 1  # não há mão nova

        # Depois do fim, só o chat vale.
        jogar(beto, "6C")
        assert beto.receive_json()["mensagem"] == "A partida já terminou."
        beto.send_json({"tipo": "chat", "texto": "boa partida"})
        assert ana.receive_json()["chat"][-1] == {"de": "Beto", "texto": "boa partida"}

    [evento] = eventos_do_stream(broker, "partida.finalizada")
    estado = ler_partida(banco, partida_id)
    assert evento == {
        "partida_id": partida_id,
        "sala_id": "sala-1",
        "formato": "1x1",
        "times": {
            "A": [{"assento": 0, "usuario_id": ANA, "nome": "Ana", "bot": False}],
            "B": [{"assento": 1, "usuario_id": BETO, "nome": "Beto", "bot": False}],
        },
        "vencedor_time": "A",
        "placar_final": {"A": 12, "B": 4},
        "encerrada_em": estado["encerrada_em"],
    }

    # Quem conectar depois recebe o mesmo estado encerrado.
    with conectar(cliente, partida_id, BETO) as ws:
        assert ws.receive_json()["status"] == "encerrada"


# ---------- Queda, reconexão e conexão substituída ----------


def test_jogador_que_cai_recebe_o_estado_atual_ao_voltar(cliente, banco):
    partida_id = criar_partida(cliente)
    preparar_partida(banco, partida_id, MAOS, VIRA)

    with conectar(cliente, partida_id, ANA) as ana:
        ana.receive_json()
        with conectar(cliente, partida_id, BETO) as beto:
            beto.receive_json()
        # O Beto caiu. A partida espera por ele, e a Ana continua jogando a vez dela.
        jogar(ana, "3O")
        assert ana.receive_json()["mao_atual"]["vez_assento"] == 1

        with conectar(cliente, partida_id, BETO) as beto:
            volta = beto.receive_json()
            assert volta["meu_assento"] == 1
            assert volta["mao_atual"]["rodadas"][0]["jogadas"] == [{"assento": 0, "carta": "3O", "coberta": False}]
            assert volta["mao_atual"]["vez_assento"] == 1
            jogar(beto, "4C")
            assert beto.receive_json()["mao_atual"]["rodadas"][0]["vencedor_time"] == "A"
            assert ana.receive_json()["mao_atual"]["vez_assento"] == 0


def test_segunda_conexao_do_mesmo_jogador_substitui_a_primeira_que_fecha_com_4409(cliente):
    partida_id = criar_partida(cliente)

    with conectar(cliente, partida_id, ANA) as primeira:
        primeira.receive_json()
        with conectar(cliente, partida_id, ANA) as segunda:
            segunda.receive_json()
            with pytest.raises(WebSocketDisconnect) as fechou:
                primeira.receive_json()
            assert (fechou.value.code, fechou.value.reason) == (4409, "conexão substituída")

            # A nova conexão continua valendo.
            segunda.send_json({"tipo": "chat", "texto": "aba nova"})
            assert segunda.receive_json()["chat"] == [{"de": "Ana", "texto": "aba nova"}]


# ---------- Bots ----------


def test_bot_conecta_com_token_proprio_so_no_assento_de_bot_da_partida(cliente):
    assentos = [ASSENTOS_1X1[0], {"assento": 1, "usuario_id": None, "nome": "Bot 1", "bot": True}]
    partida_id = criar_partida(cliente, assentos)
    outra_partida = criar_partida(cliente)

    with conectar(cliente, partida_id, f"bot-{partida_id}-1") as bot:
        visao = bot.receive_json()
    assert visao["meu_assento"] == 1
    assert visao["jogadores"][1]["bot"] is True

    assert fechamento(cliente, partida_id, sub=f"bot-{partida_id}-0")[0] == 4403  # assento de jogador
    assert fechamento(cliente, partida_id, sub=f"bot-{outra_partida}-1")[0] == 4403  # outra partida
    assert fechamento(cliente, partida_id, sub=f"bot-{partida_id}-7")[0] == 4403  # assento que não existe
