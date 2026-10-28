"""Rotas do Auth: cadastro, login e /me (docs/guia-backend-login.md, seção 3).

O gateway repassa o caminho inteiro (/api/auth/login chega aqui como /api/auth/login), por isso
o prefixo completo fica no APIRouter.

As rotas usam "def" comum, sem "async": o hash da senha é lento de propósito e, numa rota
"async def", seguraria todas as outras requisições enquanto roda. Com "def", o FastAPI roda cada
requisição numa linha de execução separada.
"""

import re
import uuid

import jwt  # pacote PyJWT
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app import banco, seguranca
from app.erros import erro

rotas = APIRouter(prefix="/api/auth")

# Lê o cabeçalho "Authorization: Bearer <token>". Com auto_error=False, quando ele falta o
# FastAPI não responde sozinho (seria no formato dele): quem decide é a rota.
bearer = HTTPBearer(auto_error=False)

# As mesmas regras que a tela confere antes de enviar (seção 5 do guia). O servidor confere de
# novo porque qualquer um pode chamar a rota direto, sem passar pela tela.
NOME_MAX = 20
SENHA_MIN = 6
FORMATO_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")  # algo@algo.algo, sem espaços


# Corpo esperado em cada rota. O FastAPI lê o JSON e confere se os campos vieram e são texto;
# se não, quem responde é o tratador de RequestValidationError (erros.py), com 422.
class DadosCadastro(BaseModel):
    nome: str
    email: str
    senha: str


class DadosLogin(BaseModel):
    email: str
    senha: str


def limpar_email(email: str) -> str:
    """Sem espaços nas pontas e em minúsculas: Ana@Teste.com e ana@teste.com são a mesma conta.
    Usada no cadastro e no login, para o e-mail ser gravado e buscado do mesmo jeito."""
    return email.strip().lower()


def problema_no_cadastro(nome: str, email: str, senha: str) -> str | None:
    """Mensagem do primeiro problema encontrado nos dados do cadastro, ou None se estão certos.
    Os textos são os mesmos que a tela mostra junto de cada campo. len() conta caracteres como a
    tela: uma letra acentuada ou um emoji vale 1."""
    if not nome:
        return "Informe seu nome."
    if len(nome) > NOME_MAX:
        return f"O nome pode ter no máximo {NOME_MAX} caracteres."
    if not email:
        return "Informe seu e-mail."
    if not FORMATO_EMAIL.fullmatch(email):
        return "Informe um e-mail válido, como nome@exemplo.com."
    if len(senha) < SENHA_MIN:
        return f"A senha precisa ter no mínimo {SENHA_MIN} caracteres."
    return None


def email_ja_cadastrado():
    return erro(409, "email_ja_cadastrado", "Este e-mail já está cadastrado.")


def sessao_invalida():
    return erro(401, "token_invalido", "Sessão inválida. Entre de novo.")


@rotas.post("/cadastro", status_code=201)
def cadastro(dados: DadosCadastro):
    # 1. Limpa o nome e o e-mail. A senha fica exatamente como chegou: espaços e maiúsculas contam.
    nome = dados.nome.strip()
    email = limpar_email(dados.email)

    # 2. Confere as regras da tela.
    problema = problema_no_cadastro(nome, email, dados.senha)
    if problema:
        return erro(422, "dados_invalidos", problema)

    # 3. Recusa e-mail que já tem conta (antes de calcular o hash, que é demorado).
    if banco.buscar_usuario_por_email(email) is not None:
        return email_ja_cadastrado()

    # 4. Grava o usuário com o hash da senha. A senha em si não é guardada em lugar nenhum.
    try:
        usuario = banco.inserir_usuario(nome, email, seguranca.gerar_hash(dados.senha))
    except banco.EmailJaCadastrado:
        # Outro cadastro com o mesmo e-mail chegou junto e gravou primeiro.
        return email_ja_cadastrado()

    # 5. Responde 201 com id e nome. O login é uma segunda requisição, feita pela tela.
    return {"id": str(usuario["id"]), "nome": usuario["nome"]}


@rotas.post("/login")
def login(dados: DadosLogin):
    usuario = banco.buscar_usuario_por_email(limpar_email(dados.email))

    # E-mail sem conta e senha errada recebem a mesma resposta, para não revelar quais e-mails
    # têm conta. Não há regra de tamanho aqui: senha curta é só mais uma senha errada.
    if usuario is None or not seguranca.senha_confere(usuario["senha_hash"], dados.senha):
        return erro(401, "credenciais_invalidas", "E-mail ou senha incorretos.")

    return {
        "token": seguranca.criar_token(usuario["id"], usuario["nome"]),
        "usuario": {"id": str(usuario["id"]), "nome": usuario["nome"], "email": usuario["email"]},
    }


@rotas.get("/me")
def me(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credenciais is None:  # sem o cabeçalho, ou sem a palavra "Bearer"
        return sessao_invalida()

    try:
        conteudo = seguranca.conteudo_do_token(credenciais.credentials)
        # "sub" traz o id do usuário. Um sub que não é UUID (token de outro sistema assinado com
        # o mesmo segredo, por exemplo) daria erro no banco: é recusado aqui mesmo.
        usuario_id = uuid.UUID(conteudo["sub"])
    except jwt.ExpiredSignatureError:  # vem antes: é um caso particular de InvalidTokenError
        return erro(401, "token_expirado", "Sua sessão expirou. Entre de novo.")
    except (jwt.InvalidTokenError, ValueError):
        return sessao_invalida()

    # Os dados são buscados de novo no banco, para devolver os atuais.
    usuario = banco.buscar_usuario_por_id(usuario_id)
    if usuario is None:  # token certo, mas de um usuário que não existe mais
        return sessao_invalida()
    return {"id": str(usuario["id"]), "nome": usuario["nome"], "email": usuario["email"]}
