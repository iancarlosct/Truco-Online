// Camada de chamadas HTTP: é por aqui que as telas falam com o backend.
// As rotas passam pelo gateway com o prefixo /api, e os erros chegam no formato
// {"erro": "codigo", "mensagem": "texto"}.

import { obterToken, obterUsuario, sair } from "./auth.js";

// =====================================================================================
// PROVISÓRIO — REMOVER quando o serviço Auth existir.
// Com true, cadastrar() e login() não chamam o backend: respondem com dados falsos no
// formato do contrato (ver "MOCK DO SERVIÇO AUTH", no fim do arquivo).
// Com false, as mesmas funções chamam o backend real, sem nenhuma outra mudança no código.
// =====================================================================================
const USAR_MOCK = true;

// =====================================================================================
// PROVISÓRIO — REMOVER quando os serviços Lobby e Ranking existirem.
// O mesmo esquema do USAR_MOCK, para as funções do Lobby e do Ranking (ver "MOCK DOS
// SERVIÇOS LOBBY E RANKING", no fim do arquivo). Cada serviço tem a sua chave, para dar
// para ligar um de cada vez, à medida que ficarem prontos.
// =====================================================================================
const USAR_MOCK_LOBBY = true;
const USAR_MOCK_RANKING = true;

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
  if (USAR_MOCK) return mockCadastrar(nome, email, senha);
  return requisitar("POST", "/auth/cadastro", { nome, email, senha });
}

// POST /api/auth/login. Devolve { token, usuario: { id, nome, email } }.
export function login(email, senha) {
  if (USAR_MOCK) return mockLogin(email, senha);
  return requisitar("POST", "/auth/login", { email, senha });
}

// ---------- Serviço Lobby ----------
// As rotas que devolvem uma sala usam sempre o mesmo formato:
//   { id, formato: "1x1" | "2x2", dono_id, status: "aguardando" | "em_partida", partida_id,
//     assentos: [{ assento, usuario_id, nome, bot }] }
// Assento vazio tem usuario_id e nome null e bot false. No 1x1 os assentos são 0 e 1; no
// 2x2, de 0 a 3, com 0 e 2 no time A e 1 e 3 no time B.

function caminhoSala(id) {
  return `/lobby/salas/${encodeURIComponent(id)}`;
}

// GET /api/lobby/salas. Devolve a lista das salas abertas (status "aguardando").
export function listarSalas() {
  if (USAR_MOCK_LOBBY) return mockListarSalas();
  return requisitar("GET", "/lobby/salas");
}

// POST /api/lobby/salas. Cria a sala com o usuário no assento 0 e devolve a sala.
export function criarSala(formato) {
  if (USAR_MOCK_LOBBY) return mockCriarSala(formato);
  return requisitar("POST", "/lobby/salas", { formato });
}

// GET /api/lobby/salas/{id}. Devolve a sala.
export function obterSala(id) {
  if (USAR_MOCK_LOBBY) return mockObterSala(id);
  return requisitar("GET", caminhoSala(id));
}

// POST /api/lobby/salas/{id}/entrar. Põe o usuário no assento indicado; se ele já estiver na
// sala, troca de assento. Devolve a sala atualizada.
export function entrarNaSala(id, assento) {
  if (USAR_MOCK_LOBBY) return mockEntrarNaSala(id, assento);
  return requisitar("POST", `${caminhoSala(id)}/entrar`, { assento });
}

// POST /api/lobby/salas/{id}/sair. Devolve a sala atualizada.
export function sairDaSala(id) {
  if (USAR_MOCK_LOBBY) return mockSairDaSala(id);
  return requisitar("POST", `${caminhoSala(id)}/sair`);
}

// POST /api/lobby/salas/{id}/bot. Só o dono: põe um bot no assento vazio. Devolve a sala
// atualizada.
export function adicionarBot(id, assento, nivel = "padrao") {
  if (USAR_MOCK_LOBBY) return mockAdicionarBot(id, assento);
  return requisitar("POST", `${caminhoSala(id)}/bot`, { assento, nivel });
}

