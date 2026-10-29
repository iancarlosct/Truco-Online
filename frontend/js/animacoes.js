// Animações da mesa.
// A mesa continua sendo redesenhada inteira por renderizarMesa(estado) a cada estado recebido.
// Este módulo não desenha nada nem conhece as regras do jogo: compara o estado anterior com o
// novo para descobrir o que mudou (carta jogada, mão nova, pedido de truco, rodada decidida,
// placar, fim da partida) e anima os elementos que a mesa acabou de desenhar, partindo de onde as coisas estavam
// na tela antiga.
//
// Uso, a cada estado recebido do servidor:
//   const animar = prepararAnimacoes(anterior, novo, raiz); // antes de redesenhar: mede a tela antiga
//   renderizarMesa(novo);
//   animar();                                                // depois de redesenhar: anima a nova
//
// - Só transform e opacity, pela Web Animations API (element.animate), sem bibliotecas.
// - Nada espera uma animação terminar. Se outro estado chegar no meio, a mesa é redesenhada na
//   hora e as animações somem junto com os elementos antigos: a tela vai direto para o novo.
//   Só o aviso de truco e os confetes ficam na camada #efeitos, fora da mesa, para não sumirem
//   com um estado que só traz uma mensagem do chat; um pedido novo substitui o anterior.
// - Sem estado anterior (primeiro estado de uma conexão: ao abrir a mesa, depois de um F5 ou
//   de uma queda), nada é animado.
// - Com prefers-reduced-motion ligado no sistema, nada se move: só fades curtíssimos.

// Durações. Todas ficam abaixo do atraso mínimo dos bots (1 s) antes de cada ação: a
// distribuição inteira (12 cartas no 2x2) leva 300 + 11 × 60 = 960 ms.
const DURACAO_MOVIMENTO_MS = 300; // carta indo para a mesa, cartas da mão se ajeitando
const INTERVALO_DISTRIBUICAO_MS = 60; // entre uma carta e a seguinte, na distribuição
const DURACAO_AVISO_TRUCO_MS = 1000; // o pedido em destaque, do surgimento até sumir
const DURACAO_DESTAQUE_MS = 300; // carta vencedora subindo, marcador da rodada pulsando
const DURACAO_PLACAR_MS = 450; // contagem dos pontos
const DURACAO_FIM_MS = 400; // entrada da tela de fim de partida (na derrota, 1,5 vez isso)
const DURACAO_CONFETES_MS = [1400, 2200]; // queda de cada confete, sorteada no intervalo
const DURACAO_FADE_REDUZIDO_MS = 120; // com prefers-reduced-motion, no lugar dos movimentos

const QTD_CONFETES = 70;
const CORES_CONFETES = ["var(--dourado)", "var(--creme)", "var(--time-a)", "var(--time-b)", "var(--verde-acao)"];

// Os mesmos nomes do aviso da barra de ações (NOME_PEDIDO, em mesa.js).
const TEXTO_PEDIDO = { 3: "Truco!", 6: "Seis!", 9: "Nove!", 12: "Doze!" };

// Saída rápida e chegada suave.
const CURVA_MOVIMENTO = "cubic-bezier(0.2, 0.7, 0.3, 1)";

const movimentoReduzido = matchMedia("(prefers-reduced-motion: reduce)");
const camadaEfeitos = document.getElementById("efeitos");

// ---------- O que mudou entre dois estados ----------

function jogadorDe(estado, assento) {
  return estado.jogadores.find((j) => j.assento === assento);
}

// Compara os dois estados. Só a última rodada da lista fica no centro da mesa, então só as
// cartas dela contam como jogadas novas.
function compararEstados(anterior, novo) {
  const antes = anterior.mao_atual;
  const agora = novo.mao_atual;
  const mesmaMao = antes.numero === agora.numero;
  const indice = agora.rodadas.length - 1;
  const rodada = agora.rodadas[indice];
  const rodadaAntes = mesmaMao ? antes.rodadas[indice] : undefined;
  // Pedido de truco que acabou de aparecer, ou que subiu de valor (alguém aumentou).
  const pedido = agora.truco_pendente;
  const pedidoAntes = mesmaMao ? antes.truco_pendente : null;
  return {
    maoNova: !mesmaMao && novo.status !== "encerrada",
    jogadas: mesmaMao ? (rodada?.jogadas ?? []).slice(rodadaAntes?.jogadas?.length ?? 0) : [],
    mesmaMao,
    rodadaDecidida: mesmaMao && rodada?.vencedor_time && !rodadaAntes?.vencedor_time ? indice : null,
    pedido: pedido && (!pedidoAntes || pedido.valor_proposto > pedidoAntes.valor_proposto) ? pedido : null,
    // [time, pontos antes, pontos agora] de cada time que pontuou.
    placar: ["A", "B"]
      .filter((time) => anterior.placar[time] !== novo.placar[time])
      .map((time) => [time, anterior.placar[time], novo.placar[time]]),
    // A partida acabou agora (e não já encerrada, como chega a quem reconecta depois do fim).
    fim: anterior.status !== "encerrada" && novo.status === "encerrada",
    venceu: novo.vencedor_time === jogadorDe(novo, novo.meu_assento)?.time,
  };
}

