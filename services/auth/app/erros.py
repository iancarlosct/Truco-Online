"""Respostas de erro no formato do contrato: {"erro": "codigo", "mensagem": "texto"}.

"erro" é um código fixo, para programas. "mensagem" é mostrada pela tela ao usuário exatamente
como chega: em português, curta, sem nome de exceção, tabela ou campo interno.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


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

    # Corpo fora do esperado: JSON quebrado, campo faltando, número no lugar de texto. Sem este
    # tratador, o FastAPI responderia 422 com {"detail": [...]}, e a tela não teria mensagem.
    @app.exception_handler(RequestValidationError)
    def corpo_invalido(request: Request, exc: RequestValidationError) -> JSONResponse:
        return erro(422, "dados_invalidos", "Dados inválidos. Confira os campos e tente de novo.")

    # Rota inexistente (404), método errado (405) e qualquer HTTPException.
    @app.exception_handler(StarletteHTTPException)
    def erro_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo, mensagem = ERROS_HTTP.get(exc.status_code, ("erro_http", "Não foi possível concluir a operação."))
        # Os cabeçalhos seguem junto (o 405, por exemplo, diz no "Allow" quais métodos valem).
        return erro(exc.status_code, codigo, mensagem, headers=exc.headers)

    # Erro inesperado no código (um bug, ou o banco fora do ar). O usuário recebe uma mensagem
    # genérica; o detalhe (a exceção completa) o Uvicorn escreve no log do container
    # (docker compose logs auth).
    @app.exception_handler(Exception)
    def erro_interno(request: Request, exc: Exception) -> JSONResponse:
        return erro(500, "erro_interno", "Ocorreu um erro no servidor. Tente de novo em instantes.")
