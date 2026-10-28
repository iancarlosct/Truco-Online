// Tela da mesa de jogo.
// Toda a mesa é desenhada por renderizarMesa(estado), que limpa e redesenha a partir do estado.
// Nenhuma regra do jogo é implementada aqui: a interface só habilita ou desabilita controles
// conforme o estado recebido; quem valida as ações é o servidor.
// A página abre como mesa.html?partida={partida_id} (o lobby manda para cá quando a partida
// começa) e conversa com o Game pelo ws.js. Até o primeiro estado chegar, mostra só uma espera.
// Sem ?partida=, mostra os estados falsos do seletor de desenvolvimento.

import { prepararAnimacoes } from "../animacoes.js";
import { exigirLogin } from "../auth.js";
import { criarCarta, criarVerso, proximaManilha } from "../cartas.js";
import * as mocks from "../mock/estados.js";
import { conectarPartida } from "../ws.js";

const PAGINA_LOBBY = "lobby.html";

// Tempo que um erro do servidor fica na barra de ações, e espera antes de voltar ao lobby
// quando a partida recusa o jogador.
const DURACAO_ERRO_MS = 4000;
const ESPERA_RECUSA_MS = 5000;

// Posição na tela de cada assento relativo ao jogador (sentido anti-horário).
const POSICOES = {
  2: ["baixo", "cima"],
  4: ["baixo", "direita", "cima", "esquerda"],
};

const NOMES_TIPO = { mao_de_onze: "Mão de onze", mao_de_ferro: "Mão de ferro" };

// Nome do pedido conforme o valor proposto, e texto do botão conforme o valor atual da mão.
const NOME_PEDIDO = { 3: "Truco", 6: "Seis", 9: "Nove", 12: "Doze" };
const PROXIMO_PEDIDO = { 1: "Truco", 3: "Seis", 6: "Nove", 9: "Doze", 12: "Doze" };

const app = document.getElementById("app");
const anuncio = document.getElementById("anuncio");

// Último estado desenhado (usado para redesenhar quando muda algo local, como "Jogar coberta").
let estadoAtual = null;

// Conexão com a partida ({ enviar, fechar }, do ws.js). Fica null com os estados falsos.
let conexao = null;

// Estado local da interface, que não vem do servidor.
const ui = {
  coberta: false,
  rascunhoChat: "",
  focoChat: false,
  // "conectando", "conectado", "reconectando" ou "recusada"; "local" com os estados falsos
  conexao: "local",
  motivoRecusa: "",
  erro: null, // mensagem do último erro do servidor, enquanto estiver na tela
  confirmandoSaida: false,
  focarChave: null, // controle (data-chave) que recebe o foco no próximo desenho
  // O próximo estado é o primeiro desta conexão (ao abrir a mesa, depois de um F5 ou de uma
  // queda): é desenhado direto, sem animação.
  primeiroEstado: true,
};
let temporizadorErro = null;

// ---------- Utilitários ----------

// Cria um elemento com classes e texto opcionais.
function el(tag, classes = "", texto = "") {
  const elemento = document.createElement(tag);
  if (classes) elemento.className = classes;
  if (texto !== "") elemento.textContent = texto;
  return elemento;
}

function classeTime(time) {
  return time === "A" ? "time-a" : "time-b";
}

