// =====================================================================================
// PROVISÓRIO — SERVIDOR SIMULADO DO SERVIÇO GAME. REMOVER junto com USAR_MOCK_GAME (ws.js).
// Faz o papel do Game dentro do navegador, para testar a mesa de ponta a ponta sem backend.
// NÃO é o motor de regras oficial (services/game/engine): as regras daqui são o mínimo para a
// partida andar e podem diferir das do motor.
//
// - WebSocketSimulado imita o WebSocket do navegador (onopen, onmessage, onclose, send, close
//   e readyState), com as mensagens em texto JSON, como na rede. Assim o ws.js trata o
//   servidor simulado e o real do mesmo jeito.
// - O estado completo de cada partida fica no localStorage, para sobreviver ao F5 (que vale
//   como reconexão). A cada mudança, cada conexão recebe o "estado" na visão do seu jogador.
// - A partida usa os jogadores da sala do mock do Lobby que a iniciou (o partida_id da URL).
//   Se nenhuma sala tiver esse partida_id, é uma partida de exemplo 1x1 contra um bot.
// - O usuário da sessão (auth.js) joga pelo assento dele. Os outros assentos, bots ou jogadores
//   fictícios do mock do Lobby, são jogados aqui: carta aleatória, truco aceito na maior parte
//   das vezes e pedido de vez em quando. No time do usuário, quem responde ao truco e decide a
//   mão de onze é sempre o usuário.
// - Simplificações: depois de uma rodada empatada, quem abriu a rodada empatada abre a próxima;
//   três rodadas empatadas não dão ponto a ninguém; o placar para em 12.
// - Ficou de fora: a mão de ferro. Com os dois times com 11, a mão leva o tipo
//   "mao_de_ferro" (selo na mesa e sem truco), mas é jogada com as cartas à vista.
// - window.mockGame (no fim do arquivo) é uma FERRAMENTA DE DESENVOLVIMENTO para o console.
// =====================================================================================

import { salaDaPartidaMock } from "../api.js";
import { obterToken, obterUsuario } from "../auth.js";

const CHAVE_PARTIDAS_MOCK = "truco.mock.partidas";

// Tempos simulados.
const ATRASO_CONEXAO_MS = 400; // do new WebSocket até a conexão abrir
const ATRASO_REDE_MS = 120; // cada mensagem, nos dois sentidos
const ATRASO_JOGADA_MS = [800, 1500]; // quanto quem é jogado aqui "pensa" (sorteado no intervalo)
const PAUSA_ENTRE_MAOS_MS = 2000; // a mão encerrada fica na mesa antes da próxima

const PONTOS_PARA_VENCER = 12;
const LIMITE_CHAT = 50; // últimas mensagens guardadas
const TAMANHO_CHAT = 200; // caracteres por mensagem

// Força das cartas, da mais fraca para a mais forte. Entre as manilhas vale o naipe.
const VALORES = ["4", "5", "6", "7", "Q", "J", "K", "A", "2", "3"];
const NAIPES = ["O", "E", "C", "P"]; // ouros < espadas < copas < paus

// Próximo valor da mão a cada pedido: truco (3), seis, nove e doze.
const PROXIMO_VALOR = { 1: 3, 3: 6, 6: 9, 9: 12 };

const NOME_TIPO = { mao_de_onze: "mão de onze", mao_de_ferro: "mão de ferro" };

// Comportamento de quem é jogado aqui.
const CHANCE_PEDIR_TRUCO = 0.15;
const CHANCE_ACEITAR = 0.7;
const CHANCE_AUMENTAR = 0.12; // o resto corre
const CHANCE_JOGAR_MAO_DE_ONZE = 0.75;

// Códigos de erro do protocolo, com a mensagem usada por mockGame.enviarErro().
const ERROS = {
  fora_da_vez: "Não é a sua vez.",
  carta_invalida: "Você não tem essa carta.",
  acao_invalida: "Essa ação não vale agora.",
  nao_autorizado: "Você não pode fazer isso.",
};

// Fechamentos que o Game usa para recusar a conexão.
const FECHAMENTOS = { 4401: "token inválido", 4403: "não pertence à partida", 4404: "partida inexistente" };

// Ação recusada: vira a mensagem "erro" para quem enviou.
class ErroJogada extends Error {
  constructor(codigo, mensagem) {
    super(mensagem);
    this.codigo = codigo;
  }
}