// Cartas que saíram da mão aberta de um jogador (a própria, ou a do parceiro na mão de onze).
// É por elas que se acha a carta jogada coberta, que chega sem o código.
function cartasQueSairam(anterior, novo, assento) {
  const depois = jogadorDe(novo, assento)?.mao ?? [];
  return (jogadorDe(anterior, assento)?.mao ?? []).filter((carta) => !depois.includes(carta));
}

// ---------- Medidas ----------

function centroDe(retangulo) {
  return { x: retangulo.left + retangulo.width / 2, y: retangulo.top + retangulo.height / 2 };
}

// Converte um deslocamento na tela para o sistema de coordenadas do elemento, desfazendo o giro
// dos ancestrais (a carta jogada fica dentro de uma .jogada girada alguns graus).
function deslocamentoLocal(elemento, dx, dy) {
  let matriz = new DOMMatrix();
  for (let pai = elemento.parentElement; pai; pai = pai.parentElement) {
    const transformacao = getComputedStyle(pai).transform;
    if (transformacao && transformacao !== "none") matriz = new DOMMatrix(transformacao).multiply(matriz);
  }
  // Só o giro e a escala importam para um deslocamento: tira a translação.
  matriz.e = 0;
  matriz.f = 0;
  const ponto = matriz.inverse().transformPoint(new DOMPoint(dx, dy));
  return [ponto.x, ponto.y];
}

// Posição (centro) e largura de uma carta na tela antiga. A largura é a de layout, sem o giro
// das cartas deitadas nas laterais.
function medirCarta(carta) {
  return { ...centroDe(carta.getBoundingClientRect()), largura: carta.offsetWidth };
}

// De onde sai, na tela antiga, a carta de uma jogada nova: na mão aberta (a própria, ou a do
// parceiro na mão de onze), a carta que saiu dela; nas outras, o último verso.
function medirOrigem(raiz, jogada, saiu) {
  const jogador = raiz.querySelector(`.jogador[data-assento="${jogada.assento}"]`);
  if (!jogador) return null;
  const codigo = saiu.includes(jogada.carta) ? jogada.carta : saiu[0];
  const carta =
    (codigo && jogador.querySelector(`.carta[data-carta="${codigo}"]`)) ||
    jogador.querySelector(".mao-oculta .espaco:last-child .carta");
  return carta ? medirCarta(carta) : null;
}

// Posição de cada carta da própria mão na tela antiga, pelo código.
function medirMinhaMao(raiz, meuAssento) {
  const posicoes = new Map();
  for (const carta of raiz.querySelectorAll(`.jogador[data-assento="${meuAssento}"] .mao .carta`)) {
    posicoes.set(carta.dataset.carta, centroDe(carta.getBoundingClientRect()));
  }
  return posicoes;
}

// ---------- Animações ----------

function aparecer(elemento, atraso = 0) {
  elemento.animate([{ opacity: 0 }, { opacity: 1 }], {
    duration: DURACAO_FADE_REDUZIDO_MS,
    delay: atraso,
    fill: "backwards",
  });
}

// Carta jogada: desenhada já no centro, ela começa sobre a carta de origem (técnica FLIP) e
// desliza até o lugar dela. A coberta faz o mesmo trajeto mostrando o verso.
function voarParaMesa(carta, origem) {
  const destino = centroDe(carta.getBoundingClientRect());
  const [dx, dy] = deslocamentoLocal(carta, origem.x - destino.x, origem.y - destino.y);
  const escala = origem.largura / carta.offsetWidth;
  // Durante o trajeto a carta passa por cima das mãos e das plaquinhas.
  const jogada = carta.closest(".jogada");
  jogada.classList.add("voando");
  const animacao = carta.animate(
    [{ transform: `translate(${dx}px, ${dy}px) scale(${escala})` }, { transform: "none" }],
    { duration: DURACAO_MOVIMENTO_MS, easing: CURVA_MOVIMENTO },
  );
  animacao.onfinish = () => jogada.classList.remove("voando");
}

