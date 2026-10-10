// Tela da mesa de jogo.
// Toda a tela é desenhada por renderizarMesa(estado), que limpa e redesenha a partir do estado.
// Nenhuma regra do jogo é implementada aqui: a interface só habilita ou desabilita controles
// conforme o estado recebido; quem valida as ações é o servidor.

import { criarCarta, criarVerso, proximaManilha } from "../cartas.js";
import * as mocks from "../mock/estados.js";

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

// Último estado desenhado (usado para redesenhar quando muda algo local, como "Jogar coberta").
let estadoAtual = null;

// Estado local da interface, que não vem do servidor.
const ui = { coberta: false, rascunhoChat: "", focoChat: false };

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

  return {
    eu,
    meuTime,
    timeAdversario: meuTime === "A" ? "B" : "A",
    minhaVez,
    posicaoDe: (assento) => POSICOES[n][(assento - estado.meu_assento + n) % n],
    podeJogar: minhaVez && !truco && !maoAtual.aguardando_decisao_mao_de_onze,
    podePedirTruco:
      minhaVez &&
      !truco &&
      maoAtual.valor < 12 &&
      maoAtual.ultimo_aumento_time !== meuTime &&
      maoAtual.tipo === "normal",
    trucoContraMim: Boolean(truco) && truco.pedido_por_time !== meuTime,
    decidindoMaoDeOnze: maoAtual.aguardando_decisao_mao_de_onze && estado.placar[meuTime] === 11,
    // "Jogar coberta" só fica disponível a partir da segunda rodada da mão.
    podeCobrir: maoAtual.rodadas.length >= 2,
  };
}

// ---------- Envio de ações ----------

// Único ponto de saída das ações do jogador. Por enquanto só registra no console;
// depois enviará a mensagem pelo WebSocket.
export function enviar(mensagem) {
  console.log("[enviar]", mensagem);
}

function jogarCarta(carta) {
  const podeCobrir = estadoAtual.mao_atual.rodadas.length >= 2;
  enviar({ tipo: "jogar_carta", carta, coberta: ui.coberta && podeCobrir });
  ui.coberta = false;
  renderizarMesa(estadoAtual);
}

function alternarCoberta(marcada) {
  ui.coberta = marcada;
  renderizarMesa(estadoAtual);
}

function enviarChat(texto) {
  if (!texto) return;
  enviar({ tipo: "chat", texto });
  ui.rascunhoChat = "";
  ui.focoChat = true;
  renderizarMesa(estadoAtual);
}

// ---------- Componentes ----------