// ---------- Guarda das partidas ----------

const partidas = new Map(); // partida_id -> estado completo, como o servidor guarda
const conexoes = new Map(); // socket aberto -> { partidaId, assento }
const temporizadores = new Map(); // partida_id -> próxima ação automática agendada
let quedaAte = 0; // até quando as conexões falham (mockGame.derrubarConexao)

function lerPartidasMock() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_PARTIDAS_MOCK)) ?? {};
  } catch {
    return {};
  }
}

function salvarPartidaMock(partida) {
  const guardadas = lerPartidasMock();
  guardadas[partida.partida_id] = partida;
  localStorage.setItem(CHAVE_PARTIDAS_MOCK, JSON.stringify(guardadas));
}

function buscarPartida(partidaId) {
  if (!partidas.has(partidaId)) {
    const guardada = lerPartidasMock()[partidaId];
    if (guardada) partidas.set(partidaId, guardada);
  }
  return partidas.get(partidaId) ?? null;
}

// ---------- Utilitários ----------

function sortear(lista) {
  return lista[Math.floor(Math.random() * lista.length)];
}

function sortearEntre([minimo, maximo]) {
  return minimo + Math.random() * (maximo - minimo);
}

function embaralhar(lista) {
  for (let i = lista.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [lista[i], lista[j]] = [lista[j], lista[i]];
  }
  return lista;
}

function outroTime(time) {
  return time === "A" ? "B" : "A";
}

function jogadorNoAssento(partida, assento) {
  return partida.jogadores.find((j) => j.assento === assento);
}

// Manilha: o valor seguinte ao da vira (depois do 3 volta para o 4).
function manilhaDaMao(mao) {
  return VALORES[(VALORES.indexOf(mao.vira.slice(0, -1)) + 1) % VALORES.length];
}

function forcaDaCarta(carta, manilha) {
  const valor = carta.slice(0, -1);
  if (valor === manilha) return 100 + NAIPES.indexOf(carta.slice(-1));
  return VALORES.indexOf(valor);
}

// Rodada que a próxima carta vai jogar: a rodada nova só entra na lista com a primeira carta
// dela, para a rodada encerrada continuar visível na mesa.
function numeroDaRodada(mao) {
  const ultima = mao.rodadas.at(-1);
  if (!ultima) return 1;
  return ultima.vencedor_time ? mao.rodadas.length + 1 : mao.rodadas.length;
}

// ---------- Partida ----------

// Monta a partida com os assentos da sala que a iniciou. Sem sala, é a partida de exemplo
// 1x1, com o usuário contra um bot. Devolve null se o usuário não está na sala.
function criarPartida(partidaId, usuario) {
  const sala = salaDaPartidaMock(partidaId);
  const assentos = sala?.assentos ?? [
    { assento: 0, usuario_id: usuario.id, nome: usuario.nome, bot: false },
    { assento: 1, usuario_id: null, nome: "Bot 1", bot: true },
  ];
  if (!assentos.some((a) => a.usuario_id === usuario.id)) return null;

  const partida = {
    partida_id: partidaId,
    sala_id: sala?.id ?? null,
    formato: assentos.length === 4 ? "2x2" : "1x1",
    status: "em_andamento",
    vencedor_time: null,
    jogadores: assentos.map((a) => ({
      assento: a.assento,
      usuario_id: a.usuario_id,
      nome: a.nome,
      time: a.assento % 2 === 0 ? "A" : "B",
      bot: a.bot,
      mao: [],
      // Só do servidor: assento jogado aqui (todos, menos o do usuário da sessão).
      automatico: a.usuario_id !== usuario.id,
    })),
    placar: { A: 0, B: 0 },
    mao_atual: null,
    chat: [],
    // Só do servidor: quando distribuir a próxima mão (pausa depois do fim de uma mão).
    proxima_mao_em: null,
  };
  iniciarMao(partida);
  return partida;
}