// As cartas que ficaram na própria mão se ajeitam no espaço da que saiu, em vez de pular.
function ajeitarMinhaMao(raiz, meuAssento, posicoesAntigas) {
  for (const botao of raiz.querySelectorAll(`.jogador[data-assento="${meuAssento}"] .carta-mao`)) {
    const antiga = posicoesAntigas.get(botao.querySelector(".carta").dataset.carta);
    if (!antiga) continue;
    const atual = centroDe(botao.getBoundingClientRect());
    const [dx, dy] = deslocamentoLocal(botao, antiga.x - atual.x, antiga.y - atual.y);
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
    botao.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], {
      duration: DURACAO_MOVIMENTO_MS,
      easing: CURVA_MOVIMENTO,
    });
  }
}

// Distribuição da mão nova: as cartas saem do centro da mesa e chegam a cada jogador, uma para
// cada um por vez, começando por quem tem a vez e seguindo a numeração dos assentos (a ordem é
// só visual).
function distribuir(raiz, estado, reduzir) {
  const n = estado.jogadores.length;
  const primeiro = estado.mao_atual.vez_assento ?? estado.meu_assento;
  const maos = [];
  for (let i = 0; i < n; i++) {
    const jogador = raiz.querySelector(`.jogador[data-assento="${(primeiro + i) % n}"]`);
    maos.push([...(jogador?.querySelectorAll(".carta-mao, .mao-oculta .espaco, .mao-parceiro .carta") ?? [])]);
  }
  const cartas = [];
  const voltas = Math.max(...maos.map((mao) => mao.length));
  for (let volta = 0; volta < voltas; volta++) {
    for (const mao of maos) if (mao[volta]) cartas.push(mao[volta]);
  }

  if (reduzir) {
    for (const carta of cartas) aparecer(carta);
    return;
  }

  const centroMesa = raiz.querySelector(".centro");
  if (!centroMesa) return;
  const origem = centroDe(centroMesa.getBoundingClientRect());
  // Do centro, as cartas saem do tamanho das cartas da mesa (a vira é um pouco menor).
  const larguraMesa = raiz.querySelector(".vira .carta")?.offsetWidth;
  cartas.forEach((elemento, ordem) => {
    const destino = centroDe(elemento.getBoundingClientRect());
    const [dx, dy] = deslocamentoLocal(elemento, origem.x - destino.x, origem.y - destino.y);
    const largura = (elemento.matches(".carta") ? elemento : elemento.querySelector(".carta")).offsetWidth;
    const escala = larguraMesa && largura ? larguraMesa / largura : 1;
    elemento.animate(
      [
        { transform: `translate(${dx}px, ${dy}px) scale(${escala})`, opacity: 0 },
        { opacity: 1, offset: 0.3 },
        { transform: "none", opacity: 1 },
      ],
      {
        duration: DURACAO_MOVIMENTO_MS,
        delay: ordem * INTERVALO_DISTRIBUICAO_MS,
        easing: CURVA_MOVIMENTO,
        // Até a vez dela, a carta espera no centro, invisível.
        fill: "backwards",
      },
    );
  });
}

// Rodada decidida: a carta vencedora (já desenhada em destaque pela mesa) sobe e o contorno
// aparece, depois que a última carta chega; o marcador da rodada pulsa. No empate, as cartas
// ficam como estão e só o marcador, cinza, pulsa.
function destacarRodada(raiz, indice, atraso) {
  const opcoes = { duration: DURACAO_DESTAQUE_MS, delay: atraso, easing: CURVA_MOVIMENTO, fill: "backwards" };
  for (const jogada of raiz.querySelectorAll(".jogada.vencedora")) {
    jogada.animate([{ translate: "0 0" }, { translate: getComputedStyle(jogada).translate }], opcoes);
    jogada.animate([{ opacity: 0 }, { opacity: 1 }], { ...opcoes, pseudoElement: "::after" });
  }
  raiz.querySelectorAll(".marcadores .marcador")[indice]?.animate(
    [{ transform: "scale(1)" }, { transform: "scale(1.45)" }, { transform: "scale(1)" }],
    { duration: DURACAO_DESTAQUE_MS, delay: atraso },
  );
}