// DELETE /api/lobby/salas/{id}/assentos/{assento}. Só o dono: tira o bot ou o jogador do
// assento. Devolve a sala atualizada.
// PROPOSTA: esta rota NÃO está no documento de contratos. Combinar com quem implementar o
// serviço Lobby antes de contar com ela.
export function liberarAssento(id, assento) {
  if (USAR_MOCK_LOBBY) return mockLiberarAssento(id, assento);
  return requisitar("DELETE", `${caminhoSala(id)}/assentos/${assento}`);
}

// POST /api/lobby/salas/{id}/iniciar. Só o dono, com todos os assentos ocupados. Devolve
// { partida_id }; a sala passa a ter status "em_partida" e o mesmo partida_id.
export function iniciarPartida(id) {
  if (USAR_MOCK_LOBBY) return mockIniciarPartida(id);
  return requisitar("POST", `${caminhoSala(id)}/iniciar`);
}

// ---------- Serviço Ranking ----------

// GET /api/ranking. Devolve [{ posicao, usuario_id, nome, vitorias, partidas }], ordenado
// por vitórias.
export function obterRanking() {
  if (USAR_MOCK_RANKING) return mockObterRanking();
  return requisitar("GET", "/ranking");
}

// =====================================================================================
// PROVISÓRIO — BASE DOS MOCKS (Auth, Lobby e Ranking). REMOVER junto com o último deles.
// =====================================================================================

// Atraso de cada resposta simulada, como se ela viesse pela rede.
const ATRASO_MOCK_MS = 500;