// Distribui uma mão nova: 3 cartas para cada um e a vira. O pé passa para o assento seguinte,
// e quem joga primeiro é o assento depois do pé (na primeira mão, o assento 0).
function iniciarMao(partida) {
  const n = partida.jogadores.length;
  const anterior = partida.mao_atual;
  const pe = anterior ? (anterior.pe + 1) % n : n - 1;
  const baralho = embaralhar(VALORES.flatMap((valor) => NAIPES.map((naipe) => valor + naipe)));
  for (const jogador of partida.jogadores) jogador.mao = baralho.splice(0, 3);

  const { A, B } = partida.placar;
  let tipo = "normal";
  if (A === 11 && B === 11) tipo = "mao_de_ferro";
  else if (A === 11 || B === 11) tipo = "mao_de_onze";

  partida.mao_atual = {
    numero: (anterior?.numero ?? 0) + 1,
    pe,
    vira: baralho.pop(),
    valor: 1,
    tipo,
    truco_pendente: null,
    ultimo_aumento_time: null,
    aguardando_decisao_mao_de_onze: tipo === "mao_de_onze",
    rodadas: [],
    vez_assento: (pe + 1) % n,
  };
  partida.proxima_mao_em = null;
}

// Fim da mão: o time vencedor (null se ninguém pontua) ganha os pontos. Aos 12 a partida
// termina; senão a mão encerrada fica na mesa por um instante antes da próxima.
function encerrarMao(partida, time, pontos) {
  const mao = partida.mao_atual;
  mao.vez_assento = null;
  mao.truco_pendente = null;
  mao.aguardando_decisao_mao_de_onze = false;
  if (time) partida.placar[time] = Math.min(PONTOS_PARA_VENCER, partida.placar[time] + pontos);
  if (time && partida.placar[time] >= PONTOS_PARA_VENCER) encerrarPartida(partida, time);
  else partida.proxima_mao_em = Date.now() + PAUSA_ENTRE_MAOS_MS;
}

function encerrarPartida(partida, time) {
  const mao = partida.mao_atual;
  mao.vez_assento = null;
  mao.truco_pendente = null;
  mao.aguardando_decisao_mao_de_onze = false;
  partida.status = "encerrada";
  partida.vencedor_time = time;
  partida.proxima_mao_em = null;
}

// Melhor carta de cada time; carta coberta não vale nada. Cartas de mesma força (fora as
// manilhas, que nunca empatam) empatam a rodada. Devolve o vencedor ("A", "B" ou "empate") e
// quem abre a próxima rodada: quem jogou a carta vencedora ou, no empate, quem abriu esta.
function resultadoDaRodada(partida, rodada) {
  const manilha = manilhaDaMao(partida.mao_atual);
  const melhor = {};
  for (const jogada of rodada.jogadas) {
    const { time } = jogadorNoAssento(partida, jogada.assento);
    const forca = jogada.coberta ? -1 : forcaDaCarta(jogada.carta, manilha);
    if (!melhor[time] || forca > melhor[time].forca) melhor[time] = { forca, assento: jogada.assento };
  }
  if (melhor.A.forca === melhor.B.forca) return { vencedor: "empate", assento: rodada.jogadas[0].assento };
  const vencedor = melhor.A.forca > melhor.B.forca ? "A" : "B";
  return { vencedor, assento: melhor[vencedor].assento };
}

// Vencedor da mão pelos resultados das rodadas até agora: "A", "B", "empate" (as três
// empatadas) ou null (a mão continua). Melhor de 3; com um empate no meio, vale o time que
// ganhou a primeira rodada que não empatou.
function resultadoDaMao(resultados) {
  for (const time of ["A", "B"]) {
    if (resultados.filter((r) => r === time).length >= 2) return time;
  }
  const primeiroVencedor = resultados.find((r) => r !== "empate");
  if (resultados.includes("empate") && primeiroVencedor) return primeiroVencedor;
  if (resultados.length === 3) return "empate";
  return null;
}

// ---------- Ações (as mesmas para o jogador e para quem é jogado aqui) ----------
// Cada ação confere se vale e muda o estado, ou lança ErroJogada sem mudar nada.

function exigirMaoEmJogo(partida) {
  if (partida.status === "encerrada") throw new ErroJogada("acao_invalida", "A partida já terminou.");
  if (partida.proxima_mao_em) throw new ErroJogada("acao_invalida", "A mão terminou. Aguarde a próxima.");
}

