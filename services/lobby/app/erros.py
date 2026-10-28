"""Respostas de erro no formato do contrato: {"erro": "codigo", "mensagem": "texto"}.

"erro" é um código fixo, para programas. "mensagem" é mostrada pela tela ao jogador exatamente
como chega, num aviso no pé da tela. Os códigos e as mensagens são os do mock da tela, definitivos
por decisão do grupo (docs/guia-backend-lobby.md, seção 5.2).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Código -> (status HTTP, mensagem padrão).
ERROS = {
    "sala_nao_encontrada": (404, "Sala não encontrada. Ela pode ter sido encerrada."),
    "sala_cheia": (409, "A sala está cheia."),
    "assento_ocupado": (409, "Este assento já está ocupado."),
    "assento_vazio": (409, "Este assento já está vazio."),
    "apenas_dono": (403, "Só o dono da sala pode fazer isso."),
    "sala_incompleta": (409, "A partida só começa com todos os assentos ocupados."),
    "partida_ja_iniciada": (409, "A partida desta sala já começou."),
    "ja_esta_em_outra_sala": (409, "Você já está em outra sala. Saia dela antes de entrar em outra."),
    "nao_esta_na_sala": (409, "Você não está nesta sala."),
    "dados_invalidos": (422, "Dados inválidos."),
    "token_invalido": (401, "Sessão inválida. Entre de novo."),
    "token_expirado": (401, "Sua sessão expirou. Entre de novo."),
    "game_indisponivel": (503, "Não foi possível iniciar a partida agora. Tente de novo em instantes."),
}


class ErroLobby(Exception):
    """Erro de regra. As rotas fazem raise ErroLobby("codigo") e o tratador abaixo responde no
    formato do contrato, com o status da tabela ERROS. A mensagem padrão pode ser trocada
    (dados_invalidos tem uma para cada caso)."""

    def __init__(self, codigo: str, mensagem: str | None = None):
        super().__init__(codigo)
        self.codigo = codigo
        self.status, mensagem_padrao = ERROS[codigo]
        self.mensagem = mensagem or mensagem_padrao


def erro(status: int, codigo: str, mensagem: str, headers: dict | None = None) -> JSONResponse:
    """Resposta de erro pronta, com o status HTTP indicado."""
    return JSONResponse(status_code=status, content={"erro": codigo, "mensagem": mensagem}, headers=headers)


def resposta_de_erro(exc: ErroLobby) -> JSONResponse:
    return erro(exc.status, exc.codigo, exc.mensagem)


# Erros que o próprio FastAPI gera, por status: código e mensagem do contrato.
ERROS_HTTP = {
    404: ("nao_encontrado", "Endereço não encontrado."),
    405: ("metodo_nao_permitido", "Operação não permitida neste endereço."),
}


def registrar_tratadores(app: FastAPI) -> None:
    """Troca as respostas de erro padrão do FastAPI ({"detail": ...}) pelo formato do contrato."""
    # Importado aqui para evitar a importação circular (seguranca usa ErroLobby, daqui).
    from app.seguranca import usuario_do_cabecalho

    @app.exception_handler(ErroLobby)
    def erro_lobby(request: Request, exc: ErroLobby) -> JSONResponse:
        return resposta_de_erro(exc)

    # Corpo ou caminho fora do esperado: JSON quebrado, campo faltando, texto no lugar de número.
    # O token é sempre conferido primeiro (guia do lobby, 5.2), mas o FastAPI lê o JSON do corpo
    # antes de chamar a conferência do token. Por isso o token é conferido aqui de novo: um pedido
    # sem token válido recebe 401, e não 422, mesmo com o corpo quebrado.
    @app.exception_handler(RequestValidationError)
    def corpo_invalido(request: Request, exc: RequestValidationError) -> JSONResponse:
        try:
            usuario_do_cabecalho(request.headers.get("authorization"))
        except ErroLobby as erro_do_token:
            return resposta_de_erro(erro_do_token)
        return resposta_de_erro(ErroLobby("dados_invalidos"))

    # Rota inexistente (404), método errado (405) e qualquer HTTPException.
    @app.exception_handler(StarletteHTTPException)
    def erro_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codigo, mensagem = ERROS_HTTP.get(exc.status_code, ("erro_http", "Não foi possível concluir a operação."))
        # Os cabeçalhos seguem junto (o 405, por exemplo, diz no "Allow" quais métodos valem).
        return erro(exc.status_code, codigo, mensagem, headers=exc.headers)

    # Erro inesperado no código (um bug, ou o banco fora do ar). O jogador recebe uma mensagem
    # genérica; o detalhe (a exceção completa) o Uvicorn escreve no log do container
    # (docker compose logs lobby).
    @app.exception_handler(Exception)
    def erro_interno(request: Request, exc: Exception) -> JSONResponse:
        return erro(500, "erro_interno", "Ocorreu um erro no servidor. Tente de novo em instantes.")
