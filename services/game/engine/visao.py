"""O que cada jogador pode ver: a mensagem "estado" (docs/guia-backend-mesa.md, seções 4.1 e 4.3).

- "meu_assento" é o assento de quem recebe.
- "mao" só vai no item do próprio jogador. Na mão de onze, o time com 11 vê também a mão do
  parceiro (2x2). As cartas dos outros nunca saem do servidor.
- "qtd_cartas" vai em todos os itens.
- Carta coberta vai como {"carta": None, "coberta": True}, para todos, em todas as rodadas.
- Só saem os campos do protocolo: nada de baralho, usuario_id, sala_id ou campos internos.
"""

from engine.regras import time_do_assento


def visao_do_jogador(estado: dict, assento: int) -> dict:
    """Monta a mensagem "estado" para o jogador deste assento. Devolve um dicionário novo, que
    não divide nenhuma lista com o estado guardado."""
    mao = estado["mao_atual"]
    meu_time = time_do_assento(assento)
    ve_parceiro = mao["tipo"] == "mao_de_onze" and estado["placar"][meu_time] == 11

    jogadores = []
    for jogador in estado["jogadores"]:
        item = {
            "assento": jogador["assento"],
            "nome": jogador["nome"],
            "time": jogador["time"],
            "bot": jogador["bot"],
            "qtd_cartas": len(jogador["mao"]),
        }
        if jogador["assento"] == assento or (ve_parceiro and jogador["time"] == meu_time):
            item["mao"] = list(jogador["mao"])
        jogadores.append(item)

    visao = {
        "tipo": "estado",
        "partida_id": estado["partida_id"],
        "formato": estado["formato"],
        "status": estado["status"],
        "meu_assento": assento,
        "jogadores": jogadores,
        "placar": dict(estado["placar"]),
        "mao_atual": {
            "numero": mao["numero"],
            "pe": mao["pe"],
            "vira": mao["vira"],
            "valor": mao["valor"],
            "tipo": mao["tipo"],
            "truco_pendente": dict(mao["truco_pendente"]) if mao["truco_pendente"] else None,
            "ultimo_aumento_time": mao["ultimo_aumento_time"],
            "aguardando_decisao_mao_de_onze": mao["aguardando_decisao_mao_de_onze"],
            "rodadas": [
                {
                    "jogadas": [
                        {
                            "assento": jogada["assento"],
                            "carta": None if jogada["coberta"] else jogada["carta"],
                            "coberta": jogada["coberta"],
                        }
                        for jogada in rodada["jogadas"]
                    ],
                    "vencedor_time": rodada["vencedor_time"],
                    # .get: uma partida gravada antes de o campo existir não o tem nas rodadas.
                    "vencedor_assento": rodada.get("vencedor_assento"),
                }
                for rodada in mao["rodadas"]
            ],
            "vez_assento": mao["vez_assento"],
        },
        "chat": [dict(mensagem) for mensagem in estado["chat"]],
    }
    if estado["status"] == "encerrada":
        visao["vencedor_time"] = estado["vencedor_time"]
    return visao