function jogarCarta(partida, assento, carta, coberta) {
  exigirMaoEmJogo(partida);
  const mao = partida.mao_atual;
  if (mao.vez_assento !== assento) throw new ErroJogada("fora_da_vez", "Não é a sua vez.");
  if (mao.aguardando_decisao_mao_de_onze) {
    throw new ErroJogada("acao_invalida", "Aguarde a decisão da mão de onze.");
  }
  if (mao.truco_pendente) throw new ErroJogada("acao_invalida", "O pedido de truco ainda não foi respondido.");
  const jogador = jogadorNoAssento(partida, assento);
  if (typeof carta !== "string" || !jogador.mao.includes(carta)) {
    throw new ErroJogada("carta_invalida", "Você não tem essa carta.");
  }
  if (coberta && numeroDaRodada(mao) === 1) {
    throw new ErroJogada("carta_invalida", "Na primeira rodada não dá para jogar coberta.");
  }

  jogador.mao.splice(jogador.mao.indexOf(carta), 1);
  let rodada = mao.rodadas.at(-1);
  if (!rodada || rodada.vencedor_time) {
    rodada = { jogadas: [], vencedor_time: null };
    mao.rodadas.push(rodada);
  }
  rodada.jogadas.push({ assento, carta, coberta });
  if (rodada.jogadas.length < partida.jogadores.length) {
    mao.vez_assento = (assento + 1) % partida.jogadores.length;
    return;
  }

  // Rodada completa.
  const { vencedor, assento: abreAProxima } = resultadoDaRodada(partida, rodada);
  rodada.vencedor_time = vencedor;
  const vencedorDaMao = resultadoDaMao(mao.rodadas.map((r) => r.vencedor_time));
  if (vencedorDaMao) encerrarMao(partida, vencedorDaMao === "empate" ? null : vencedorDaMao, mao.valor);
  else mao.vez_assento = abreAProxima;
}

function pedirTruco(partida, assento) {
  exigirMaoEmJogo(partida);
  const mao = partida.mao_atual;
  const { time } = jogadorNoAssento(partida, assento);
  if (mao.vez_assento !== assento) throw new ErroJogada("fora_da_vez", "Só dá para pedir truco na sua vez.");
  if (mao.tipo !== "normal") throw new ErroJogada("acao_invalida", `Não se pede truco na ${NOME_TIPO[mao.tipo]}.`);
  if (mao.truco_pendente) throw new ErroJogada("acao_invalida", "Já há um pedido de truco esperando resposta.");
  if (mao.valor >= 12) throw new ErroJogada("acao_invalida", "A mão já vale 12.");
  if (mao.ultimo_aumento_time === time) {
    throw new ErroJogada("acao_invalida", "Seu time fez o último aumento: agora só o adversário pode pedir.");
  }
  mao.truco_pendente = { pedido_por_time: time, valor_proposto: PROXIMO_VALOR[mao.valor] };
}

// No 2x2, qualquer jogador do time desafiado responde, e vale a primeira resposta: a segunda
// já não encontra pedido pendente.
function responderTruco(partida, assento, resposta) {
  exigirMaoEmJogo(partida);
  const mao = partida.mao_atual;
  const pedido = mao.truco_pendente;
  const { time } = jogadorNoAssento(partida, assento);
  if (!pedido) throw new ErroJogada("acao_invalida", "Não há pedido de truco para responder.");
  if (pedido.pedido_por_time === time) {
    throw new ErroJogada("nao_autorizado", "Quem responde ao truco é o time adversário.");
  }

  if (resposta === "aceitar") {
    mao.valor = pedido.valor_proposto;
    mao.ultimo_aumento_time = pedido.pedido_por_time;
    mao.truco_pendente = null;
  } else if (resposta === "correr") {
    // Quem pediu ganha o que a mão vale antes do pedido.
    encerrarMao(partida, pedido.pedido_por_time, mao.valor);
  } else if (resposta === "aumentar") {
    if (pedido.valor_proposto >= 12) throw new ErroJogada("acao_invalida", "A aposta já está em 12.");
    // Aumentar aceita o pedido anterior e faz um novo, um nível acima.
    mao.valor = pedido.valor_proposto;
    mao.ultimo_aumento_time = pedido.pedido_por_time;
    mao.truco_pendente = { pedido_por_time: time, valor_proposto: PROXIMO_VALOR[pedido.valor_proposto] };
  } else {
    throw new ErroJogada("acao_invalida", "Resposta inválida.");
  }
}