// Reúne tudo o que a tela precisa saber e que é derivado do estado.
function derivar(estado) {
  const n = estado.jogadores.length;
  const eu = estado.jogadores.find((j) => j.assento === estado.meu_assento);
  const meuTime = eu.time;
  const maoAtual = estado.mao_atual;
  const truco = maoAtual.truco_pendente;
  const minhaVez = maoAtual.vez_assento === estado.meu_assento;
  const encerrada = estado.status === "encerrada";
  const conectado = ui.conexao === "conectado" || ui.conexao === "local";
  // Com a conexão caída ou a partida encerrada, nenhum controle de jogo fica clicável.
  const podeAgir = conectado && !encerrada;
  // Rodada que a próxima carta joga. A rodada nova só entra em "rodadas" com a primeira carta
  // dela (assim a rodada encerrada continua na mesa): se a última já tem vencedor, é a seguinte.
  const ultima = maoAtual.rodadas.at(-1);
  let numeroRodada = maoAtual.rodadas.length;
  if (!ultima || ultima.vencedor_time) numeroRodada++;

  return {
    eu,
    meuTime,
    timeAdversario: meuTime === "A" ? "B" : "A",
    minhaVez,
    encerrada,
    podeAgir,
    reconectando: ui.conexao === "reconectando",
    erro: ui.erro,
    // O chat continua valendo depois do fim da partida; só precisa da conexão.
    podeConversar: conectado,
    posicaoDe: (assento) => POSICOES[n][(assento - estado.meu_assento + n) % n],
    timeDe: (assento) => estado.jogadores.find((j) => j.assento === assento)?.time,
    podeJogar: podeAgir && minhaVez && !truco && !maoAtual.aguardando_decisao_mao_de_onze,
    podePedirTruco:
      podeAgir &&
      minhaVez &&
      !truco &&
      maoAtual.valor < 12 &&
      maoAtual.ultimo_aumento_time !== meuTime &&
      maoAtual.tipo === "normal",
    // Truco e mão de onze valem para o time: no 2x2, os dois parceiros podem responder.
    trucoContraMim: Boolean(truco) && truco.pedido_por_time !== meuTime,
    decidindoMaoDeOnze: maoAtual.aguardando_decisao_mao_de_onze && estado.placar[meuTime] === 11,
    numeroRodada,
    // A mão está em jogo (alguém tem a vez): entre as mãos e depois do fim, não.
    maoEmJogo: maoAtual.vez_assento !== null && maoAtual.vez_assento !== undefined && !encerrada,
    // "Jogar coberta" só fica disponível a partir da segunda rodada da mão.
    podeCobrir: numeroRodada >= 2,
  };
}

// ---------- Envio de ações ----------

// Único ponto de saída das ações do jogador: vai pela conexão com a partida. Com os estados
// falsos, que não têm conexão, só registra no console. Devolve false se a mensagem não saiu.
export function enviar(mensagem) {
  if (conexao) return conexao.enviar(mensagem);
  console.log("[enviar]", mensagem);
  return true;
}

function jogarCarta(carta) {
  enviar({ tipo: "jogar_carta", carta, coberta: ui.coberta && derivar(estadoAtual).podeCobrir });
  ui.coberta = false;
  renderizarMesa(estadoAtual);
}

function alternarCoberta(marcada) {
  ui.coberta = marcada;
  renderizarMesa(estadoAtual);
}

// Se a mensagem não sair (a conexão caiu), o rascunho fica no campo.
function enviarChat(texto) {
  if (!texto || !enviar({ tipo: "chat", texto })) return;
  ui.rascunhoChat = "";
  ui.focoChat = true;
  renderizarMesa(estadoAtual);
}

// ---------- Componentes ----------

// Mão do próprio jogador: cartas abertas, clicáveis apenas quando podeJogar. Com "Jogar
// coberta" marcada, cada carta mostra que vai para a mesa virada.
function criarMao(cartas, podeJogar, cobrindo, aoJogar) {
  const mao = el("div", cobrindo ? "mao cobrindo" : "mao");
  for (const codigo of cartas) {
    const botao = el("button", "carta-mao");
    botao.type = "button";
    botao.dataset.chave = `carta:${codigo}`;
    botao.disabled = !podeJogar;
    const carta = criarCarta(codigo);
    if (cobrindo) botao.setAttribute("aria-label", `${carta.alt}, coberta`);
    botao.append(carta);
    botao.addEventListener("click", () => aoJogar(codigo));
    mao.append(botao);
  }
  return mao;
}

// Mão do parceiro, que o time com 11 pontos vê na mão de onze: cartas abertas, menores e só
// para olhar.
function criarMaoParceiro(cartas) {
  const mao = el("div", "mao-parceiro");
  mao.setAttribute("role", "group");
  mao.setAttribute("aria-label", "Mão do parceiro");
  for (const codigo of cartas) mao.append(criarCarta(codigo));
  return mao;
}

