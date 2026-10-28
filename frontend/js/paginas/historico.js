// Tela do histórico de um jogador (RF18): nome, estatísticas e as últimas partidas.
// Abre como historico.html?jogador={usuario_id}, pelo nome de um jogador no ranking do lobby;
// sem o parâmetro, mostra o histórico do próprio usuário ("Meu histórico", no cabeçalho do
// lobby). Os dados chegam uma vez só, ao abrir a página, de GET /api/ranking/jogadores/{id}.
// Como no lobby, a área principal é desenhada por inteiro, a partir do estado, por uma única
// função (renderizar); nenhum outro trecho mexe no DOM dela.

import { ErroApi, obterJogador } from "../api.js";
import { exigirLogin, obterUsuario, sair } from "../auth.js";
import { criarVerso } from "../cartas.js";

const PAGINA_LOGIN = "index.html";
const PAGINA_LOBBY = "lobby.html";

const tela = document.getElementById("tela");
const areaUsuario = document.getElementById("usuario");
const conteudo = document.getElementById("conteudo");

// Usuário logado ({ id, nome, email }), lido da sessão ao abrir a página.
let usuario = null;

// Jogador cujo histórico está na tela: o do parâmetro ?jogador= ou o próprio usuário.
let jogadorId = null;

// Estado da tela: "carregando", "pronto" (com o jogador), "vazio" (o jogador nunca terminou
// uma partida: a rota responde 404) ou "erro" (com a mensagem).
const estado = { situacao: "carregando", jogador: null, mensagem: "" };

// ---------- Utilitários ----------

// Cria um elemento com classes e texto opcionais.
function el(tag, classes = "", texto = "") {
  const elemento = document.createElement(tag);
  if (classes) elemento.className = classes;
  if (texto !== "") elemento.textContent = texto;
  return elemento;
}

// Nome de um jogador. Nomes longos são cortados com reticências pelo CSS; o nome inteiro fica
// no title.
function criarNome(nome, classes = "nome-jogador") {
  const elemento = el("span", classes, nome);
  elemento.title = nome;
  return elemento;
}

// Texto para mostrar ao usuário: a mensagem do ErroApi ou, num erro inesperado (um bug), um
// aviso genérico, com o detalhe no console.
function textoDoErro(erro) {
  if (erro instanceof ErroApi) return erro.mensagem;
  console.error(erro);
  return "Algo deu errado. Tente de novo.";
}

function souEu() {
  return jogadorId === usuario.id;
}

function outroTime(time) {
  return time === "A" ? "B" : "A";
}

// "67%": vitórias sobre partidas, arredondado.
function aproveitamento(vitorias, partidas) {
  return partidas ? `${Math.round((vitorias / partidas) * 100)}%` : "—";
}

// ---------- Renderização ----------

// Nome do usuário logado e o link de volta ao lobby, no cabeçalho.
function renderizarUsuario() {
  const nome = criarNome(usuario.nome, "usuario-nome");
  nome.title = usuario.email ?? usuario.nome;
  const voltar = el("a", "botao", "Voltar ao lobby");
  voltar.href = PAGINA_LOBBY;
  areaUsuario.replaceChildren(nome, voltar);
}

function renderizar() {
  const raiz = el("section", "historico");
  raiz.setAttribute("aria-labelledby", "titulo-historico");

  if (estado.situacao === "carregando") {
    raiz.append(criarPerfil(null), el("p", "carregando", "Carregando histórico…"));
  } else if (estado.situacao === "erro") {
    raiz.append(criarPerfil(null), criarErro());
  } else if (estado.situacao === "vazio") {
    raiz.append(criarPerfil(null), criarVazio());
  } else {
    const { jogador } = estado;
    raiz.append(criarPerfil(jogador), criarEstatisticas(jogador), criarPartidas(jogador));
  }
  conteudo.replaceChildren(raiz);
}

// Topo: de quem é o histórico e a posição no ranking. Sem os dados do jogador (carregando,
// erro ou sem partidas), só o próprio usuário tem nome conhecido.
function criarPerfil(jogador) {
  const perfil = el("div", "perfil");
  const nome = jogador?.nome ?? (souEu() ? usuario.nome : null);
  perfil.append(el("p", "perfil-rotulo", souEu() ? "Seu histórico" : "Histórico do jogador"));

  const titulo = el("h2", "perfil-titulo");
  titulo.id = "titulo-historico";
  titulo.append(nome ? criarNome(nome, "perfil-nome") : el("span", "perfil-nome", "Jogador"));
  if (souEu()) titulo.append(el("span", "voce", "(você)"));
  perfil.append(titulo);

  if (jogador) perfil.append(el("p", "perfil-posicao", `${jogador.posicao}º no ranking`));
  document.title = `Truco Online — ${nome ? `Histórico de ${nome}` : "Histórico"}`;
  return perfil;
}

// Quatro números em cartões creme, como as salas do lobby.
function criarEstatisticas(jogador) {
  const lista = el("ul", "estatisticas");
  lista.setAttribute("aria-label", "Estatísticas");
  const itens = [
    ["Vitórias", String(jogador.vitorias)],
    ["Derrotas", String(jogador.derrotas)],
    ["Partidas", String(jogador.partidas)],
    ["Aproveitamento", aproveitamento(jogador.vitorias, jogador.partidas)],
  ];
  for (const [rotulo, valor] of itens) {
    const item = el("li", "estatistica");
    item.append(el("span", "estatistica-valor", valor), el("span", "estatistica-rotulo", rotulo));
    lista.append(item);
  }
  return lista;
}