// Mão de onze: o time com 11 joga valendo 3 ou corre, e o adversário ganha 1 ponto. No 2x2
// vale a primeira decisão, como no truco.
function decidirMaoDeOnze(partida, assento, jogar) {
  exigirMaoEmJogo(partida);
  const mao = partida.mao_atual;
  const { time } = jogadorNoAssento(partida, assento);
  if (!mao.aguardando_decisao_mao_de_onze) {
    throw new ErroJogada("acao_invalida", "Não há decisão de mão de onze pendente.");
  }
  if (partida.placar[time] !== 11) {
    throw new ErroJogada("nao_autorizado", "Quem decide a mão de onze é o time com 11 pontos.");
  }
  if (typeof jogar !== "boolean") throw new ErroJogada("acao_invalida", "Decisão inválida.");
  mao.aguardando_decisao_mao_de_onze = false;
  if (jogar) mao.valor = 3;
  else encerrarMao(partida, outroTime(time), mao.valor);
}

// O chat vale a qualquer momento, inclusive entre as mãos e depois do fim.
function escreverNoChat(partida, assento, texto) {
  const limpo = typeof texto === "string" ? texto.trim().slice(0, TAMANHO_CHAT) : "";
  if (!limpo) throw new ErroJogada("acao_invalida", "A mensagem está vazia.");
  partida.chat.push({ de: jogadorNoAssento(partida, assento).nome, texto: limpo });
  if (partida.chat.length > LIMITE_CHAT) partida.chat.splice(0, partida.chat.length - LIMITE_CHAT);
}

// Mensagens que a mesa envia: tipo -> ação.
const ACOES = {
  jogar_carta: (partida, assento, m) => jogarCarta(partida, assento, m.carta, m.coberta === true),
  pedir_truco: (partida, assento) => pedirTruco(partida, assento),
  responder_truco: (partida, assento, m) => responderTruco(partida, assento, m.resposta),
  decidir_mao_de_onze: (partida, assento, m) => decidirMaoDeOnze(partida, assento, m.jogar),
  chat: (partida, assento, m) => escreverNoChat(partida, assento, m.texto),
};

// ---------- Quem é jogado aqui ----------

// Alguém do time para responder ou decidir por ele, se o time inteiro é jogado aqui. No time
// do usuário quem decide é ele: devolve null.
function automaticoDoTime(partida, time) {
  const doTime = partida.jogadores.filter((j) => j.time === time);
  return doTime.every((j) => j.automatico) ? doTime[0] : null;
}

function sortearResposta(pedido) {
  const sorte = Math.random();
  if (sorte < CHANCE_ACEITAR) return "aceitar";
  if (sorte < CHANCE_ACEITAR + CHANCE_AUMENTAR && pedido.valor_proposto < 12) return "aumentar";
  return "correr";
}

// Faz a ação e diz se ela valeu.
function tentar(acao) {
  try {
    acao();
    return true;
  } catch (erro) {
    if (erro instanceof ErroJogada) return false;
    throw erro;
  }
}

// O que acontece sozinho a seguir, e daqui a quanto tempo: a próxima mão depois da pausa, ou a
// vez de alguém jogado aqui. Devolve null quando a partida espera o usuário (ou acabou).
function proximoPassoAutomatico(partida) {
  if (partida.status === "encerrada") return null;
  if (partida.proxima_mao_em) {
    return { espera: Math.max(0, partida.proxima_mao_em - Date.now()), executar: () => iniciarMao(partida) };
  }
  const mao = partida.mao_atual;
  const pensar = (executar) => ({ espera: sortearEntre(ATRASO_JOGADA_MS), executar });

  if (mao.aguardando_decisao_mao_de_onze) {
    const quem = automaticoDoTime(partida, partida.placar.A === 11 ? "A" : "B");
    return quem && pensar(() => decidirMaoDeOnze(partida, quem.assento, Math.random() < CHANCE_JOGAR_MAO_DE_ONZE));
  }
  if (mao.truco_pendente) {
    const quem = automaticoDoTime(partida, outroTime(mao.truco_pendente.pedido_por_time));
    return quem && pensar(() => responderTruco(partida, quem.assento, sortearResposta(mao.truco_pendente)));
  }
  const daVez = jogadorNoAssento(partida, mao.vez_assento);
  if (!daVez?.automatico) return null;
  return pensar(() => {
    const pediu = Math.random() < CHANCE_PEDIR_TRUCO && tentar(() => pedirTruco(partida, daVez.assento));
    if (!pediu) jogarCarta(partida, daVez.assento, sortear(daVez.mao), false);
  });
}

