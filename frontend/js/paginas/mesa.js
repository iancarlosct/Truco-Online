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
  };
}

// ---------- Envio de ações ----------

// Único ponto de saída das ações do jogador. Por enquanto só registra no console;
// depois enviará a mensagem pelo WebSocket.
export function enviar(mensagem) {
  console.log("[enviar]", mensagem);
}

function jogarCarta(carta) {
  enviar({ tipo: "jogar_carta", carta, coberta: false });
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
  areaMesa.append(mesa);

  const tela = el("div", "tela");
  tela.append(areaMesa);
  app.replaceChildren(tela);
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
