"""Ajudantes dos testes da estratégia: estados montados à mão, no formato da mensagem "estado"
que o Game envia ao assento do bot (docs/guia-backend-mesa.md, seção 4)."""


class Sorteio:
    """Faz o papel do random.Random do bot, com o resultado escolhido pelo teste: com 0.0, todo
    sorteio de blefe sai; com 0.99, nenhum."""

    def __init__(self, valor):
        self.valor = valor

    def random(self):
        return self.valor


SEM_BLEFE = Sorteio(0.99)
SEMPRE_BLEFA = Sorteio(0.0)


def rodada(*jogadas, vencedor=None):
    """Uma rodada de "rodadas". Cada jogada é (assento, carta); carta None é uma coberta."""
    return {
        "jogadas": [{"assento": a, "carta": c, "coberta": c is None} for a, c in jogadas],
        "vencedor_time": vencedor,
    }


def estado(
    mao,
    vira="4O",
    meu=0,
    vez="meu",
    formato="1x1",
    rodadas=(),
    placar=(0, 0),
    valor=1,
    tipo="normal",
    truco=None,
    ultimo=None,
    aguardando=False,
    bots=None,
    mao_parceiro=None,
    status="em_andamento",
):
    """Estado na visão do assento "meu", com a vez nele, a menos que "vez" diga outro assento (ou
    None, a pausa entre as mãos).

    truco: o time que fez o pedido pendente ("A" ou "B"), com o valor proposto seguinte a "valor".
    bots: assentos de bot. Sem ele, só o próprio assento é bot.
    mao_parceiro: no 2x2, as cartas do parceiro que a mão de onze mostra.
    """
    quantidade = 2 if formato == "1x1" else 4
    bots = {meu} if bots is None else set(bots)
    jogadores = []
    for assento in range(quantidade):
        item = {
            "assento": assento,
            "nome": f"Jogador {assento}",
            "time": "A" if assento % 2 == 0 else "B",
            "bot": assento in bots,
            "qtd_cartas": 3,
        }
        if assento == meu:
            item["mao"], item["qtd_cartas"] = list(mao), len(mao)
        elif mao_parceiro and assento == (meu + 2) % quantidade:
            item["mao"], item["qtd_cartas"] = list(mao_parceiro), len(mao_parceiro)
        jogadores.append(item)
    proximo = {1: 3, 3: 6, 6: 9, 9: 12}
    return {
        "tipo": "estado",
        "partida_id": "p1",
        "formato": formato,
        "status": status,
        "meu_assento": meu,
        "jogadores": jogadores,
        "placar": {"A": placar[0], "B": placar[1]},
        "mao_atual": {
            "numero": 1,
            "pe": quantidade - 1,
            "vira": vira,
            "valor": valor,
            "tipo": tipo,
            "truco_pendente": {"pedido_por_time": truco, "valor_proposto": proximo[valor]} if truco else None,
            "ultimo_aumento_time": ultimo,
            "aguardando_decisao_mao_de_onze": aguardando,
            "rodadas": [dict(r) for r in rodadas],
            "vez_assento": meu if vez == "meu" else vez,
        },
        "chat": [],
    }