// Agenda o próximo passo automático da partida, no lugar do que estava agendado.
function agendar(partida) {
  clearTimeout(temporizadores.get(partida.partida_id));
  const passo = proximoPassoAutomatico(partida);
  if (!passo) return;
  const temporizador = setTimeout(() => {
    try {
      passo.executar();
    } catch (erro) {
      console.error("[mockGame] Erro numa jogada automática:", erro);
    }
    mudou(partida);
  }, passo.espera);
  temporizadores.set(partida.partida_id, temporizador);
}

// Depois de qualquer mudança: guarda, manda o estado a todos e agenda o que vem depois.
function mudou(partida) {
  salvarPartidaMock(partida);
  for (const [socket, conexao] of conexoes) {
    if (conexao.partidaId === partida.partida_id) entregar(socket, visaoDoJogador(partida, conexao.assento));
  }
  agendar(partida);
}

// ---------- Visão de cada jogador ----------

// A mensagem "estado" que o jogador deste assento pode receber: só a própria mão (e, na mão
// de onze, a do parceiro do time com 11), a quantidade de cartas de todos e as cartas cobertas
// sem o valor. Os campos que só o servidor usa ficam de fora.
function visaoDoJogador(partida, assento) {
  const mao = partida.mao_atual;
  const meuTime = jogadorNoAssento(partida, assento).time;
  const veParceiro = mao.tipo === "mao_de_onze" && partida.placar[meuTime] === 11;
  const visao = {
    tipo: "estado",
    partida_id: partida.partida_id,
    formato: partida.formato,
    status: partida.status,
    meu_assento: assento,
    jogadores: partida.jogadores.map((j) => {
      const visto = { assento: j.assento, nome: j.nome, time: j.time, bot: j.bot, qtd_cartas: j.mao.length };
      if (j.assento === assento || (veParceiro && j.time === meuTime)) visto.mao = j.mao;
      return visto;
    }),
    placar: partida.placar,
    mao_atual: {
      numero: mao.numero,
      pe: mao.pe,
      vira: mao.vira,
      valor: mao.valor,
      tipo: mao.tipo,
      truco_pendente: mao.truco_pendente,
      ultimo_aumento_time: mao.ultimo_aumento_time,
      aguardando_decisao_mao_de_onze: mao.aguardando_decisao_mao_de_onze,
      rodadas: mao.rodadas.map((rodada) => ({
        jogadas: rodada.jogadas.map((j) => ({ assento: j.assento, carta: j.coberta ? null : j.carta, coberta: j.coberta })),
        vencedor_time: rodada.vencedor_time,
      })),
      vez_assento: mao.vez_assento,
    },
    chat: partida.chat,
  };
  if (partida.status === "encerrada") visao.vencedor_time = partida.vencedor_time;
  return visao;
}

// ---------- Conexões ----------

// Manda uma mensagem ao navegador, como texto JSON, depois do atraso da rede. O texto é
// montado na hora, então mudanças seguintes no estado não alteram o que já saiu.
function entregar(socket, mensagem) {
  const texto = JSON.stringify(mensagem);
  setTimeout(() => {
    if (socket.readyState === WebSocket.OPEN) socket.onmessage?.({ data: texto });
  }, ATRASO_REDE_MS);
}

function abrirSocket(socket) {
  socket.readyState = WebSocket.OPEN;
  socket.onopen?.({});
}

function fecharSocket(socket, codigo, motivo = "") {
  if (socket.readyState === WebSocket.CLOSED) return;
  const abria = socket.readyState === WebSocket.CONNECTING;
  socket.readyState = WebSocket.CLOSED;
  conexoes.delete(socket);
  setTimeout(() => {
    if (abria) socket.onerror?.({});
    socket.onclose?.({ code: codigo, reason: motivo, wasClean: codigo !== 1006 });
  }, 0);
}

// Recusa como o Game: aceita e fecha com o código, para o navegador receber o motivo.
function recusar(socket, codigo) {
  abrirSocket(socket);
  fecharSocket(socket, codigo, FECHAMENTOS[codigo]);
}