// Mão de outro jogador: apenas versos, na quantidade informada.
function criarMaoOculta(quantidade) {
  const mao = el("div", "mao-oculta");
  for (let i = 0; i < quantidade; i++) {
    const espaco = el("span", "espaco");
    espaco.append(criarVerso());
    mao.append(espaco);
  }
  return mao;
}

// Nome de um jogador. Nomes longos são cortados com reticências pelo CSS; o nome inteiro fica
// no title.
function criarNome(nome, classes) {
  const elemento = el("span", classes, nome);
  elemento.title = nome;
  return elemento;
}

// Jogador na mesa: plaquinha (time, nome, selos) + a mão já montada.
function criarJogador(jogador, { posicao, naVez, souEu, mao }) {
  const raiz = el("div", `jogador pos-${posicao} ${classeTime(jogador.time)}`);
  raiz.dataset.assento = jogador.assento;
  if (naVez) raiz.classList.add("na-vez");

  const plaquinha = el("div", "plaquinha");
  plaquinha.title = `Time ${jogador.time}`;
  plaquinha.append(el("span", "cor-time"), criarNome(jogador.nome, "nome"));
  if (souEu) plaquinha.append(el("span", "voce", "(você)"));
  if (jogador.bot) plaquinha.append(el("span", "selo-bot", "BOT"));
  plaquinha.append(el("span", "selo-vez", "vez"));

  // Embaixo a mão fica acima da plaquinha; nas outras posições, do lado do centro.
  if (posicao === "baixo") raiz.append(mao, plaquinha);
  else raiz.append(plaquinha, mao);
  return raiz;
}

// Marcadores das 3 rodadas da mão. Com a mão em jogo, a rodada que a próxima carta joga ganha
// o contorno de "rodada atual".
function criarRodadas(rodadas, ctx) {
  const bloco = el("div", "rodadas");
  const marcadores = el("div", "marcadores");
  for (let i = 0; i < 3; i++) {
    const vencedor = rodadas[i]?.vencedor_time ?? null;
    const marcador = el("span", "marcador");
    if (vencedor === "empate") marcador.classList.add("empate");
    else if (vencedor) marcador.classList.add(classeTime(vencedor));
    else if (ctx.maoEmJogo && i === ctx.numeroRodada - 1) marcador.classList.add("atual");
    marcadores.append(marcador);
  }
  bloco.append(el("span", "rotulo-mesa", "Rodadas"), marcadores);
  return bloco;
}

// Centro da mesa: cartas da última rodada (a atual, ou a que acabou de terminar), vira com a
// manilha e marcadores das rodadas. Na rodada decidida, as cartas do time vencedor ficam em
// destaque enquanto ela continua na mesa: o estado diz só o time que venceu, não a carta.
function criarCentro(maoAtual, ctx) {
  const { posicaoDe, timeDe } = ctx;
  const centro = el("div", "centro");

  const rodadaAtual = maoAtual.rodadas.at(-1);
  const jogadas = el("div", "jogadas");
  for (const jogada of rodadaAtual?.jogadas ?? []) {
    const item = el("div", `jogada pos-${posicaoDe(jogada.assento)}`);
    item.dataset.assento = jogada.assento;
    const vencedor = rodadaAtual.vencedor_time;
    if (vencedor === timeDe(jogada.assento)) item.classList.add("vencedora", classeTime(vencedor));
    item.append(jogada.coberta || !jogada.carta ? criarVerso() : criarCarta(jogada.carta));
    jogadas.append(item);
  }

  const vira = el("div", "vira");
  const manilha = el("span", "manilha", "Manilha: ");
  manilha.append(el("strong", "", proximaManilha(maoAtual.vira)));
  vira.append(el("span", "rotulo-mesa", "Vira"), criarCarta(maoAtual.vira), manilha);

  centro.append(jogadas, vira, criarRodadas(maoAtual.rodadas, ctx));
  return centro;
}