// Mão do próprio jogador: cartas abertas, clicáveis apenas quando podeJogar.
function criarMao(cartas, podeJogar, aoJogar) {
  const mao = el("div", "mao");
  for (const codigo of cartas) {
    const botao = el("button", "carta-mao");
    botao.type = "button";
    botao.disabled = !podeJogar;
    botao.append(criarCarta(codigo));
    botao.addEventListener("click", () => aoJogar(codigo));
    mao.append(botao);
  }
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

// Jogador na mesa: plaquinha (time, nome, selos) + a mão já montada.
function criarJogador(jogador, { posicao, naVez, souEu, mao }) {
  const raiz = el("div", `jogador pos-${posicao} ${classeTime(jogador.time)}`);
  if (naVez) raiz.classList.add("na-vez");

  const plaquinha = el("div", "plaquinha");
  plaquinha.title = `Time ${jogador.time}`;
  plaquinha.append(el("span", "cor-time"), el("span", "nome", jogador.nome));
  if (souEu) plaquinha.append(el("span", "voce", "(você)"));
  if (jogador.bot) plaquinha.append(el("span", "selo-bot", "BOT"));
  plaquinha.append(el("span", "selo-vez", "vez"));

  // Embaixo a mão fica acima da plaquinha; nas outras posições, do lado do centro.
  if (posicao === "baixo") raiz.append(mao, plaquinha);
  else raiz.append(plaquinha, mao);
  return raiz;
}

// Marcadores das 3 rodadas da mão.
function criarRodadas(rodadas) {
  const bloco = el("div", "rodadas");
  const marcadores = el("div", "marcadores");
  for (let i = 0; i < 3; i++) {
    const vencedor = rodadas[i]?.vencedor_time ?? null;
    const marcador = el("span", "marcador");
    if (vencedor === "empate") marcador.classList.add("empate");
    else if (vencedor) marcador.classList.add(classeTime(vencedor));
    else if (rodadas.length > 0 && i === rodadas.length - 1) marcador.classList.add("atual");
    marcadores.append(marcador);
  }
  bloco.append(el("span", "rotulo-mesa", "Rodadas"), marcadores);
  return bloco;
}

// Centro da mesa: cartas da rodada atual, vira com a manilha e marcadores das rodadas.
function criarCentro(maoAtual, posicaoDe) {
  const centro = el("div", "centro");

  const rodadaAtual = maoAtual.rodadas.at(-1);
  const jogadas = el("div", "jogadas");
  for (const jogada of rodadaAtual?.jogadas ?? []) {
    const item = el("div", `jogada pos-${posicaoDe(jogada.assento)}`);
    item.append(jogada.coberta || !jogada.carta ? criarVerso() : criarCarta(jogada.carta));
    jogadas.append(item);
  }

  const vira = el("div", "vira");
  const manilha = el("span", "manilha", "Manilha: ");
  manilha.append(el("strong", "", proximaManilha(maoAtual.vira)));
  vira.append(el("span", "rotulo-mesa", "Vira"), criarCarta(maoAtual.vira), manilha);

  centro.append(jogadas, vira, criarRodadas(maoAtual.rodadas));
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

// Texto de situação mostrado na barra de ações.
function textoAviso(maoAtual, ctx, jogadores) {
  const truco = maoAtual.truco_pendente;
  if (ctx.trucoContraMim) return `Time adversário pediu ${NOME_PEDIDO[truco.valor_proposto]}!`;
  if (truco) return `Aguardando o adversário responder ao pedido de ${NOME_PEDIDO[truco.valor_proposto]}…`;
  if (ctx.decidindoMaoDeOnze) return "Mão de onze: seu time decide se joga ou corre.";
  if (maoAtual.aguardando_decisao_mao_de_onze) return "Aguardando o adversário decidir a mão de onze…";
  if (ctx.minhaVez) return "Sua vez de jogar.";
  const daVez = jogadores.find((j) => j.assento === maoAtual.vez_assento);
  return daVez ? `Vez de ${daVez.nome}.` : "";
}

// Botão da barra de ações: desabilitado quando não se aplica; ao clicar envia a mensagem.
function criarBotaoAcao(texto, classes, ativo, mensagem) {
  const botao = el("button", `botao ${classes}`, texto);
  botao.type = "button";
  botao.disabled = !ativo;
  botao.addEventListener("click", () => enviar(mensagem));
  return botao;
}

// Barra de ações abaixo da mão: aviso, truco, resposta ao truco, jogar coberta e mão de onze.
function criarBarraAcoes(maoAtual, ctx, jogadores, coberta, aoAlternarCoberta) {
  const barra = el("div", "barra-acoes");

  const aviso = el("p", "aviso", textoAviso(maoAtual, ctx, jogadores));
  if (ctx.trucoContraMim || ctx.decidindoMaoDeOnze) aviso.classList.add("alerta");

  const controles = el("div", "controles");
  const podeAumentar = ctx.trucoContraMim && maoAtual.truco_pendente.valor_proposto < 12;

  const resposta = el("div", "grupo");
  resposta.append(
    criarBotaoAcao("Aceitar", "botao-aceitar", ctx.trucoContraMim, { tipo: "responder_truco", resposta: "aceitar" }),
    criarBotaoAcao("Correr", "botao-correr", ctx.trucoContraMim, { tipo: "responder_truco", resposta: "correr" }),
    criarBotaoAcao("Aumentar", "", podeAumentar, { tipo: "responder_truco", resposta: "aumentar" }),
  );

  const alternador = el("label", "alternador");
  const caixa = el("input");
  caixa.type = "checkbox";
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
      criarBotaoAcao("Jogar a mão", "botao-aceitar", true, { tipo: "decidir_mao_de_onze", jogar: true }),
      criarBotaoAcao("Correr", "botao-correr", true, { tipo: "decidir_mao_de_onze", jogar: false }),
    );
    controles.append(el("span", "separador"), onze);
  }

  barra.append(aviso, controles);
  return barra;
}