function esperar(ms) {
  return new Promise((resolver) => setTimeout(resolver, ms));
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

// =====================================================================================
// PROVISÓRIO — MOCK DOS SERVIÇOS LOBBY E RANKING. REMOVER junto com USAR_MOCK_LOBBY e
// USAR_MOCK_RANKING.
// Simula as rotas do Lobby e do Ranking sem backend, dentro do navegador:
// - As salas ficam no localStorage, para sobreviver ao F5. Na primeira vez já existem
//   algumas salas de jogadores fictícios, com vagas diferentes.
// - O usuário é o da sessão (auth.js). Sem token, a resposta é 401, como no serviço.
// - Alguns segundos depois de você criar uma sala, um jogador fictício entra numa vaga.
// - window.mockLobby (no fim do arquivo) é uma FERRAMENTA DE DESENVOLVIMENTO para fazer, pelo
//   console do navegador, o que os outros jogadores fariam.
// As regras e os códigos de erro são um palpite, como no mock do Auth: o contrato define as
// rotas e o formato da sala, mas não a lista de erros.
// =====================================================================================
const CHAVE_SALAS_MOCK = "truco.mock.salas";

// Tempo entre criar uma sala e o jogador fictício entrar nela.
const ENTRADA_FICTICIA_MS = 4000;

const ASSENTOS_POR_FORMATO = { "1x1": 2, "2x2": 4 };

// Jogadores fictícios: donos das salas iniciais, quem entra nas salas e quem está no ranking.
const FICTICIOS = [
  { id: "ficticio-1", nome: "Maria" },
  { id: "ficticio-2", nome: "João" },
  { id: "ficticio-3", nome: "Ana" },
  { id: "ficticio-4", nome: "Carla" },
  { id: "ficticio-5", nome: "Pedro" },
  { id: "ficticio-6", nome: "Lucas" },
  { id: "ficticio-7", nome: "Bia" },
  { id: "ficticio-8", nome: "Seu Zé" },
  { id: "ficticio-9", nome: "Rafa" },
  { id: "ficticio-10", nome: "Dona Cida" },
];

// Erros que o mock simula: código -> [status HTTP, mensagem].
const ERROS_LOBBY = {
  sala_nao_encontrada: [404, "Sala não encontrada. Ela pode ter sido encerrada."],
  sala_cheia: [409, "A sala está cheia."],
  assento_ocupado: [409, "Este assento já está ocupado."],
  assento_vazio: [409, "Este assento já está vazio."],
  apenas_dono: [403, "Só o dono da sala pode fazer isso."],
  sala_incompleta: [409, "A partida só começa com todos os assentos ocupados."],
  partida_ja_iniciada: [409, "A partida desta sala já começou."],
  ja_esta_em_outra_sala: [409, "Você já está em outra sala. Saia dela antes de entrar em outra."],
  nao_esta_na_sala: [409, "Você não está nesta sala."],
  dados_invalidos: [422, "Dados inválidos."],
};

function erroLobby(codigo, mensagem) {
  const [status, mensagemPadrao] = ERROS_LOBBY[codigo];
  return new ErroApi(codigo, mensagem ?? mensagemPadrao, status);
}

function assentoVazio(assento) {
  return { assento, usuario_id: null, nome: null, bot: false };
}

function estaOcupado(assento) {
  return Boolean(assento.bot || assento.usuario_id);
}

// Monta uma das salas que existem desde o começo. Cada ocupante é um jogador fictício, o nome
// de um bot ou null (vaga). O primeiro ocupante é o dono.
function salaInicial(id, formato, ocupantes) {
  const assentos = ocupantes.map((ocupante, assento) => {
    if (ocupante === null) return assentoVazio(assento);
    if (typeof ocupante === "string") return { assento, usuario_id: null, nome: ocupante, bot: true };
    return { assento, usuario_id: ocupante.id, nome: ocupante.nome, bot: false };
  });
  return { id, formato, dono_id: assentos[0].usuario_id, status: "aguardando", partida_id: null, assentos };
}

function salasIniciais() {
  const [maria, joao, ana, carla, pedro, lucas, bia, ze] = FICTICIOS;
  return [
    salaInicial("s1", "1x1", [maria, null]),
    salaInicial("s2", "2x2", [ze, null, null, null]),
    salaInicial("s3", "2x2", [joao, null, ana, null]),
    salaInicial("s4", "2x2", [carla, "Bot 1", pedro, null]),
    salaInicial("s5", "1x1", [lucas, bia]),
  ];
}

// Estado guardado: { proximoId, salas, entradas }. "entradas" são as entradas de jogadores
// fictícios agendadas para depois da criação de uma sala: [{ salaId, quando }].
function lerSalasMock() {
  try {
    const estado = JSON.parse(localStorage.getItem(CHAVE_SALAS_MOCK));
    if (Array.isArray(estado?.salas) && Array.isArray(estado.entradas)) return estado;
  } catch {
    // Valor corrompido: recomeça com as salas iniciais.
  }
  const salas = salasIniciais();
  return { proximoId: salas.length + 1, salas, entradas: [] };
}

function salvarSalasMock(estado) {
  localStorage.setItem(CHAVE_SALAS_MOCK, JSON.stringify(estado));
}

function assentoDoUsuario(sala, usuarioId) {
  return sala.assentos.find((a) => a.usuario_id === usuarioId);
}

function primeiraVaga(sala) {
  return sala.assentos.find((a) => !estaOcupado(a));
}

// Sala que ainda não começou e em que o usuário está sentado.
function salaAbertaDoUsuario(estado, usuarioId) {
  return estado.salas.find((s) => s.status === "aguardando" && assentoDoUsuario(s, usuarioId));
}

// "Bot 1", "Bot 2"...: o menor número que ainda não está em uso na sala.
function nomeDeBot(sala) {
  const usados = new Set(sala.assentos.filter((a) => a.bot).map((a) => a.nome));
  let numero = 1;
  while (usados.has(`Bot ${numero}`)) numero++;
  return `Bot ${numero}`;
}

// Põe um jogador fictício no assento indicado (sem número, na primeira vaga), de preferência
// um que não esteja em nenhuma sala aberta. Devolve o assento, ou null se não estava vago.
function sentarFicticio(estado, sala, numero) {
  const assento = numero === undefined ? primeiraVaga(sala) : sala.assentos.find((a) => a.assento === numero);
  if (!assento || estaOcupado(assento)) return null;
  const jogador =
    FICTICIOS.find((f) => !salaAbertaDoUsuario(estado, f.id)) ??
    FICTICIOS.find((f) => !assentoDoUsuario(sala, f.id));
  Object.assign(assento, { usuario_id: jogador.id, nome: jogador.nome, bot: false });
  return assento;
}

// Faz as entradas agendadas cujo horário já passou. Isso acontece a cada chamada, e não num
// setTimeout, para continuar valendo depois de um F5.
function fazerEntradasAgendadas(estado) {
  const agora = Date.now();
  for (const entrada of estado.entradas.filter((e) => e.quando <= agora)) {
    const sala = estado.salas.find((s) => s.id === entrada.salaId);
    if (sala?.status === "aguardando") sentarFicticio(estado, sala);
  }
  estado.entradas = estado.entradas.filter((e) => e.quando > agora);
}

// Combinados pelos comandos do console (mockLobby) para a próxima resposta.
let erroDaProximaAcao = null;
let sessaoVencida = false;

// Confere a sessão como o serviço faria. Sem token (logout em outra aba, por exemplo) ou depois
// de mockLobby.expirarSessao(), responde 401 e, como em requisitar(), encerra a sessão.
function usuarioDaSessaoMock() {
  const usuario = obterUsuario();
  if (obterToken() && usuario && !sessaoVencida) return usuario;
  sessaoVencida = false;
  encerrarSessao();
  throw new ErroApi("token_expirado", "Sua sessão expirou. Entre de novo.", 401);
}

// Toda rota simulada do Lobby passa por aqui, como uma requisição passaria pelo servidor:
// atraso de rede, sessão, entradas agendadas e, por fim, a operação, que recebe o estado e o
// usuário e devolve a resposta (ou lança o erro). O estado é salvo mesmo quando a operação
// falha, porque as entradas agendadas podem ter mudado algo. Só as ações ("acao") obedecem a
// mockLobby.falharProximaAcao(): a atualização periódica não pode gastar o erro combinado.
async function simularLobby(operacao, { acao = false } = {}) {
  await esperar(ATRASO_MOCK_MS);
  const usuario = usuarioDaSessaoMock();
  if (acao && erroDaProximaAcao) {
    const codigo = erroDaProximaAcao;
    erroDaProximaAcao = null;
    throw erroLobby(codigo);
  }
  const estado = lerSalasMock();
  fazerEntradasAgendadas(estado);
  try {
    // A resposta é uma cópia, como se tivesse vindo pela rede.
    return JSON.parse(JSON.stringify(operacao(estado, usuario)));
  } finally {
    salvarSalasMock(estado);
  }
}

function buscarSalaMock(estado, id) {
  const sala = estado.salas.find((s) => s.id === id);
  if (!sala) throw erroLobby("sala_nao_encontrada");
  return sala;
}

function buscarAssentoMock(sala, numero) {
  const assento = sala.assentos.find((a) => a.assento === numero);
  if (!assento) throw erroLobby("dados_invalidos", "Assento inválido.");
  return assento;
}

function exigirDonoMock(sala, usuario) {
  if (sala.dono_id !== usuario.id) throw erroLobby("apenas_dono");
}

function exigirAguardandoMock(sala) {
  if (sala.status !== "aguardando") throw erroLobby("partida_ja_iniciada");
}

// Passa a sala para "em_partida" com um partida_id inventado. Devolve { partida_id }.
function iniciarSalaMock(sala) {
  sala.status = "em_partida";
  sala.partida_id = `mock-${sala.id}-${Date.now().toString(36)}`;
  return { partida_id: sala.partida_id };
}

// Para o mock do Game (js/mock/servidor-game.js), no lugar do POST /interno/partidas que o
// Lobby faria ao iniciar: a sala do mock que começou a partida com este partida_id, com os
// assentos, ou null. Só lê: não muda nada nas salas.
export function salaDaPartidaMock(partidaId) {
  const sala = lerSalasMock().salas.find((s) => s.partida_id === partidaId);
  return sala ? JSON.parse(JSON.stringify(sala)) : null;
}

function mockListarSalas() {
  return simularLobby((estado) => estado.salas.filter((s) => s.status === "aguardando"));
}

function mockCriarSala(formato) {
  return simularLobby(
    (estado, eu) => {
      if (!Object.hasOwn(ASSENTOS_POR_FORMATO, formato)) {
        throw erroLobby("dados_invalidos", "Formato de sala inválido.");
      }
      if (salaAbertaDoUsuario(estado, eu.id)) throw erroLobby("ja_esta_em_outra_sala");
      const assentos = Array.from({ length: ASSENTOS_POR_FORMATO[formato] }, (_, i) => assentoVazio(i));
      Object.assign(assentos[0], { usuario_id: eu.id, nome: eu.nome });
      const sala = {
        id: `s${estado.proximoId++}`,
        formato,
        dono_id: eu.id,
        status: "aguardando",
        partida_id: null,
        assentos,
      };
      estado.salas.push(sala);
      estado.entradas.push({ salaId: sala.id, quando: Date.now() + ENTRADA_FICTICIA_MS });
      return sala;
    },
    { acao: true },
  );
}

function mockObterSala(id) {
  return simularLobby((estado) => buscarSalaMock(estado, id));
}

function mockEntrarNaSala(id, numero) {
  return simularLobby(
    (estado, eu) => {
      const sala = buscarSalaMock(estado, id);
      exigirAguardandoMock(sala);
      const destino = buscarAssentoMock(sala, numero);
      const atual = assentoDoUsuario(sala, eu.id);
      if (destino === atual) return sala;
      if (!atual && !primeiraVaga(sala)) throw erroLobby("sala_cheia");
      if (estaOcupado(destino)) throw erroLobby("assento_ocupado");
      if (!atual && salaAbertaDoUsuario(estado, eu.id)) throw erroLobby("ja_esta_em_outra_sala");
      // Quem já está na sala troca de assento: o assento antigo fica vago.
      if (atual) Object.assign(atual, assentoVazio(atual.assento));
      Object.assign(destino, { usuario_id: eu.id, nome: eu.nome, bot: false });
      return sala;
    },
    { acao: true },
  );
}

function mockSairDaSala(id) {
  return simularLobby(
    (estado, eu) => {
      const sala = buscarSalaMock(estado, id);
      exigirAguardandoMock(sala);
      const atual = assentoDoUsuario(sala, eu.id);
      if (!atual) throw erroLobby("nao_esta_na_sala");
      Object.assign(atual, assentoVazio(atual.assento));
      // Se o dono sai, a sala é encerrada: some da lista e passa a responder 404. O status
      // "encerrada" da resposta não existe no contrato; a tela não lê a resposta do /sair.
      if (sala.dono_id === eu.id) {
        estado.salas = estado.salas.filter((s) => s !== sala);
        sala.status = "encerrada";
      }
      return sala;
    },
    { acao: true },
  );
}

// O nível do bot não muda nada no mock: o contrato só cita "padrao".
function mockAdicionarBot(id, numero) {
  return simularLobby(
    (estado, eu) => {
      const sala = buscarSalaMock(estado, id);
      exigirDonoMock(sala, eu);
      exigirAguardandoMock(sala);
      const assento = buscarAssentoMock(sala, numero);
      if (estaOcupado(assento)) throw erroLobby("assento_ocupado");
      Object.assign(assento, { usuario_id: null, nome: nomeDeBot(sala), bot: true });
      return sala;
    },
    { acao: true },
  );
}

function mockLiberarAssento(id, numero) {
  return simularLobby(
    (estado, eu) => {
      const sala = buscarSalaMock(estado, id);
      exigirDonoMock(sala, eu);
      exigirAguardandoMock(sala);
      const assento = buscarAssentoMock(sala, numero);
      if (!estaOcupado(assento)) throw erroLobby("assento_vazio");
      if (assento.usuario_id === eu.id) {
        throw erroLobby("dados_invalidos", "Para sair da sala, use o botão Sair da sala.");
      }
      Object.assign(assento, assentoVazio(numero));
      return sala;
    },
    { acao: true },
  );
}

function mockIniciarPartida(id) {
  return simularLobby(
    (estado, eu) => {
      const sala = buscarSalaMock(estado, id);
      exigirDonoMock(sala, eu);
      exigirAguardandoMock(sala);
      if (primeiraVaga(sala)) throw erroLobby("sala_incompleta");
      return iniciarSalaMock(sala);
    },
    { acao: true },
  );
}

// Ranking com nove jogadores fictícios e o usuário logado, já em ordem de vitórias.
async function mockObterRanking() {
  await esperar(ATRASO_MOCK_MS);
  const eu = usuarioDaSessaoMock();
  const [maria, joao, ana, carla, pedro, lucas, bia, ze, rafa] = FICTICIOS;
  const linhas = [
    [carla, 31, 48],
    [joao, 27, 50],
    [maria, 24, 39],
    [bia, 19, 33],
    [pedro, 15, 30],
    [eu, 12, 21],
    [ana, 10, 25],
    [ze, 8, 22],
    [lucas, 5, 14],
    [rafa, 2, 9],
  ];
  return linhas.map(([jogador, vitorias, partidas], indice) => ({
    posicao: indice + 1,
    usuario_id: jogador.id,
    nome: jogador.nome,
    vitorias,
    partidas,
  }));
}

// =====================================================================================
// FERRAMENTA DE DESENVOLVIMENTO — REMOVER junto com o mock do Lobby.
// window.mockLobby: comandos para o console do navegador (F12) que fazem o papel dos outros
// jogadores. Eles mexem direto nas salas guardadas, e a tela percebe na próxima atualização
// (até 3 segundos). Sem o id da sala, valem para a sala aberta na tela (lobby.html?sala=...).
// A lista de comandos aparece com mockLobby.ajuda().
// =====================================================================================

// Separa os argumentos de um comando: texto é o id da sala; número, o assento.
function alvoDoComando(argumentos) {
  return {
    salaId: argumentos.find((a) => typeof a === "string") ?? new URLSearchParams(location.search).get("sala"),
    numero: argumentos.find((a) => typeof a === "number"),
  };
}

// Executa um comando sobre uma sala. "mudar" altera o estado e devolve a frase que conta o que
// aconteceu.
function comandoMock(argumentos, mudar) {
  const { salaId, numero } = alvoDoComando(argumentos);
  const estado = lerSalasMock();
  fazerEntradasAgendadas(estado);
  const sala = estado.salas.find((s) => s.id === salaId);
  if (sala) console.info(`[mockLobby] ${mudar(estado, sala, numero)}`);
  else if (salaId) console.warn(`[mockLobby] A sala ${salaId} não existe. Veja as salas com mockLobby.salas().`);
  else console.warn('[mockLobby] Informe a sala, por exemplo: mockLobby.entrarJogador("s1").');
  salvarSalasMock(estado);
}

if (USAR_MOCK_LOBBY) {
  window.mockLobby = {
    ajuda() {
      console.info(
        [
          "mockLobby — FERRAMENTA DE DESENVOLVIMENTO: simula os outros jogadores.",
          "Sem o id da sala, os comandos valem para a sala aberta na tela.",
          "  mockLobby.salas()                        lista as salas do mock",
          '  mockLobby.entrarJogador("s1", 2)         um jogador fictício entra (assento opcional)',
          '  mockLobby.removerJogador("s1", 1)        tira quem está no assento (se for o dono, encerra a sala)',
          '  mockLobby.encerrarSala("s1")             o dono sai e a sala deixa de existir',
          '  mockLobby.iniciarPartida("s1")           o dono inicia a partida (as vagas viram bots)',
          '  mockLobby.falharProximaAcao("sala_cheia")  a próxima ação da tela falha com esse erro',
          "  mockLobby.expirarSessao()                a próxima chamada responde 401",
          "  mockLobby.resetar()                      volta às salas iniciais",
        ].join("\n"),
      );
    },

    salas() {
      const estado = lerSalasMock();
      fazerEntradasAgendadas(estado);
      salvarSalasMock(estado);
      console.table(
        estado.salas.map((s) => ({
          id: s.id,
          formato: s.formato,
          dono: assentoDoUsuario(s, s.dono_id)?.nome ?? s.dono_id,
          jogadores: `${s.assentos.filter(estaOcupado).length}/${s.assentos.length}`,
          status: s.status,
          partida_id: s.partida_id,
        })),
      );
    },

    entrarJogador(...argumentos) {
      comandoMock(argumentos, (estado, sala, numero) => {
        if (sala.status !== "aguardando") return `A partida da sala ${sala.id} já começou.`;
        const assento = sentarFicticio(estado, sala, numero);
        if (assento) return `${assento.nome} entrou na sala ${sala.id}, no assento ${assento.assento}.`;
        if (numero === undefined) return `A sala ${sala.id} está cheia.`;
        return `O assento ${numero} da sala ${sala.id} não existe ou não está vago.`;
      });
    },

    removerJogador(...argumentos) {
      comandoMock(argumentos, (estado, sala, numero) => {
        const assento = sala.assentos.find((a) => a.assento === numero);
        if (!assento) return "Informe o assento, por exemplo: mockLobby.removerJogador(1).";
        if (!estaOcupado(assento)) return `O assento ${numero} da sala ${sala.id} já está vazio.`;
        if (assento.usuario_id === sala.dono_id) {
          estado.salas = estado.salas.filter((s) => s !== sala);
          return `${assento.nome} era o dono: a sala ${sala.id} foi encerrada.`;
        }
        const nome = assento.nome;
        Object.assign(assento, assentoVazio(numero));
        return `${nome} saiu do assento ${numero} da sala ${sala.id}.`;
      });
    },

    encerrarSala(...argumentos) {
      comandoMock(argumentos, (estado, sala) => {
        estado.salas = estado.salas.filter((s) => s !== sala);
        return `A sala ${sala.id} foi encerrada.`;
      });
    },

    iniciarPartida(...argumentos) {
      comandoMock(argumentos, (estado, sala) => {
        if (sala.status !== "aguardando") return `A partida da sala ${sala.id} já começou.`;
        const vagas = sala.assentos.filter((a) => !estaOcupado(a));
        for (const assento of vagas) Object.assign(assento, { nome: nomeDeBot(sala), bot: true });
        const { partida_id } = iniciarSalaMock(sala);
        const bots = vagas.length ? `; ${vagas.length} vaga(s) preenchida(s) com bot` : "";
        return `Partida ${partida_id} iniciada na sala ${sala.id}${bots}.`;
      });
    },

    falharProximaAcao(codigo) {
      if (!Object.hasOwn(ERROS_LOBBY, codigo)) {
        console.warn(`[mockLobby] Códigos possíveis: ${Object.keys(ERROS_LOBBY).join(", ")}.`);
        return;
      }
      erroDaProximaAcao = codigo;
      console.info(`[mockLobby] A próxima ação da tela vai falhar com "${codigo}".`);
    },

    expirarSessao() {
      sessaoVencida = true;
      console.info("[mockLobby] A próxima chamada vai responder 401, e a tela volta para o login.");
    },

    resetar() {
      localStorage.removeItem(CHAVE_SALAS_MOCK);
      erroDaProximaAcao = null;
      sessaoVencida = false;
      console.info("[mockLobby] As salas voltaram ao estado inicial.");
    },
  };
  console.info("[mockLobby] Lobby simulado (USAR_MOCK_LOBBY). Comandos: mockLobby.ajuda()");
}