// Placar relativo ao jogador ("Nós" e "Eles"), valor da mão e selo do tipo de mão.
function criarPlacar(placar, maoAtual, meuTime, timeAdversario) {
  const raiz = el("div", "placar");

  const times = el("div", "placar-times");
  for (const [rotulo, time] of [["Nós", meuTime], ["Eles", timeAdversario]]) {
    const bloco = el("div", `placar-time ${classeTime(time)}`);
    bloco.append(el("span", "rotulo", rotulo), el("span", "pontos", String(placar[time])));
    times.append(bloco);
  }

  const mao = el("div", "placar-mao");
  const valor = el("span", "", "Valendo ");
  valor.append(el("strong", "", String(maoAtual.valor)));
  mao.append(el("span", "", `Mão ${maoAtual.numero}`), valor);

  raiz.append(times, mao);
  if (NOMES_TIPO[maoAtual.tipo]) raiz.append(el("div", "selo-tipo", NOMES_TIPO[maoAtual.tipo]));
  return raiz;
}

// Texto de situação mostrado na barra de ações. A conexão caída e o erro recente de uma ação
// passam na frente da situação da mão.
function textoAviso(maoAtual, ctx, jogadores) {
  const truco = maoAtual.truco_pendente;
  if (ctx.reconectando) return "Conexão perdida. Reconectando…";
  if (ctx.erro) return ctx.erro;
  if (ctx.encerrada) return "Fim de partida.";
  if (ctx.trucoContraMim) return `Time adversário pediu ${NOME_PEDIDO[truco.valor_proposto]}!`;
  if (truco) return `Aguardando o adversário responder ao pedido de ${NOME_PEDIDO[truco.valor_proposto]}…`;
  if (ctx.decidindoMaoDeOnze) return "Mão de onze: seu time decide se joga ou corre.";
  if (maoAtual.aguardando_decisao_mao_de_onze) return "Aguardando o adversário decidir a mão de onze…";
  if (ctx.minhaVez) return "Sua vez de jogar.";
  const daVez = jogadores.find((j) => j.assento === maoAtual.vez_assento);
  // Sem vez de ninguém, a mão acabou e a próxima ainda não foi distribuída.
  return daVez ? `Vez de ${daVez.nome}.` : "Fim da mão.";
}

// Botão da barra de ações: desabilitado quando não se aplica; ao clicar envia a mensagem.
// A chave (tipo e resposta da mensagem) devolve o foco ao botão depois de cada desenho.
function criarBotaoAcao(texto, classes, ativo, mensagem) {
  const botao = el("button", `botao ${classes}`, texto);
  botao.type = "button";
  botao.dataset.chave = [mensagem.tipo, mensagem.resposta ?? mensagem.jogar].join(":");
  botao.disabled = !ativo;
  botao.addEventListener("click", () => enviar(mensagem));
  return botao;
}