// Jogadores de um lado da partida (parceiro ou adversários), um por linha, com o selo de bot.
function criarListaDeJogadores(jogadores) {
  if (jogadores.length === 0) return el("span", "sem-jogador", "—");
  const lista = el("ul", "jogadores");
  for (const jogador of jogadores) {
    const item = el("li", "jogador");
    item.append(criarNome(jogador.nome));
    if (jogador.bot) item.append(el("span", "selo-bot", "BOT"));
    lista.append(item);
  }
  return lista;
}

// Data e hora em que a partida acabou, no fuso do navegador: "28/10/2026" e "14:46".
function criarData(texto) {
  const data = new Date(texto);
  const celula = el("td", "data");
  const quando = el("time");
  quando.dateTime = texto;
  quando.append(
    el("span", "data-dia", data.toLocaleDateString("pt-BR")),
    el("span", "data-hora", data.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })),
  );
  celula.append(quando);
  return celula;
}

// Uma linha da tabela: data, formato, parceiro, adversários, placar (os pontos do time do
// jogador primeiro) e o resultado.
function criarLinhaPartida(partida, jogador) {
  const meuTime = partida.time;
  const timeAdversario = outroTime(meuTime);
  const parceiros = partida.times[meuTime].filter((j) => j.usuario_id !== jogador.usuario_id);
  const adversarios = partida.times[timeAdversario];

  const linha = el("tr", partida.venceu ? "vitoria" : "derrota");
  const parceiro = el("td", "lado");
  parceiro.append(criarListaDeJogadores(parceiros));
  const contra = el("td", "lado");
  contra.append(criarListaDeJogadores(adversarios));

  const nos = partida.placar_final[meuTime];
  const eles = partida.placar_final[timeAdversario];
  const placar = el("td", "placar", `${nos} × ${eles}`);
  placar.setAttribute("aria-label", `${nos} a ${eles}`);

  const resultado = el("td", "resultado");
  resultado.append(el("span", "selo-resultado", partida.venceu ? "Vitória" : "Derrota"));

  linha.append(criarData(partida.encerrada_em), el("td", "formato", partida.formato), parceiro, contra, placar, resultado);
  return linha;
}

// As últimas partidas numa tabela sobre um cartão creme, como uma súmula.
function criarPartidas(jogador) {
  const secao = el("section", "partidas");
  secao.setAttribute("aria-labelledby", "titulo-partidas");
  const titulo = el("h2", "secao-titulo", "Últimas partidas");
  titulo.id = "titulo-partidas";
  secao.append(titulo);

  const tabela = el("table", "tabela-partidas");
  const cabeca = el("tr");
  const colunas = [
    ["Data", "data"],
    ["Formato", "formato"],
    ["Parceiro", "lado"],
    ["Adversários", "lado"],
    ["Placar", "placar"],
    ["Resultado", "resultado"],
  ];
  for (const [texto, classe] of colunas) {
    const celula = el("th", classe, texto);
    celula.scope = "col";
    cabeca.append(celula);
  }
  const thead = el("thead");
  thead.append(cabeca);
  const corpo = el("tbody");
  for (const partida of jogador.ultimas_partidas) corpo.append(criarLinhaPartida(partida, jogador));
  tabela.append(thead, corpo);

  const cartao = el("div", "cartao-partidas");
  cartao.append(tabela);
  secao.append(cartao);
  return secao;
}

// Quem nunca terminou uma partida: três cartas viradas e um convite, como a lista de salas vazia.
function criarVazio() {
  const vazio = el("div", "historico-vazio");
  const cartas = el("div", "cartas-viradas");
  cartas.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) cartas.append(criarVerso());
  const texto = souEu()
    ? "Quando você terminar a primeira partida, as suas vitórias e as últimas partidas aparecem aqui. Crie uma sala no lobby e chame a turma, ou complete a mesa com bots."
    : "Este jogador ainda não terminou nenhuma partida.";
  vazio.append(cartas, el("p", "historico-vazio-titulo", "Nenhuma partida ainda"), el("p", "historico-vazio-texto", texto));
  return vazio;
}

function criarErro() {
  const caixa = el("div", "historico-erro");
  const tentar = el("button", "botao", "Tentar de novo");
  tentar.type = "button";
  tentar.addEventListener("click", carregar);
  caixa.append(el("p", "historico-erro-texto", estado.mensagem), tentar);
  return caixa;
}

// ---------- Dados ----------

async function carregar() {
  estado.situacao = "carregando";
  renderizar();
  try {
    estado.jogador = await obterJogador(jogadorId);
    estado.situacao = "pronto";
  } catch (erro) {
    // 401: o api.js já apagou a sessão e está levando para a tela de login.
    if (erro instanceof ErroApi && erro.status === 401) return;
    if (erro instanceof ErroApi && erro.status === 404) {
      estado.situacao = "vazio";
    } else {
      estado.situacao = "erro";
      estado.mensagem = textoDoErro(erro);
    }
  }
  renderizar();
}

// ---------- Início ----------

function iniciar() {
  usuario = obterUsuario();
  // Token sem os dados do usuário (sessão corrompida): melhor entrar de novo, como no lobby.
  if (!usuario?.id) {
    sair();
    location.replace(PAGINA_LOGIN);
    return;
  }
  jogadorId = new URLSearchParams(location.search).get("jogador") || usuario.id;

  renderizarUsuario();
  tela.hidden = false;
  carregar();

  // Voltando pelo histórico do navegador, a página pode voltar congelada, com dados antigos.
  window.addEventListener("pageshow", (evento) => {
    if (evento.persisted) location.reload();
  });
}

if (exigirLogin()) iniciar();