// Pontos de um time: o número conta do valor anterior até o novo, crescendo um instante.
// Recebe o bloco do time (no placar da mesa ou no da tela de fim de partida).
function contarPontos(blocos, de, ate, atraso) {
  for (const numero of blocos.map((bloco) => bloco.querySelector(".pontos")).filter(Boolean)) {
    numero.textContent = String(de);
    const inicio = performance.now() + atraso;
    const contar = (instante) => {
      // Mesa redesenhada no meio da contagem: o número novo já está certo.
      if (!numero.isConnected) return;
      const progresso = Math.min(1, Math.max(0, (instante - inicio) / DURACAO_PLACAR_MS));
      numero.textContent = String(Math.round(de + (ate - de) * progresso));
      if (progresso < 1) requestAnimationFrame(contar);
    };
    requestAnimationFrame(contar);
    numero.animate(
      [{ transform: "scale(1)" }, { transform: "scale(1.35)", offset: 0.4 }, { transform: "scale(1)" }],
      { duration: DURACAO_PLACAR_MS, delay: atraso, easing: "ease-out" },
    );
  }
}

// Pedido de truco: o nome aparece grande no centro da mesa, na camada de efeitos, e some. Não
// recebe cliques; o aviso da barra de ações continua lá.
function anunciarPedido(raiz, pedido, reduzir) {
  const centroMesa = raiz.querySelector(".centro");
  if (!camadaEfeitos || !centroMesa) return;
  camadaEfeitos.querySelector(".aviso-pedido")?.remove();
  const { x, y } = centroDe(centroMesa.getBoundingClientRect());
  const aviso = document.createElement("p");
  aviso.className = `aviso-pedido time-${pedido.pedido_por_time.toLowerCase()}`;
  aviso.textContent = TEXTO_PEDIDO[pedido.valor_proposto] ?? "Truco!";
  aviso.style.left = `${x}px`;
  aviso.style.top = `${y}px`;
  camadaEfeitos.append(aviso);

  const centralizar = "translate(-50%, -50%)";
  const quadros = reduzir
    ? [{ opacity: 0 }, { opacity: 1, offset: 0.1 }, { opacity: 1, offset: 0.9 }, { opacity: 0 }]
    : [
        { transform: `${centralizar} scale(0.4)`, opacity: 0 },
        { transform: `${centralizar} scale(1.08)`, opacity: 1, offset: 0.2 },
        { transform: `${centralizar} scale(1)`, opacity: 1, offset: 0.32 },
        { transform: `${centralizar} scale(1)`, opacity: 1, offset: 0.8 },
        { transform: `${centralizar} scale(1.12)`, opacity: 0 },
      ];
  const animacao = aviso.animate(quadros, { duration: DURACAO_AVISO_TRUCO_MS, easing: "ease-out", fill: "forwards" });
  animacao.onfinish = () => aviso.remove();
}

// Confetes da vitória: estouram do alto do cartão do resultado, sobem e caem até o fim da área
// da mesa, girando, sem passar para o chat.
function soltarConfetes(cartao, area, atraso) {
  if (!camadaEfeitos || !area) return;
  camadaEfeitos.querySelector(".confetes")?.remove();
  const limites = area.getBoundingClientRect();
  const origem = cartao.getBoundingClientRect();
  const x = origem.left + origem.width / 2;
  const y = origem.top + 12;
  const alcance = Math.min(x - limites.left, limites.right - x) * 0.9;
  const queda = limites.bottom - y + 30;

  const confetes = document.createElement("div");
  confetes.className = "confetes";
  let restantes = QTD_CONFETES;
  for (let i = 0; i < QTD_CONFETES; i++) {
    const confete = document.createElement("span");
    confete.className = "confete";
    confete.style.left = `${x}px`;
    confete.style.top = `${y}px`;
    confete.style.background = CORES_CONFETES[i % CORES_CONFETES.length];
    confetes.append(confete);

    // Sobe freando até o ponto mais alto e cai acelerando, girando o tempo todo.
    const dx = (Math.random() * 2 - 1) * alcance;
    const subida = 80 + Math.random() * 220;
    const giro = (Math.random() * 2 - 1) * 900;
    const centralizar = "translate(-50%, -50%)";
    const alto = `${centralizar} translate(${dx * 0.4}px, ${-subida}px) rotate(${giro * 0.3}deg)`;
    const chao = `${centralizar} translate(${dx}px, ${queda}px) rotate(${giro}deg)`;
    const [minimo, maximo] = DURACAO_CONFETES_MS;
    const animacao = confete.animate(
      [
        { transform: centralizar, opacity: 0, easing: "cubic-bezier(0.2, 0.7, 0.4, 1)" },
        { opacity: 1, offset: 0.04 },
        { transform: alto, offset: 0.3, easing: "ease-in" },
        { opacity: 1, offset: 0.75 },
        { transform: chao, opacity: 0 },
      ],
      {
        duration: minimo + Math.random() * (maximo - minimo),
        delay: atraso + Math.random() * 150,
        fill: "backwards",
      },
    );
    animacao.onfinish = () => {
      if (--restantes === 0) confetes.remove();
    };
  }
  camadaEfeitos.append(confetes);
}