// Barra de ações abaixo da mão: aviso, truco, resposta ao truco, jogar coberta e mão de onze.
function criarBarraAcoes(maoAtual, ctx, jogadores, coberta, aoAlternarCoberta) {
  const barra = el("div", "barra-acoes");

  const aviso = el("p", "aviso", textoAviso(maoAtual, ctx, jogadores));
  if (ctx.reconectando) aviso.classList.add("conexao");
  else if (ctx.erro) aviso.classList.add("erro");
  else if (!ctx.encerrada && (ctx.trucoContraMim || ctx.decidindoMaoDeOnze)) aviso.classList.add("alerta");

  const controles = el("div", "controles");
  const podeResponder = ctx.podeAgir && ctx.trucoContraMim;
  const podeAumentar = podeResponder && maoAtual.truco_pendente.valor_proposto < 12;

  const resposta = el("div", "grupo");
  resposta.append(
    criarBotaoAcao("Aceitar", "botao-aceitar", podeResponder, { tipo: "responder_truco", resposta: "aceitar" }),
    criarBotaoAcao("Correr", "botao-correr", podeResponder, { tipo: "responder_truco", resposta: "correr" }),
    criarBotaoAcao("Aumentar", "", podeAumentar, { tipo: "responder_truco", resposta: "aumentar" }),
  );

  const alternador = el("label", "alternador");
  const caixa = el("input");
  caixa.type = "checkbox";
  caixa.dataset.chave = "coberta";
  caixa.disabled = !ctx.podeCobrir;
  caixa.checked = coberta && ctx.podeCobrir;
  caixa.addEventListener("change", () => aoAlternarCoberta(caixa.checked));
  if (caixa.disabled) alternador.classList.add("desabilitado");
  alternador.append(caixa, el("span", "", "Jogar coberta"));

  controles.append(
    criarBotaoAcao(PROXIMO_PEDIDO[maoAtual.valor] ?? "Truco", "botao-truco", ctx.podePedirTruco, { tipo: "pedir_truco" }),
    el("span", "separador"),
    resposta,
    el("span", "separador"),
    alternador,
  );

  // Os botões da mão de onze são os únicos que aparecem e somem.
  if (ctx.decidindoMaoDeOnze) {
    const onze = el("div", "grupo");
    onze.append(
      criarBotaoAcao("Jogar a mão", "botao-aceitar", ctx.podeAgir, { tipo: "decidir_mao_de_onze", jogar: true }),
      criarBotaoAcao("Correr", "botao-correr", ctx.podeAgir, { tipo: "decidir_mao_de_onze", jogar: false }),
    );
    controles.append(el("span", "separador"), onze);
  }

  barra.append(aviso, controles);
  return barra;
}

// Painel lateral do chat: mensagens (autor + texto), campo de texto e botão enviar. Sem
// conexão, dá para escrever, mas não para enviar.
function criarChat(mensagens, jogadores, rascunho, podeEnviar, aoEnviar, aoDigitar) {
  const painel = el("aside", "chat");
  painel.append(el("h2", "chat-titulo", "Chat"));

  const lista = el("ul", "chat-mensagens");
  if (mensagens.length === 0) lista.append(el("li", "chat-vazio", "Nenhuma mensagem ainda."));
  for (const mensagem of mensagens) {
    const item = el("li", "chat-mensagem");
    // O autor ganha a cor do time quando o nome corresponde a um jogador da mesa.
    const autor = jogadores.find((j) => j.nome === mensagem.de);
    item.append(criarNome(mensagem.de, `autor ${autor ? classeTime(autor.time) : ""}`), el("span", "texto", mensagem.texto));
    lista.append(item);
  }

  const formulario = el("form", "chat-formulario");
  const campo = el("input", "chat-campo");
  campo.type = "text";
  campo.placeholder = "Escreva uma mensagem…";
  campo.maxLength = 200;
  campo.autocomplete = "off";
  campo.value = rascunho;
  campo.addEventListener("input", () => aoDigitar(campo.value));
  const botao = el("button", "botao botao-enviar", "Enviar");
  botao.type = "submit";
  // Com o único botão de envio desabilitado, o Enter também não envia o formulário.
  botao.disabled = !podeEnviar;
  // O envio do formulário cobre tanto o clique no botão quanto a tecla Enter.
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    aoEnviar(campo.value.trim());
  });
  formulario.append(campo, botao);

  painel.append(lista, formulario);
  return painel;
}

// ---------- Saída, fim de partida e espera ----------

// Botão da interface; a chave identifica o botão entre um desenho e outro.
function criarBotao(texto, classes, chave, aoClicar) {
  const botao = el("button", classes, texto);
  botao.type = "button";
  botao.dataset.chave = chave;
  botao.addEventListener("click", aoClicar);
  return botao;
}

// Botão discreto no canto da mesa. A saída é confirmada na própria tela.
function criarBotaoSair() {
  return criarBotao("Sair da partida", "botao-sair", "sair", pedirSaida);
}