// Painel lateral do chat: mensagens (autor + texto), campo de texto e botão enviar.
function criarChat(mensagens, jogadores, rascunho, aoEnviar, aoDigitar) {
  const painel = el("aside", "chat");
  painel.append(el("h2", "chat-titulo", "Chat"));

  const lista = el("ul", "chat-mensagens");
  if (mensagens.length === 0) lista.append(el("li", "chat-vazio", "Nenhuma mensagem ainda."));
  for (const mensagem of mensagens) {
    const item = el("li", "chat-mensagem");
    // O autor ganha a cor do time quando o nome corresponde a um jogador da mesa.
    const autor = jogadores.find((j) => j.nome === mensagem.de);
    item.append(
      el("span", `autor ${autor ? classeTime(autor.time) : ""}`, mensagem.de),
      el("span", "texto", mensagem.texto),
    );
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
  // O envio do formulário cobre tanto o clique no botão quanto a tecla Enter.
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    aoEnviar(campo.value.trim());
  });
  formulario.append(campo, botao);

  painel.append(lista, formulario);
  return painel;
}

// ---------- Renderização ----------

// Limpa a tela e redesenha tudo a partir do estado.
export function renderizarMesa(estado) {
  estadoAtual = estado;
  const ctx = derivar(estado);
  const maoAtual = estado.mao_atual;

  const feltro = el("div", "feltro");
  feltro.append(
    criarPlacar(estado.placar, maoAtual, ctx.meuTime, ctx.timeAdversario),
    criarCentro(maoAtual, ctx.posicaoDe),
  );
  for (const jogador of estado.jogadores) {
    const souEu = jogador.assento === estado.meu_assento;
    feltro.append(
      criarJogador(jogador, {
        posicao: ctx.posicaoDe(jogador.assento),
        naVez: jogador.assento === maoAtual.vez_assento,
        souEu,
        mao: souEu
          ? criarMao(jogador.mao ?? [], ctx.podeJogar, jogarCarta)
          : criarMaoOculta(jogador.qtd_cartas),
      }),
    );
  }

  const mesa = el("div", "mesa");
  mesa.append(feltro);

  const areaMesa = el("section", "area-mesa");
  areaMesa.append(
    mesa,
    criarBarraAcoes(maoAtual, ctx, estado.jogadores, ui.coberta, alternarCoberta),
  );

  const chat = criarChat(estado.chat, estado.jogadores, ui.rascunhoChat, enviarChat, (texto) => {
    ui.rascunhoChat = texto;
  });

  // Como a tela é refeita por inteiro, o foco do campo do chat é devolvido depois de redesenhar.
  const campoChat = chat.querySelector(".chat-campo");
  const devolverFoco = ui.focoChat;
  campoChat.addEventListener("focus", () => { ui.focoChat = true; });
  campoChat.addEventListener("blur", () => { ui.focoChat = false; });

  const tela = el("div", "tela");
  tela.append(areaMesa, chat);
  app.replaceChildren(tela);

  // Rolagem automática do chat até a última mensagem.
  const mensagens = chat.querySelector(".chat-mensagens");
  mensagens.scrollTop = mensagens.scrollHeight;
  ui.focoChat = devolverFoco;
  if (devolverFoco) campoChat.focus();
}

// =====================================================================================
// FERRAMENTA DE DESENVOLVIMENTO — REMOVER quando a tela for ligada ao WebSocket.
// Seletor discreto no canto da mesa para alternar entre os estados falsos (mocks).
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

montarSeletorMock();
