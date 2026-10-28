"""GET /api/ranking (docs/guia-backend-lobby.md, seções 3.10, 4.4 e 6.7)."""

from tests.conftest import Pessoa, bot, partida, publicar_e_esperar, vitoria


def pedir_ranking(cliente, pessoa):
    resposta = cliente.get("/api/ranking", headers=pessoa.headers)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def test_sem_partidas_o_ranking_e_vazio(cliente):
    assert pedir_ranking(cliente, Pessoa("Ana")) == []


def test_cada_partida_soma_partidas_para_todos_e_vitoria_para_o_time_vencedor(cliente, broker):
    ana, beto, caio, duda = Pessoa("Ana"), Pessoa("Beto"), Pessoa("Caio"), Pessoa("Duda")

    publicar_e_esperar(
        broker,
        vitoria(ana, beto),
        partida([caio.jogador(0), duda.jogador(2)], [beto.jogador(1), ana.jogador(3)], vencedor="B"),
    )

    assert pedir_ranking(cliente, ana) == [
        {"posicao": 1, "usuario_id": ana.id, "nome": "Ana", "vitorias": 2, "partidas": 2},
        {"posicao": 2, "usuario_id": beto.id, "nome": "Beto", "vitorias": 1, "partidas": 2},
        {"posicao": 3, "usuario_id": caio.id, "nome": "Caio", "vitorias": 0, "partidas": 1},
        {"posicao": 3, "usuario_id": duda.id, "nome": "Duda", "vitorias": 0, "partidas": 1},
    ]


def test_empate_divide_a_posicao_e_a_seguinte_pula_como_rank(cliente, broker):
    # O exemplo da seção 9.3 do guia: Ana, Beto e Duda com uma vitória; Caio com nenhuma.
    ana, beto, caio, duda = Pessoa("Ana"), Pessoa("Beto"), Pessoa("Caio"), Pessoa("Duda")

    publicar_e_esperar(
        broker,
        vitoria(ana, beto),
        partida([caio.jogador(0), bot(2)], [beto.jogador(1), duda.jogador(3)], vencedor="B"),
    )

    linhas = pedir_ranking(cliente, ana)
    assert [(l["posicao"], l["nome"], l["vitorias"], l["partidas"]) for l in linhas] == [
        (1, "Ana", 1, 1),
        (1, "Beto", 1, 2),
        (1, "Duda", 1, 1),
        (4, "Caio", 0, 1),
    ]


def test_bots_nao_aparecem_e_partidas_contra_bots_contam_para_os_humanos(cliente, broker):
    ana = Pessoa("Ana")

    publicar_e_esperar(
        broker,
        partida([ana.jogador(0)], [bot(1)], vencedor="A"),
        partida([ana.jogador(0), bot(2, "Bot 2")], [bot(1), bot(3, "Bot 3")], vencedor="B"),
    )

    assert pedir_ranking(cliente, ana) == [{"posicao": 1, "usuario_id": ana.id, "nome": "Ana", "vitorias": 1, "partidas": 2}]


def test_dez_primeiros_e_a_linha_de_quem_esta_abaixo_deles(cliente, broker):
    # 11 jogadores com uma vitória cada, contra o Caio, que fica em 12º (o laço da seção 9.3).
    caio = Pessoa("Caio")
    outros = [Pessoa(f"Extra {n:02d}") for n in range(11)]
    publicar_e_esperar(broker, *(vitoria(outro, caio) for outro in outros))

    do_caio = pedir_ranking(cliente, caio)
    assert len(do_caio) == 11
    assert [l["nome"] for l in do_caio[:10]] == [f"Extra {n:02d}" for n in range(10)]  # desempate pelo nome
    assert do_caio[10] == {"posicao": 12, "usuario_id": caio.id, "nome": "Caio", "vitorias": 0, "partidas": 11}

    # O 11º empata com o 10º em posição, mas fica de fora da lista de quem não é ele (P11).
    do_11 = pedir_ranking(cliente, outros[10])
    assert len(do_11) == 11 and do_11[10]["posicao"] == 1

    # Quem está entre os 10 primeiros, ou nunca jogou, recebe só os 10.
    assert len(pedir_ranking(cliente, outros[0])) == 10
    assert [l for l in pedir_ranking(cliente, Pessoa("Novo")) if l["nome"] == "Novo"] == []


def test_o_nome_e_o_da_partida_mais_recente(cliente, broker):
    ana, beto = Pessoa("Ana"), Pessoa("Beto")
    publicar_e_esperar(broker, vitoria(ana, beto))
    ana.nome = "Ana Maria"

    publicar_e_esperar(broker, vitoria(ana, beto))

    assert pedir_ranking(cliente, ana)[0]["nome"] == "Ana Maria"