// Confirmação da saída, sobre a mesa. Esc também cancela.
function criarConfirmacaoSaida() {
  const caixa = el("div", "dialogo");
  caixa.setAttribute("role", "alertdialog");
  caixa.setAttribute("aria-modal", "true");
  caixa.setAttribute("aria-labelledby", "dialogo-titulo");
  caixa.setAttribute("aria-describedby", "dialogo-texto");
  const titulo = el("h2", "dialogo-titulo", "Sair da partida?");
  titulo.id = "dialogo-titulo";
  const texto = el("p", "dialogo-texto", "Você deixa a mesa e volta ao lobby.");
  texto.id = "dialogo-texto";
  const botoes = el("div", "dialogo-botoes");
  botoes.append(
    criarBotao("Continuar jogando", "botao", "saida:ficar", cancelarSaida),
    criarBotao("Sair da partida", "botao botao-correr", "saida:sair", voltarAoLobby),
  );
  caixa.append(titulo, texto, botoes);

  const fundo = el("div", "sobreposicao");
  fundo.append(caixa);
  return fundo;
}

// Resultado do ponto de vista do jogador. No 1x1 o time é uma pessoa só.
function tituloDoFim(estado, meuTime) {
  const venceu = estado.vencedor_time === meuTime;
  if (estado.jogadores.length === 2) return venceu ? "Você venceu!" : "Você perdeu";
  return venceu ? "Vocês venceram!" : "Vocês perderam";
}

// Tela de fim de partida, sobre a mesa: o resultado, o placar final e a volta ao lobby. O chat
// continua usável ao lado.
function criarFimDePartida(estado, ctx) {
  const venceu = estado.vencedor_time === ctx.meuTime;
  const cartao = el("section", `fim-partida ${venceu ? "vitoria" : "derrota"}`);
  cartao.setAttribute("aria-labelledby", "fim-titulo");
  const titulo = el("h2", "fim-titulo", tituloDoFim(estado, ctx.meuTime));
  titulo.id = "fim-titulo";

  const placar = el("div", "fim-placar");
  for (const [rotulo, time] of [["Nós", ctx.meuTime], ["Eles", ctx.timeAdversario]]) {
    const bloco = el("div", `fim-time ${classeTime(time)}`);
    bloco.append(el("span", "rotulo", rotulo), el("span", "pontos", String(estado.placar[time])));
    placar.append(bloco);
  }

  cartao.append(
    el("p", "fim-rotulo", "Fim de partida"),
    titulo,
    placar,
    criarBotao("Voltar ao lobby", "botao-principal", "voltar-lobby", voltarAoLobby),
  );
  const fundo = el("div", "sobreposicao");
  fundo.append(cartao);
  return fundo;
}

// Antes do primeiro estado (conectando, tentando de novo ou recusado pela partida), no lugar
// da mesa, que ainda não tem o que mostrar.
function renderizarEspera() {
  const raiz = el("section", "espera");
  const cartas = el("div", "espera-cartas");
  cartas.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) cartas.append(criarVerso());

  let titulo = "Conectando à partida…";
  let texto = "";
  if (ui.conexao === "reconectando") {
    texto = "Não foi possível conectar. Tentando de novo…";
  } else if (ui.conexao === "recusada") {
    titulo = ui.motivoRecusa;
    texto = "Voltando ao lobby…";
  }
  raiz.append(cartas, el("h1", "espera-titulo", titulo));
  if (texto) raiz.append(el("p", "espera-texto", texto));
  raiz.append(criarBotao("Voltar ao lobby", "botao", "voltar-lobby", voltarAoLobby));
  trocarTela(raiz);
}

// ---------- Renderização ----------

// Troca o conteúdo da página. Como tudo é refeito, o foco volta para o controle de mesma chave
// (data-chave), se ele ainda existir: sem isso, quem usa o teclado perderia o lugar a cada
// estado recebido. ui.focarChave escolhe outro controle para o foco.
function trocarTela(conteudo) {
  const chave = ui.focarChave ?? document.activeElement?.dataset?.chave;
  ui.focarChave = null;
  app.replaceChildren(conteudo);
  if (chave) app.querySelector(`[data-chave="${CSS.escape(chave)}"]`)?.focus();
}

