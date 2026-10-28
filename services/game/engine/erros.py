"""Erros do motor."""


class ErroJogada(Exception):
    """Ação recusada. Vira a mensagem {"tipo": "erro", "codigo", "mensagem"}, enviada só a quem
    fez a ação (docs/guia-backend-mesa.md, seção 6.2).

    Códigos: fora_da_vez, carta_invalida, nao_autorizado e acao_invalida. A mensagem é mostrada
    ao jogador como chega: em português, curta, sem nomes internos.
    """

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class AssentosInvalidos(ValueError):
    """A lista de assentos recebida para criar a partida não forma uma mesa válida."""