// Pedido de conexão em /ws/partidas/{partida_id}?token=<jwt>.
function conectar(socket) {
  if (socket.readyState !== WebSocket.CONNECTING) return; // fechado antes de abrir
  const endereco = new URL(socket.url);
  const caminho = endereco.pathname.match(/^\/ws\/partidas\/([^/]+)$/);
  // Rota errada ou servidor fora do ar: a conexão falha sem abrir (código 1006).
  if (!caminho || Date.now() < quedaAte) {
    fecharSocket(socket, 1006);
    return;
  }
  const partidaId = decodeURIComponent(caminho[1]);
  // O token tem que ser o da sessão (no Game real, um JWT válido).
  const usuario = obterUsuario();
  if (!usuario?.id || endereco.searchParams.get("token") !== obterToken()) {
    recusar(socket, 4401);
    return;
  }
  let partida = buscarPartida(partidaId);
  if (!partida) {
    partida = criarPartida(partidaId, usuario);
    if (partida) {
      partidas.set(partidaId, partida);
      salvarPartidaMock(partida);
    }
  }
  const jogador = partida?.jogadores.find((j) => j.usuario_id === usuario.id);
  if (!jogador) {
    recusar(socket, 4403);
    return;
  }
  abrirSocket(socket);
  conexoes.set(socket, { partidaId, assento: jogador.assento });
  // Ao conectar, o estado atual: é assim que a tela se desenha e que um F5 reconecta.
  entregar(socket, visaoDoJogador(partida, jogador.assento));
  agendar(partida);
}

// Mensagem que chegou do navegador.
function receberDoCliente(socket, texto) {
  const conexao = conexoes.get(socket);
  if (!conexao) return;
  const partida = buscarPartida(conexao.partidaId);
  let mensagem;
  try {
    mensagem = JSON.parse(texto);
  } catch {
    entregar(socket, { tipo: "erro", codigo: "acao_invalida", mensagem: "A mensagem não é um JSON válido." });
    return;
  }
  const acao = ACOES[mensagem?.tipo];
  if (!acao) {
    entregar(socket, { tipo: "erro", codigo: "acao_invalida", mensagem: "Mensagem desconhecida." });
    return;
  }
  try {
    acao(partida, conexao.assento, mensagem);
  } catch (erro) {
    if (!(erro instanceof ErroJogada)) throw erro;
    // Ação recusada: o estado não muda e só quem enviou fica sabendo.
    entregar(socket, { tipo: "erro", codigo: erro.codigo, mensagem: erro.message });
    return;
  }
  mudou(partida);
}

// Imita o WebSocket do navegador, ligado ao servidor simulado. O ws.js usa no lugar de
// new WebSocket(endereco) quando USAR_MOCK_GAME é true.
export class WebSocketSimulado {
  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    instalarComandos();
    setTimeout(() => conectar(this), ATRASO_CONEXAO_MS);
  }

  send(texto) {
    if (this.readyState !== WebSocket.OPEN) {
      throw new DOMException("A conexão não está aberta.", "InvalidStateError");
    }
    setTimeout(() => receberDoCliente(this, texto), ATRASO_REDE_MS);
  }

  close(codigo = 1000, motivo = "") {
    fecharSocket(this, codigo, motivo);
  }
}

// =====================================================================================
// FERRAMENTA DE DESENVOLVIMENTO — REMOVER junto com o servidor simulado.
// window.mockGame: comandos para o console do navegador (F12) que mexem na partida aberta na
// tela (mesa.html?partida=...). Só existe com USAR_MOCK_GAME, a partir da primeira conexão.
// A lista de comandos aparece com mockGame.ajuda().
// =====================================================================================

// A partida aberta na tela, ou null (com aviso no console).
function partidaDaTela() {
  const partidaId = new URLSearchParams(location.search).get("partida");
  const partida = partidaId && buscarPartida(partidaId);
  if (!partida) console.warn("[mockGame] Nenhuma partida aberta. Abra a mesa com mesa.html?partida=<id>.");
  return partida || null;
}

// Sockets do usuário nesta aba.
function socketsDaTela() {
  return [...conexoes.keys()];
}