// Limpa a tela e redesenha tudo a partir do estado.
export function renderizarMesa(estado) {
  estadoAtual = estado;
  const ctx = derivar(estado);
  const maoAtual = estado.mao_atual;
  // Depois do fim, a saída é pela tela de fim de partida, sem confirmação.
  if (ctx.encerrada) ui.confirmandoSaida = false;

  const feltro = el("div", "feltro");
  feltro.append(
    criarPlacar(estado.placar, maoAtual, ctx.meuTime, ctx.timeAdversario),
    criarCentro(maoAtual, ctx),
  );
  if (!ctx.encerrada) feltro.append(criarBotaoSair());
  for (const jogador of estado.jogadores) {
    const souEu = jogador.assento === estado.meu_assento;
    // A mão de outro jogador só vem do servidor na mão de onze, para o parceiro do time com 11.
    let mao;
    if (souEu) mao = criarMao(jogador.mao ?? [], ctx.podeJogar, ui.coberta && ctx.podeCobrir, jogarCarta);
    else if (jogador.mao) mao = criarMaoParceiro(jogador.mao);
    else mao = criarMaoOculta(jogador.qtd_cartas);
    feltro.append(
      criarJogador(jogador, {
        posicao: ctx.posicaoDe(jogador.assento),
        naVez: jogador.assento === maoAtual.vez_assento,
        souEu,
        mao,
      }),
    );
  }

  const mesa = el("div", "mesa");
  mesa.append(feltro);
  const barra = criarBarraAcoes(maoAtual, ctx, estado.jogadores, ui.coberta, alternarCoberta);

  const areaMesa = el("section", "area-mesa");
  areaMesa.append(mesa, barra);

  const chat = criarChat(estado.chat, estado.jogadores, ui.rascunhoChat, ctx.podeConversar, enviarChat, (texto) => {
    ui.rascunhoChat = texto;
  });

  // Por cima da mesa, a tela de fim de partida ou a confirmação de saída. O que fica por baixo
  // não recebe clique nem foco; na confirmação, nem o chat.
  if (ctx.encerrada) {
    areaMesa.append(criarFimDePartida(estado, ctx));
    mesa.inert = true;
    barra.inert = true;
  } else if (ui.confirmandoSaida) {
    areaMesa.append(criarConfirmacaoSaida());
    mesa.inert = true;
    barra.inert = true;
    chat.inert = true;
  }

  // O foco do campo do chat é devolvido depois de redesenhar; o dos botões, por trocarTela.
  const campoChat = chat.querySelector(".chat-campo");
  const devolverFoco = ui.focoChat;
  campoChat.addEventListener("focus", () => { ui.focoChat = true; });
  campoChat.addEventListener("blur", () => { ui.focoChat = false; });

  const tela = el("div", "tela");
  tela.append(areaMesa, chat);
  trocarTela(tela);

  // Rolagem automática do chat até a última mensagem.
  const mensagens = chat.querySelector(".chat-mensagens");
  mensagens.scrollTop = mensagens.scrollHeight;
  ui.focoChat = devolverFoco;
  if (devolverFoco) campoChat.focus();
}

// ---------- Conexão com a partida ----------

// Desenha o que houver para desenhar: a mesa, se já chegou algum estado, ou a espera.
function redesenhar() {
  if (estadoAtual && ui.conexao !== "recusada") renderizarMesa(estadoAtual);
  else renderizarEspera();
}

// Texto para o leitor de tela, na região #anuncio, que fica fora da mesa redesenhada.
function anunciar(texto) {
  anuncio.textContent = texto;
}

// Erro de uma ação: aparece na barra de ações por alguns segundos, sem bloquear a mesa.
function mostrarErro(mensagem) {
  ui.erro = mensagem || "A ação não foi aceita.";
  anunciar(ui.erro);
  clearTimeout(temporizadorErro);
  temporizadorErro = setTimeout(() => {
    ui.erro = null;
    redesenhar();
  }, DURACAO_ERRO_MS);
  redesenhar();
}