// Fim de partida: o resultado entra depois que a última carta chega e o destaque da rodada
// aparece. Na vitória, o cartão salta e os confetes estouram; na derrota, ele só desce devagar
// até o lugar.
function mostrarFim(raiz, venceu, atraso, reduzir) {
  const cartao = raiz.querySelector(".fim-partida");
  const fundo = cartao?.closest(".sobreposicao");
  if (!fundo) return;
  if (reduzir) {
    aparecer(fundo, atraso);
    return;
  }
  const duracao = venceu ? DURACAO_FIM_MS : DURACAO_FIM_MS * 1.5;
  fundo.animate([{ opacity: 0 }, { opacity: 1 }], { duration: duracao, delay: atraso, fill: "backwards" });
  const quadros = venceu
    ? [{ transform: "scale(0.8)" }, { transform: "scale(1.04)", offset: 0.6 }, { transform: "scale(1)" }]
    : [{ transform: "translateY(-18px)" }, { transform: "none" }];
  cartao.animate(quadros, { duration: duracao, delay: atraso, easing: "ease-out", fill: "backwards" });
  if (venceu) soltarConfetes(cartao, raiz.querySelector(".area-mesa"), atraso);
}

// ---------- Entrada ----------

// Chamada antes de redesenhar a mesa com o estado novo: descobre o que mudou e mede, na tela
// antiga, de onde as cartas saem. Devolve a função que anima a tela nova, para chamar logo
// depois de redesenhar. Sem estado anterior, devolve uma função que não faz nada.
export function prepararAnimacoes(anterior, novo, raiz) {
  if (!anterior || anterior.partida_id !== novo.partida_id) return () => {};
  const mudou = compararEstados(anterior, novo);
  const meuAssento = novo.meu_assento;

  const origens = mudou.jogadas.map((jogada) =>
    medirOrigem(raiz, jogada, cartasQueSairam(anterior, novo, jogada.assento)),
  );
  const minhaMao = mudou.mesmaMao ? medirMinhaMao(raiz, meuAssento) : new Map();

  return () => {
    const reduzir = movimentoReduzido.matches;

    if (mudou.maoNova) distribuir(raiz, novo, reduzir);

    mudou.jogadas.forEach((jogada, i) => {
      const carta = raiz.querySelector(`.jogada[data-assento="${jogada.assento}"] .carta`);
      if (!carta) return;
      if (reduzir || !origens[i]) aparecer(carta);
      else voarParaMesa(carta, origens[i]);
    });

    if (mudou.pedido) anunciarPedido(raiz, mudou.pedido, reduzir);

    // O que depende da carta que acabou de ser jogada começa quando ela chega ao centro, e o
    // fim de partida, depois do destaque da rodada.
    const chegada = !reduzir && mudou.jogadas.length > 0 ? DURACAO_MOVIMENTO_MS : 0;
    const entradaFim = chegada + (!reduzir && mudou.rodadaDecidida !== null ? DURACAO_DESTAQUE_MS : 0);
    if (mudou.fim) mostrarFim(raiz, mudou.venceu, entradaFim, reduzir);
    // Com o movimento reduzido, o destaque da rodada e os pontos novos aparecem direto.
    if (reduzir) return;

    if (mudou.jogadas.length > 0) ajeitarMinhaMao(raiz, meuAssento, minhaMao);
    if (mudou.rodadaDecidida !== null) destacarRodada(raiz, mudou.rodadaDecidida, chegada);
    for (const [time, de, ate] of mudou.placar) {
      const classe = `time-${time.toLowerCase()}`;
      contarPontos([...raiz.querySelectorAll(`.placar-time.${classe}`)], de, ate, chegada);
      contarPontos([...raiz.querySelectorAll(`.fim-time.${classe}`)], de, ate, entradaFim);
    }
  };
}
