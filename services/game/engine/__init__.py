"""Motor de regras do truco paulista, em Python puro: sem FastAPI, sem Redis e sem I/O.

O estado da partida é um dicionário que vira JSON sem conversão nenhuma (é assim que a camada
de serviço o guarda no Redis). As funções recebem o estado e devolvem um estado NOVO: o
recebido nunca é alterado. Uma ação que não vale lança ErroJogada, com o código e a mensagem
do protocolo (docs/guia-backend-mesa.md, seção 6.2), e o estado continua o mesmo.

    estado = criar_partida("p1", "sala-1", assentos, random.Random())
    estado = aplicar_acao(estado, 0, {"tipo": "jogar_carta", "carta": "7O", "coberta": False})
    mensagem = visao_do_jogador(estado, 1)  # o "estado" que o jogador do assento 1 recebe

O sorteio das cartas usa o gerador recebido (rng): a camada de serviço passa um
random.SystemRandom(), e os testes, um random.Random(semente), para repetir as mesmas mãos.

Módulos:
    cartas   baralho, manilha e força de cada carta
    regras   vencedor da rodada e da mão, com a regra de empate adotada
    partida  criação da partida, distribuição das mãos e as ações dos jogadores
    visao    o que cada jogador pode ver (a mensagem "estado")
"""

from engine.erros import AssentosInvalidos, ErroJogada
from engine.partida import aguardando_proxima_mao, aplicar_acao, criar_partida, iniciar_proxima_mao
from engine.visao import visao_do_jogador

__all__ = [
    "AssentosInvalidos",
    "ErroJogada",
    "aguardando_proxima_mao",
    "aplicar_acao",
    "criar_partida",
    "iniciar_proxima_mao",
    "visao_do_jogador",
]