function instalarComandos() {
  if (window.mockGame) return;
  window.mockGame = {
    ajuda() {
      console.info(
        [
          "mockGame — FERRAMENTA DE DESENVOLVIMENTO: mexe na partida aberta na tela.",
          "  mockGame.partida()                 mostra o estado completo, com as cartas de todos",
          "  mockGame.placar(11, 5)             muda o placar (A, B) e distribui uma mão nova;",
          "                                     com 11 é mão de onze, com 11 e 11 mão de ferro, com 12 acaba",
          '  mockGame.encerrar("B")             encerra a partida com a vitória do time (padrão: o seu)',
          "  mockGame.derrubarConexao(5)        derruba a conexão; novas tentativas falham por 5 segundos",
          "  mockGame.fecharConexao(4404)       fecha com um código do Game: 4401, 4403 ou 4404",
          '  mockGame.enviarErro("fora_da_vez") manda uma mensagem de erro (mensagem opcional no 2º argumento)',
          "  mockGame.resetar()                 apaga as partidas simuladas e recomeça a da tela",
        ].join("\n"),
      );
    },

    partida() {
      const partida = partidaDaTela();
      if (partida) console.log("[mockGame] Estado completo:", JSON.parse(JSON.stringify(partida)));
    },

    placar(pontosA, pontosB) {
      const partida = partidaDaTela();
      if (!partida) return;
      const valido = (p) => Number.isInteger(p) && p >= 0 && p <= PONTOS_PARA_VENCER;
      if (!valido(pontosA) || !valido(pontosB)) {
        console.warn("[mockGame] Informe os pontos dos times A e B, de 0 a 12, por exemplo: mockGame.placar(11, 5).");
        return;
      }
      partida.placar = { A: pontosA, B: pontosB };
      partida.status = "em_andamento";
      partida.vencedor_time = null;
      const vencedor = ["A", "B"].find((time) => partida.placar[time] >= PONTOS_PARA_VENCER);
      if (vencedor) encerrarPartida(partida, vencedor);
      else iniciarMao(partida);
      mudou(partida);
      console.info(
        vencedor
          ? `[mockGame] Placar ${pontosA} a ${pontosB}: a partida terminou com a vitória do time ${vencedor}.`
          : `[mockGame] Placar ${pontosA} a ${pontosB}; mão ${partida.mao_atual.numero} distribuída (${partida.mao_atual.tipo}).`,
      );
    },

    encerrar(time) {
      const partida = partidaDaTela();
      if (!partida) return;
      const usuario = obterUsuario();
      const vencedor = time ?? partida.jogadores.find((j) => j.usuario_id === usuario?.id)?.time ?? "A";
      if (vencedor !== "A" && vencedor !== "B") {
        console.warn('[mockGame] Informe o time vencedor: "A" ou "B".');
        return;
      }
      partida.placar[vencedor] = PONTOS_PARA_VENCER;
      encerrarPartida(partida, vencedor);
      mudou(partida);
      console.info(`[mockGame] Partida encerrada com a vitória do time ${vencedor}.`);
    },

    derrubarConexao(segundos = 5) {
      quedaAte = Date.now() + segundos * 1000;
      for (const socket of socketsDaTela()) fecharSocket(socket, 1006);
      console.info(`[mockGame] Conexão derrubada. Novas tentativas falham por ${segundos} segundo(s).`);
    },

    fecharConexao(codigo) {
      if (!Object.hasOwn(FECHAMENTOS, codigo)) {
        console.warn("[mockGame] Códigos possíveis: 4401 (token inválido), 4403 (não pertence à partida), 4404 (partida inexistente).");
        return;
      }
      for (const socket of socketsDaTela()) fecharSocket(socket, codigo, FECHAMENTOS[codigo]);
      console.info(`[mockGame] Conexão fechada com o código ${codigo} (${FECHAMENTOS[codigo]}).`);
    },

    enviarErro(codigo = "acao_invalida", mensagem) {
      if (!Object.hasOwn(ERROS, codigo)) {
        console.warn(`[mockGame] Códigos possíveis: ${Object.keys(ERROS).join(", ")}.`);
        return;
      }
      for (const socket of socketsDaTela()) entregar(socket, { tipo: "erro", codigo, mensagem: mensagem ?? ERROS[codigo] });
      console.info(`[mockGame] Erro "${codigo}" enviado.`);
    },

    resetar() {
      for (const temporizador of temporizadores.values()) clearTimeout(temporizador);
      temporizadores.clear();
      partidas.clear();
      localStorage.removeItem(CHAVE_PARTIDAS_MOCK);
      quedaAte = 0;
      // A conexão cai e, ao voltar (o ws.js reconecta sozinho), encontra a partida do começo.
      for (const socket of socketsDaTela()) fecharSocket(socket, 1006);
      console.info("[mockGame] Partidas simuladas apagadas; a da tela recomeça na reconexão.");
    },
  };
  console.info("[mockGame] Game simulado (USAR_MOCK_GAME). Comandos: mockGame.ajuda()");
}
