"""Respostas de erro no formato do contrato: {"erro": "codigo", "mensagem": "texto"}.

É o mesmo formato do Auth e do Lobby. "mensagem" é mostrada pela tela ao jogador exatamente como
chega: o painel do ranking a mostra com um botão "Tentar de novo".
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Código -> (status HTTP, mensagem).
ERROS = {
    "token_invalido": (401, "Sessão inválida. Entre de novo."),
    "token_expirado": (401, "Sua sessão expirou. Entre de novo."),
    "jogador_nao_encontrado": (404, "Este jogador ainda não tem partidas registradas."),
}


class ErroRanking(Exception):
    """Erro de regra. As rotas fazem raise ErroRanking("codigo") e o tratador abaixo responde no
    formato do contrato, com o status da tabela ERROS."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo
        self.status, self.mensagem = ERROS[codigo]


def erro(status: int, codigo: str, mensagem: str, headers: dict | None = None) -> JSONResponse:
    """Resposta de erro pronta, com o status HTTP indicado."""
    return JSONResponse(status_code=status, content={"erro": codigo, "mensagem": mensagem}, headers=headers)


# Erros que o próprio FastAPI gera, por status: código e mensagem do contrato.
ERROS_HTTP = {
    404: ("nao_encontrado", "Endereço não encontrado."),
    405: ("metodo_nao_permitido", "Operação não permitida neste endereço."),
}


def registrar_tratadores(app: FastAPI) -> None:
    """Troca as respostas de erro padrão do FastAPI ({"detail": ...}) pelo formato do contrato."""

    @app.exception_handler(ErroRanking)
    def erro_ranking(request: Request, exc: ErroRanking) -> JSONResponse:
        return erro(exc.status, exc.codigo, exc.mensagem)

    # As rotas do Ranking não recebem corpo; este tratador cobre um parâmetro fora do formato.
    @app.exception_handler(RequestValidationError)
    def dados_invalidos(request: Request, exc: RequestValidationError) -> JSONResponse:
        return erro(422, "dados_invalidos", "Dados inválidos.")

    # Rota inexistente (404), método errado (405) e qualquer HTTPException.
    @app.exception_handler(StarletteHTTPException)
    def erro_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo, mensagem = ERROS_HTTP.get(exc.status_code, ("erro_http", "Não foi possível concluir a operação."))
        return erro(exc.status_code, codigo, mensagem, headers=exc.headers)

    # Erro inesperado no código (um bug, ou o banco fora do ar). O detalhe fica no log do
    # container (docker compose logs ranking).
    @app.exception_handler(Exception)
    def erro_interno(request: Request, exc: Exception) -> JSONResponse:
        return erro(500, "erro_interno", "Ocorreu um erro no servidor. Tente de novo em instantes.")