// Fecha a conexão e volta ao lobby. A mesa sai do histórico: o botão Voltar do navegador, no
// lobby, não traz de volta a partida.
function voltarAoLobby() {
  conexao?.fechar();
  location.replace(PAGINA_LOBBY);
}

function pedirSaida() {
  ui.confirmandoSaida = true;
  ui.focarChave = "saida:ficar";
  redesenhar();
}

function cancelarSaida() {
  ui.confirmandoSaida = false;
  ui.focarChave = "sair";
  redesenhar();
}

function receberEstado(estado) {
  // A partida acabou de terminar (ou já chegou terminada): o foco vai para "Voltar ao lobby",
  // a menos que o jogador esteja escrevendo no chat.
  if (estado.status === "encerrada" && estadoAtual?.status !== "encerrada") {
    if (!ui.focoChat) ui.focarChave = "voltar-lobby";
    const eu = estado.jogadores.find((j) => j.assento === estado.meu_assento);
    anunciar(`Fim de partida. ${tituloDoFim(estado, eu.time)}`);
  }
  // As animações comparam o estado anterior com o novo: medem a mesa antiga antes de redesenhar
  // e animam a nova logo depois (js/animacoes.js).
  const animar = prepararAnimacoes(ui.primeiroEstado ? null : estadoAtual, estado, app);
  ui.primeiroEstado = false;
  renderizarMesa(estado);
  animar();
}

function mudarConexao(situacao, motivo) {
  const anterior = ui.conexao;
  ui.conexao = situacao;
  if (situacao === "conectado") ui.primeiroEstado = true;
  if (situacao === "recusada") {
    ui.motivoRecusa = motivo;
    anunciar(`${motivo} Voltando ao lobby…`);
    setTimeout(voltarAoLobby, ESPERA_RECUSA_MS);
  } else if (estadoAtual && situacao === "reconectando" && anterior !== "reconectando") {
    anunciar("Conexão perdida. Reconectando…");
  } else if (estadoAtual && situacao === "conectado" && anterior === "reconectando") {
    anunciar("Conexão restabelecida.");
  }
  redesenhar();
}

function entrarNaPartida(partidaId) {
  conexao = conectarPartida(partidaId, {
    aoReceberEstado: receberEstado,
    aoReceberErro: (erro) => mostrarErro(erro.mensagem),
    aoMudarConexao: mudarConexao,
  });
}

// =====================================================================================
// FERRAMENTA DE DESENVOLVIMENTO — REMOVER junto com os estados falsos (mock/estados.js).
// Sem ?partida= na URL, um seletor discreto no canto da mesa alterna entre os estados falsos.
// O mock escolhido fica no hash da URL (ex.: mesa.html#meio2x2) para sobreviver ao F5.
// =====================================================================================
function montarSeletorMock() {
  const nomes = Object.keys(mocks);
  const inicial = nomes.includes(location.hash.slice(1)) ? location.hash.slice(1) : nomes[0];

  const seletor = el("select", "dev-seletor-mock");
  seletor.title = "Mock (ferramenta de desenvolvimento)";
  for (const nome of nomes) {
    const opcao = el("option", "", nome);
    opcao.value = nome;
    seletor.append(opcao);
  }
  seletor.value = inicial;
  seletor.addEventListener("change", () => {
    location.hash = seletor.value;
    ui.coberta = false;
    renderizarMesa(mocks[seletor.value]);
  });
  document.body.append(seletor);

  renderizarMesa(mocks[inicial]);
}

// ---------- Início ----------

function iniciar() {
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && ui.confirmandoSaida) cancelarSaida();
  });
  // Voltando pelo histórico, o navegador pode devolver a página congelada, com a conexão
  // fechada. Nesse caso, recarrega para conectar de novo.
  window.addEventListener("pageshow", (evento) => {
    if (evento.persisted) location.reload();
  });

  const partidaId = new URLSearchParams(location.search).get("partida");
  if (partidaId) entrarNaPartida(partidaId);
  else montarSeletorMock();
}

// A mesa exige login: sem sessão, exigirLogin() manda para a tela de login e a mesa não é montada.
if (exigirLogin()) iniciar();
