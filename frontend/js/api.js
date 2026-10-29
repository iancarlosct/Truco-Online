// Camada de chamadas HTTP: é por aqui que as telas falam com o backend.
// As rotas passam pelo gateway com o prefixo /api, e os erros chegam no formato
// {"erro": "codigo", "mensagem": "texto"}.

import { obterToken, sair } from "./auth.js";

const PREFIXO = "/api";

// Tempo máximo de espera pela resposta antes de desistir da requisição.
const TEMPO_LIMITE_MS = 10000;

// Para onde vai quem tem a sessão recusada pelo servidor: a tela de login, com o parâmetro
// que faz ela avisar que a sessão expirou (ver login.js).
const PAGINA_SESSAO_EXPIRADA = "index.html?sessao=expirada";

// Rotas que não exigem login (pelo contrato, todas as outras exigem o token). Nelas um 401
// quer dizer e-mail ou senha incorretos, e não sessão vencida.
const ROTAS_SEM_LOGIN = ["/auth/cadastro", "/auth/login"];

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

// Resposta 401 numa rota que exige login: o token venceu ou não vale mais. Apaga a sessão e
// volta para a tela de login, que avisa o motivo. Fica aqui, e não em cada tela, para valer em
// todas elas. O ws.js usa a mesma função quando o Game recusa o token (fechamento 4401).
export function encerrarSessao() {
  sair();
  location.replace(PAGINA_SESSAO_EXPIRADA);
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
    if (resposta.status === 401 && !ROTAS_SEM_LOGIN.includes(caminho)) encerrarSessao();
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
  return requisitar("POST", "/auth/cadastro", { nome, email, senha });
}

// POST /api/auth/login. Devolve { token, usuario: { id, nome, email } }.
export function login(email, senha) {
  return requisitar("POST", "/auth/login", { email, senha });
}

// GET /api/auth/me. Devolve o usuário do token: { id, nome, email }.
export function obterUsuarioLogado() {
  return requisitar("GET", "/auth/me");
}

// Confere o token no Auth ao abrir uma página que exige login, antes de montá-la: um token
// vencido leva logo para o login, com o aviso de sessão expirada, em vez de a página abrir e
// falhar na primeira chamada. Devolve false quando o Auth recusa o token (401: requisitar() já
// encerrou a sessão), e a página não deve continuar. Qualquer outra falha (Auth fora do ar, por
// exemplo) não impede a página: as chamadas dela mostram o erro.
//   if (exigirLogin() && (await conferirSessao())) iniciar();
export async function conferirSessao() {
  try {
    await obterUsuarioLogado();
    return true;
  } catch (erro) {
    return !(erro instanceof ErroApi && erro.status === 401);
  }
}

// ---------- Serviço Lobby ----------
// As rotas que devolvem uma sala usam sempre o mesmo formato (docs/guia-backend-lobby.md, seção 4):
//   { id, formato: "1x1" | "2x2", dono_id, status: "aguardando" | "em_partida" | "encerrada",
//     partida_id, assentos: [{ assento, usuario_id, nome, bot }] }
// Assento vazio tem usuario_id e nome null e bot false. No 1x1 os assentos são 0 e 1; no
// 2x2, de 0 a 3, com 0 e 2 no time A e 1 e 3 no time B. A sala fica "encerrada" quando o dono
// sai ou quando a partida dela termina; neste caso, com o partida_id ainda preenchido.

function caminhoSala(id) {
  return `/lobby/salas/${encodeURIComponent(id)}`;
}

// GET /api/lobby/salas. Devolve a lista das salas abertas (status "aguardando").
export function listarSalas() {
  return requisitar("GET", "/lobby/salas");
}

// POST /api/lobby/salas. Cria a sala com o usuário no assento 0 e devolve a sala.
export function criarSala(formato) {
  return requisitar("POST", "/lobby/salas", { formato });
}

// GET /api/lobby/salas/{id}. Devolve a sala.
export function obterSala(id) {
  return requisitar("GET", caminhoSala(id));
}

// POST /api/lobby/salas/{id}/entrar. Põe o usuário no assento indicado; se ele já estiver na
// sala, troca de assento. Devolve a sala atualizada.
export function entrarNaSala(id, assento) {
  return requisitar("POST", `${caminhoSala(id)}/entrar`, { assento });
}

// POST /api/lobby/salas/{id}/sair. Devolve a sala atualizada.
export function sairDaSala(id) {
  return requisitar("POST", `${caminhoSala(id)}/sair`);
}

// POST /api/lobby/salas/{id}/bot. Só o dono: põe um bot no assento vazio. Devolve a sala
// atualizada.
export function adicionarBot(id, assento, nivel = "padrao") {
  return requisitar("POST", `${caminhoSala(id)}/bot`, { assento, nivel });
}

// DELETE /api/lobby/salas/{id}/assentos/{assento}. Só o dono: tira o bot ou o jogador do
// assento. Devolve a sala atualizada. A rota não estava no documento de contratos: foi
// combinada com o Lobby (docs/guia-backend-lobby.md, seção 3.8).
export function liberarAssento(id, assento) {
  return requisitar("DELETE", `${caminhoSala(id)}/assentos/${assento}`);
}

// POST /api/lobby/salas/{id}/iniciar. Só o dono, com todos os assentos ocupados. Devolve
// { partida_id }; a sala passa a ter status "em_partida" e o mesmo partida_id.
export function iniciarPartida(id) {
  return requisitar("POST", `${caminhoSala(id)}/iniciar`);
}

// ---------- Serviço Ranking ----------

// GET /api/ranking. Devolve [{ posicao, usuario_id, nome, vitorias, partidas }], ordenado
// por vitórias.
export function obterRanking() {
  return requisitar("GET", "/ranking");
}

// GET /api/ranking/jogadores/{id}. Devolve o histórico do jogador (RF18):
//   { usuario_id, nome, posicao, vitorias, derrotas, partidas,
//     ultimas_partidas: [{ partida_id, formato, encerrada_em, time, venceu, placar_final: { A, B },
//                          times: { A: [{ assento, usuario_id, nome, bot }], B: [...] } }] }
// As últimas partidas vêm da mais recente para a mais antiga (até 10). Quem nunca jogou
// responde 404 jogador_nao_encontrado.
export function obterJogador(id) {
  return requisitar("GET", `/ranking/jogadores/${encodeURIComponent(id)}`);
}
