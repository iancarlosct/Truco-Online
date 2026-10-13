// Camada de chamadas HTTP: é por aqui que as telas falam com o backend.
// As rotas passam pelo gateway com o prefixo /api, e os erros chegam no formato
// {"erro": "codigo", "mensagem": "texto"}.

import { obterToken } from "./auth.js";

// =====================================================================================
// PROVISÓRIO — REMOVER quando o serviço Auth existir.
// Com true, cadastrar() e login() não chamam o backend: respondem com dados falsos no
// formato do contrato (ver "MOCK DO SERVIÇO AUTH", no fim do arquivo).
// Com false, as mesmas funções chamam o backend real, sem nenhuma outra mudança no código.
// =====================================================================================
const USAR_MOCK = true;

const PREFIXO = "/api";

// Tempo máximo de espera pela resposta antes de desistir da requisição.
const TEMPO_LIMITE_MS = 10000;

// Erro de qualquer chamada à API. Tem "codigo" (o campo "erro" do contrato), "mensagem"
// (texto pronto para mostrar ao usuário) e "status" (HTTP; 0 quando não houve resposta).
export class ErroApi extends Error {
  constructor(codigo, mensagem, status = 0) {
    super(mensagem);
    this.name = "ErroApi";
    this.codigo = codigo;
    this.mensagem = mensagem;
    this.status = status;
  }
}

// ---------- Requisição genérica ----------

// Lê o corpo da resposta como JSON. Devolve null quando ele vem vazio (204) ou não é JSON
// (a página de erro do gateway, por exemplo).
async function lerJson(resposta) {
  try {
    const texto = await resposta.text();
    return texto ? JSON.parse(texto) : null;
  } catch {
    return null;
  }
}

// Mensagem usada quando a resposta de erro não vem no formato do contrato.
function mensagemPadrao(status) {
  if (status >= 500) return "O servidor está indisponível no momento. Tente de novo em instantes.";
  return `Não foi possível concluir a operação (erro ${status}).`;
}

// Chama uma rota da API e devolve o corpo da resposta, já convertido de JSON.
// Qualquer falha vira um ErroApi. Exemplos:
//   requisitar("GET", "/lobby/salas")
//   requisitar("POST", "/auth/login", { email, senha })
export async function requisitar(metodo, caminho, corpo) {
  const opcoes = {
    method: metodo,
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(TEMPO_LIMITE_MS),
  };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const token = obterToken();
  if (token) opcoes.headers.Authorization = `Bearer ${token}`;

  let resposta;
  try {
    resposta = await fetch(PREFIXO + caminho, opcoes);
  } catch {
    // O fetch só falha quando não chega resposta nenhuma: servidor fora do ar, sem rede
    // ou tempo limite esgotado.
    throw new ErroApi(
      "falha_de_rede",
      "Não foi possível conectar ao servidor. Verifique sua conexão e tente de novo em instantes.",
    );
  }

  const dados = await lerJson(resposta);
  if (!resposta.ok) {
    throw new ErroApi(
      dados?.erro ?? "erro_http",
      dados?.mensagem ?? mensagemPadrao(resposta.status),
      resposta.status,
    );
  }
  return dados;
}

// ---------- Serviço Auth ----------

// POST /api/auth/cadastro. Devolve { id, nome }.
export function cadastrar(nome, email, senha) {
  if (USAR_MOCK) return mockCadastrar(nome, email, senha);
  return requisitar("POST", "/auth/cadastro", { nome, email, senha });
}

// POST /api/auth/login. Devolve { token, usuario: { id, nome, email } }.
export function login(email, senha) {
  if (USAR_MOCK) return mockLogin(email, senha);
  return requisitar("POST", "/auth/login", { email, senha });
}

// =====================================================================================
// PROVISÓRIO — MOCK DO SERVIÇO AUTH. REMOVER junto com USAR_MOCK.
// Simula o cadastro e o login sem backend. Os usuários ficam no localStorage deste
// navegador, para dar para cadastrar e depois logar. A senha é guardada em texto puro:
// use só dados de teste.
// Os códigos de erro ("email_ja_cadastrado", "credenciais_invalidas") são um palpite: o
// contrato define o formato e o status HTTP, mas não a lista de códigos.
// =====================================================================================
const CHAVE_USUARIOS_MOCK = "truco.mock.usuarios";
const ATRASO_MOCK_MS = 500;

function esperar(ms) {
  return new Promise((resolver) => setTimeout(resolver, ms));
}

function lerUsuariosMock() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_USUARIOS_MOCK)) ?? [];
  } catch {
    return [];
  }
}

// O e-mail identifica o usuário sem diferenciar maiúsculas de minúsculas.
function normalizarEmail(email) {
  return email.trim().toLowerCase();
}

async function mockCadastrar(nome, email, senha) {
  await esperar(ATRASO_MOCK_MS);
  const usuarios = lerUsuariosMock();
  if (usuarios.some((u) => u.email === normalizarEmail(email))) {
    throw new ErroApi("email_ja_cadastrado", "Este e-mail já está cadastrado.", 409);
  }
  const usuario = { id: `mock-${usuarios.length + 1}`, nome, email: normalizarEmail(email), senha };
  localStorage.setItem(CHAVE_USUARIOS_MOCK, JSON.stringify([...usuarios, usuario]));
  return { id: usuario.id, nome: usuario.nome };
}

async function mockLogin(email, senha) {
  await esperar(ATRASO_MOCK_MS);
  const usuario = lerUsuariosMock().find((u) => u.email === normalizarEmail(email));
  // E-mail desconhecido e senha errada dão o mesmo erro, para não revelar quem tem conta.
  if (!usuario || usuario.senha !== senha) {
    throw new ErroApi("credenciais_invalidas", "E-mail ou senha incorretos.", 401);
  }
  return {
    token: `mock.${usuario.id}.${Date.now()}`,
    usuario: { id: usuario.id, nome: usuario.nome, email: usuario.email },
  };
}
