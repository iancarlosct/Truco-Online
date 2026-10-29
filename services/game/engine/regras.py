"""Quem vence cada rodada e cada mão, e quem abre a rodada seguinte.

Regra adotada para os empates (truco paulista). Ela varia de mesa para mesa, por isso fica
escrita aqui:

- Rodada: vence o time da carta mais forte. Se a carta mais forte de cada time tiver a mesma
  força, a rodada empata. Carta coberta não vale nada: perde para qualquer carta aberta, e
  duas cobertas empatam entre si.
- Quem abre a rodada seguinte é quem jogou a carta vencedora. Depois de um empate, abre quem
  abriu a rodada empatada.
- Mão, em melhor de 3: vence quem ganhar duas rodadas. Havendo empate, vence o time que ganhou
  a primeira rodada que não empatou:
      1ª empatada                  quem vencer a 2ª leva a mão (se a 2ª também empatar, a 3ª);
      1ª vencida e 2ª empatada     leva quem venceu a 1ª, e a 3ª nem é jogada;
      uma para cada e 3ª empatada  leva quem venceu a 1ª.
  Com as três rodadas empatadas, ninguém marca ponto, e a mão seguinte é distribuída como
  qualquer outra.
"""

from engine.cartas import FORCA_COBERTA, forca


def time_do_assento(assento: int) -> str:
    """Assentos pares formam o time A e ímpares o time B. No 2x2, os parceiros ficam frente a
    frente (0 e 2, 1 e 3), e a vez anda pela numeração dos assentos."""
    return "A" if assento % 2 == 0 else "B"


def outro_time(time: str) -> str:
    return "B" if time == "A" else "A"


def resultado_da_rodada(jogadas: list[dict], valor_da_manilha: str) -> tuple[str, int]:
    """Vencedor da rodada completa ("A", "B" ou "empate") e o assento que abre a próxima. Fora
    do empate, esse assento é o da carta vencedora. Se os dois parceiros jogam a carta mais
    forte do time com a mesma força, vale a que foi jogada primeiro.

    jogadas: [{"assento", "carta", "coberta"}], na ordem em que foram jogadas.
    """
    melhor = {}  # time -> (força, assento) da carta mais forte do time
    for jogada in jogadas:
        time = time_do_assento(jogada["assento"])
        valor = FORCA_COBERTA if jogada["coberta"] else forca(jogada["carta"], valor_da_manilha)
        if time not in melhor or valor > melhor[time][0]:
            melhor[time] = (valor, jogada["assento"])
    if melhor["A"][0] == melhor["B"][0]:
        return "empate", jogadas[0]["assento"]
    vencedor = "A" if melhor["A"][0] > melhor["B"][0] else "B"
    return vencedor, melhor[vencedor][1]


def resultado_da_mao(resultados: list[str]) -> str | None:
    """Vencedor da mão pelos resultados das rodadas jogadas até agora, na ordem.

    Devolve "A", "B", "empate" (as três rodadas empatadas: ninguém pontua) ou None, quando a
    mão continua.
    """
    for time in ("A", "B"):
        if resultados.count(time) >= 2:
            return time
    primeiro_vencedor = next((r for r in resultados if r != "empate"), None)
    if "empate" in resultados and primeiro_vencedor:
        return primeiro_vencedor
    if len(resultados) == 3:
        return "empate"
    return None
