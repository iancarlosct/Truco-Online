// Tela do lobby: lista de salas, sala de espera e ranking.
// A página tem duas vistas, trocadas sem recarregar: a lista de salas e a sala de espera. A
// sala aberta fica na URL (lobby.html?sala=s1), para a tela voltar a ela depois de um F5.
// Como na mesa, cada vista é desenhada por inteiro, a partir dos últimos dados recebidos, por
// uma única função (renderizarLista ou renderizarSala); nenhum outro trecho mexe no DOM delas.
// Os dados chegam por atualização periódica (polling) a cada 3 segundos. Quem fala com o
// backend é o api.js, e quem decide se uma ação vale é o servidor.

import {
  ErroApi,
  adicionarBot,
  conferirSessao,
  criarSala,
  entrarNaSala,
  iniciarPartida,
  liberarAssento,
  listarSalas,
  obterRanking,
  obterSala,
  sairDaSala,
} from "../api.js";
import { exigirLogin, obterUsuario, sair } from "../auth.js";
import { criarVerso } from "../cartas.js";

const PAGINA_LOGIN = "index.html";
const PAGINA_MESA = "mesa.html";
const PAGINA_HISTORICO = "historico.html";

// Intervalo da atualização periódica e tempo que um aviso fica na tela.
const INTERVALO_ATUALIZACAO_MS = 3000;
const DURACAO_AVISO_MS = 6000;

// Linhas do ranking que aparecem no painel.
const TAMANHO_RANKING = 10;

// Posição na tela de cada assento relativo ao jogador (sentido anti-horário), como na mesa.
const POSICOES = {
  2: ["baixo", "cima"],
  4: ["baixo", "direita", "cima", "esquerda"],
};

// Lugar da mesa em palavras, para os rótulos lidos pelo leitor de tela.
const NOME_POSICAO = { baixo: "de baixo", cima: "da frente", direita: "da direita", esquerda: "da esquerda" };

// Ordem de leitura das posições (de cima para baixo, da esquerda para a direita). Os assentos
// entram no DOM nessa ordem para o Tab percorrer a mesa na ordem em que ela é vista.
const ORDEM_POSICOES = ["cima", "esquerda", "direita", "baixo"];

// Texto do botão enquanto a requisição dele está em andamento, pelo tipo da ação (o começo
// da chave do botão, antes do ":").
const TEXTO_ESPERA = {
  criar: "Criando…",
  entrar: "Entrando…",
  sentar: "Sentando…",
  bot: "Adicionando…",
  remover: "Removendo…",
  iniciar: "Iniciando…",
  sair: "Saindo…",
  logout: "Saindo…",
};

const tela = document.getElementById("tela");
const areaUsuario = document.getElementById("usuario");
const vista = document.getElementById("vista");
const areaAviso = document.getElementById("aviso");
const painelRanking = document.getElementById("ranking");

// Usuário logado ({ id, nome, email }), lido da sessão ao abrir a página.
let usuario = null;

// Estado da tela: os últimos dados recebidos do servidor e o pouco que é só da interface.
const estado = {
  salaId: null, // sala aberta (vista da sala); null = vista da lista
  salas: null, // última lista de salas recebida; null enquanto carrega
  sala: null, // última versão da sala aberta; null enquanto carrega
  estavaNaSala: false, // se o usuário estava sentado na versão anterior da sala (para notar a remoção)
  acao: null, // chave do botão cuja requisição está em andamento
  aviso: null, // { texto, tipo: "erro" | "info", daAtualizacao }
  ranking: { situacao: "carregando" }, // depois { situacao: "pronto", linhas } ou { situacao: "erro", mensagem }
};

// Controle da atualização periódica.
let temporizador = null; // próxima atualização agendada
let atualizando = false; // há um pedido de atualização em andamento
let atualizarDeNovo = false; // pediram uma atualização enquanto não dava para fazer
let versao = 0; // muda quando os dados da tela mudam por outro caminho: respostas antigas são descartadas
let saindo = false; // a página está indo para outra (login ou mesa)

let temporizadorAviso = null;
let ultimoDesenho = "";

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

// Time de cada assento: os pares são do time A e os ímpares do time B (no 2x2, 0 e 2 contra
// 1 e 3; no 1x1, 0 contra 1).
function timeDoAssento(numero) {
  return numero % 2 === 0 ? "A" : "B";
}

function ocupado(assento) {
  return Boolean(assento.bot || assento.usuario_id);
}

// Texto para mostrar ao usuário: a mensagem do ErroApi ou, num erro inesperado (um bug), um
// aviso genérico, com o detalhe no console.
function textoDoErro(erro) {
  if (erro instanceof ErroApi) return erro.mensagem;
  console.error(erro);
  return "Algo deu errado. Tente de novo.";
}

// Resposta 401: o api.js já apagou a sessão e está levando para a tela de login. Aqui a tela
// só para de atualizar, sem aviso. Devolve true nesse caso.
function sessaoEncerrada(erro) {
  if (!(erro instanceof ErroApi) || erro.status !== 401) return false;
  pararTudo();
  return true;
}

// Troca o conteúdo de uma região da tela. Se o foco estava num botão que continua existindo
// no desenho novo (mesma data-chave), ele volta para esse botão: sem isso, quem usa o teclado
// perderia o lugar a cada atualização.
function trocarConteudo(regiao, ...filhos) {
  const ativo = document.activeElement;
  const chave = regiao.contains(ativo) ? ativo.dataset.chave : undefined;
  regiao.replaceChildren(...filhos);
  if (chave) regiao.querySelector(`[data-chave="${CSS.escape(chave)}"]`)?.focus();
}

// Quando o foco se perde (o botão clicado sumiu ou ficou desabilitado), ele vai para o botão
// indicado, se ainda existir e estiver habilitado, ou para o título da vista.
function garantirFoco(chave) {
  if (document.activeElement && document.activeElement !== document.body) return;
  const botao = chave && vista.querySelector(`[data-chave="${CSS.escape(chave)}"]`);
  if (botao && !botao.disabled) botao.focus();
  else document.getElementById("titulo-vista")?.focus();
}

// Botão da interface. Fica desabilitado enquanto qualquer ação estiver em andamento (ou
// quando "ativo" for falso). A chave identifica o botão entre um desenho e outro.
function criarBotao(chave, texto, classes, aoClicar, ativo = true) {
  const botao = el("button", classes, texto);
  botao.type = "button";
  botao.dataset.chave = chave;
  botao.disabled = !ativo || estado.acao !== null;
  if (aoClicar) botao.addEventListener("click", aoClicar);
  return botao;
}

// Botão que faz uma requisição ao servidor: enquanto ela não termina, mostra o texto de
// espera e todos os botões ficam desabilitados.
function botaoDeAcao(chave, texto, classes, requisicao, ativo = true) {
  const emAndamento = estado.acao === chave;
  const rotulo = emAndamento ? TEXTO_ESPERA[chave.split(":")[0]] : texto;
  const botao = criarBotao(chave, rotulo, classes, () => executar(chave, requisicao), ativo);
  if (emAndamento) botao.setAttribute("aria-busy", "true");
  return botao;
}

// Título da vista. Recebe o foco quando a vista troca, para o teclado e o leitor de tela
// continuarem do começo da vista nova.
function criarTituloVista(texto) {
  const titulo = el("h2", "titulo-vista", texto);
  titulo.id = "titulo-vista";
  titulo.tabIndex = -1;
  titulo.dataset.chave = "titulo-vista";
  return titulo;
}

// ---------- Renderização ----------

// Desenha a área do usuário e a vista atual. Se nada mudou desde o último desenho, não
// redesenha: a cada 3 segundos costumam chegar os mesmos dados, e redesenhar à toa tiraria o
// foco do teclado e o hover do mouse.
function renderizar() {
  const desenho = JSON.stringify([estado.salaId, estado.salas, estado.sala, estado.acao]);
  if (desenho === ultimoDesenho) return;
  ultimoDesenho = desenho;
  renderizarUsuario();
  if (estado.salaId) renderizarSala();
  else renderizarLista();
}

// Endereço do histórico de um jogador (historico.html); sem o id, o do próprio usuário.
function enderecoDoHistorico(usuarioId) {
  return usuarioId ? `${PAGINA_HISTORICO}?jogador=${encodeURIComponent(usuarioId)}` : PAGINA_HISTORICO;
}

// Nome do usuário logado, o link "Meu histórico" e o botão Sair, no cabeçalho.
function renderizarUsuario() {
  const nome = el("span", "usuario-nome", usuario.nome);
  nome.title = usuario.email ? `${usuario.nome} (${usuario.email})` : usuario.nome;
  const historico = el("a", "botao", "Meu histórico");
  historico.href = enderecoDoHistorico();
  historico.dataset.chave = "historico";
  trocarConteudo(areaUsuario, nome, historico, botaoDeAcao("logout", "Sair", "botao", sairDaConta));
}

// ---------- Vista 1: lista de salas ----------

function renderizarLista() {
  const raiz = el("section", "lista");
  raiz.setAttribute("aria-labelledby", "titulo-vista");

  const topo = el("div", "lista-topo");
  const criar = el("div", "criar-sala");
  criar.append(
    botaoDeAcao("criar:1x1", "Criar sala 1x1", "botao-creme", () => criarEAbrir("1x1")),
    botaoDeAcao("criar:2x2", "Criar sala 2x2", "botao-creme", () => criarEAbrir("2x2")),
  );
  topo.append(criarTituloVista("Salas abertas"), criar);
  raiz.append(topo);

  if (estado.salas === null) {
    raiz.append(el("p", "carregando", "Carregando salas…"));
  } else if (estado.salas.length === 0) {
    raiz.append(criarListaVazia());
  } else {
    const grade = el("ul", "salas");
    for (const sala of estado.salas) grade.append(criarCartaoSala(sala));
    raiz.append(grade);
  }
  trocarConteudo(vista, raiz);
}

// Cartão de uma sala: formato, lugares ocupados, dono e o botão para entrar.
function criarCartaoSala(sala) {
  const total = sala.assentos.length;
  const ocupados = sala.assentos.filter(ocupado).length;
  const dono = sala.assentos.find((a) => a.usuario_id === sala.dono_id);
  const estouNaSala = sala.assentos.some((a) => a.usuario_id === usuario.id);

  const cartao = el("li", "cartao-sala");

  const topo = el("div", "cartao-sala-topo");
  topo.append(
    el("span", "formato", sala.formato),
    el("span", "modalidade", sala.formato === "1x1" ? "Um contra um" : "Dupla contra dupla"),
  );

  // Um ponto por assento, na cor do time quando ocupado. O texto ao lado diz o mesmo.
  const lugares = el("p", "lugares");
  const pontos = el("span", "pontos");
  pontos.setAttribute("aria-hidden", "true");
  for (const assento of sala.assentos) {
    const ponto = el("span", `ponto ${classeTime(timeDoAssento(assento.assento))}`);
    if (ocupado(assento)) ponto.classList.add("ocupado");
    pontos.append(ponto);
  }
  lugares.append(pontos, el("span", "", `${ocupados}/${total} jogadores`));

  const minha = sala.dono_id === usuario.id;
  const nomeDono = dono?.nome ?? "outro jogador";

  let botao;
  if (estouNaSala) {
    botao = criarBotao(`voltar:${sala.id}`, "Voltar à sala", "botao-principal", () => abrirSala(sala));
  } else if (ocupados === total) {
    botao = criarBotao(`cheia:${sala.id}`, "Sala cheia", "botao-principal", null, false);
  } else {
    botao = botaoDeAcao(`entrar:${sala.id}`, "Entrar", "botao-principal", () => entrarEAbrir(sala));
  }
  // Para o leitor de tela, o botão diz de que sala é ("Entrar: sala 2x2 de Maria").
  botao.setAttribute("aria-label", `${botao.textContent}: ${minha ? "sua sala" : "sala"} ${sala.formato}${minha ? "" : ` de ${nomeDono}`}`);

  const textoDono = el("p", "dono", minha ? "Sua sala" : `Sala de ${nomeDono}`);
  textoDono.title = textoDono.textContent;
  cartao.append(topo, lugares, textoDono, botao);
  return cartao;
}

// Lista vazia: três cartas viradas sobre o feltro e um convite para criar uma sala.
function criarListaVazia() {
  const vazio = el("div", "lista-vazia");
  const cartas = el("div", "cartas-viradas");
  cartas.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) cartas.append(criarVerso());
  vazio.append(
    cartas,
    el("p", "lista-vazia-titulo", "Nenhuma sala aberta agora"),
    el("p", "lista-vazia-texto", "Crie uma sala 1x1 ou 2x2 e chame a turma. Se faltar gente, quem cria a sala pode completar a mesa com bots."),
  );
  return vazio;
}

// ---------- Vista 2: sala de espera ----------

// Reúne o que a vista da sala precisa saber e que é derivado da sala recebida.
function derivarSala(sala) {
  const n = sala.assentos.length;
  const meuAssento = sala.assentos.find((a) => a.usuario_id === usuario.id) ?? null;
  // Quem ainda não está sentado (abriu o link da sala, por exemplo) vê a mesa a partir do
  // assento 0.
  const referencia = meuAssento ? meuAssento.assento : 0;
  return {
    meuAssento,
    souDono: sala.dono_id === usuario.id,
    duplas: n === 4,
    vagas: sala.assentos.filter((a) => !ocupado(a)).length,
    posicaoDe: (assento) => POSICOES[n][(assento - referencia + n) % n],
  };
}

// Assento ocupado: plaquinha com a cor do time, o nome e os selos; para o dono, o botão de
// remover os outros. Assento vago: botão para sentar (ou trocar de lugar) e, para o dono, o
// botão de pôr um bot.
function criarAssento(assento, sala, ctx) {
  const numero = assento.assento;
  const time = timeDoAssento(numero);
  const posicao = ctx.posicaoDe(numero);
  const raiz = el("div", `assento pos-${posicao} ${classeTime(time)}`);
  // No 2x2 o assento define o time, então o time aparece escrito.
  if (ctx.duplas) raiz.append(el("span", "rotulo-time", `Time ${time}`));

  if (ocupado(assento)) {
    const souEu = assento.usuario_id === usuario.id;
    if (souEu) raiz.classList.add("meu");
    const plaquinha = el("div", "plaquinha");
    plaquinha.title = `Time ${time}`;
    const nome = el("span", "nome", assento.nome);
    nome.title = assento.nome;
    plaquinha.append(el("span", "cor-time"), nome);
    if (souEu) plaquinha.append(el("span", "voce", "(você)"));
    if (assento.bot) plaquinha.append(el("span", "selo-bot", "BOT"));
    if (assento.usuario_id && assento.usuario_id === sala.dono_id) plaquinha.append(el("span", "selo-dono", "dono"));
    raiz.append(plaquinha);

    if (ctx.souDono && !souEu) {
      const remover = botaoDeAcao(`remover:${numero}`, "Remover", "botao botao-pequeno botao-remover", () =>
        removerDoAssento(numero),
      );
      remover.setAttribute("aria-label", `Remover ${assento.nome} da sala`);
      raiz.append(remover);
    }
    return raiz;
  }

  const lugar = `lugar ${NOME_POSICAO[posicao]}${ctx.duplas ? `, time ${time}` : ""}`;
  const vaga = botaoDeAcao(`sentar:${numero}`, ctx.meuAssento ? "Trocar para cá" : "Sentar aqui", "vaga", () => sentar(numero));
  vaga.prepend(el("span", "cor-time"));
  vaga.setAttribute("aria-label", `${vaga.textContent}: ${lugar}`);
  raiz.append(vaga);

  if (ctx.souDono) {
    const bot = botaoDeAcao(`bot:${numero}`, "Adicionar bot", "botao botao-pequeno", () => colocarBot(numero));
    bot.setAttribute("aria-label", `${bot.textContent} no ${lugar}`);
    raiz.append(bot);
  }
  return raiz;
}

// Centro da mesa: o baralho esperando e quantos lugares faltam.
function criarCentroSala(sala, ctx) {
  const centro = el("div", "centro-sala");
  const baralho = el("div", "baralho");
  baralho.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) baralho.append(criarVerso());

  const total = sala.assentos.length;
  let falta = "Mesa completa";
  if (ctx.vagas === 1) falta = "Falta 1 jogador";
  else if (ctx.vagas > 1) falta = `Faltam ${ctx.vagas} jogadores`;

  centro.append(
    baralho,
    el("p", "ocupacao", `${total - ctx.vagas} de ${total} jogadores`),
    el("p", `falta${ctx.vagas === 0 ? " completa" : ""}`, falta),
  );
  return centro;
}

// Barra abaixo da mesa: sair, a situação da sala e, para o dono, o botão de iniciar.
function criarBarraSala(ctx) {
  const barra = el("div", "barra-sala");

  const sairOuVoltar = ctx.meuAssento
    ? botaoDeAcao("sair", "Sair da sala", "botao", sairDaSalaAtual)
    : criarBotao("voltar-lista", "Voltar à lista", "botao", () => voltarParaLista());

  let situacao;
  if (!ctx.meuAssento) situacao = ctx.vagas ? "Escolha um lugar vago para entrar na sala." : "Esta sala está cheia.";
  else if (!ctx.souDono) situacao = "Aguardando o dono iniciar…";
  else if (ctx.vagas) situacao = "Complete a mesa com jogadores ou bots para iniciar.";
  else situacao = "Mesa completa: já dá para iniciar.";

  barra.append(sairOuVoltar, el("p", "situacao", situacao));
  // O botão fica desabilitado enquanto houver vaga; quem decide de verdade é o servidor.
  if (ctx.souDono) barra.append(botaoDeAcao("iniciar", "Iniciar partida", "botao botao-iniciar", comecarPartida, ctx.vagas === 0));
  return barra;
}

function renderizarSala() {
  const raiz = el("section", "sala");
  raiz.setAttribute("aria-labelledby", "titulo-vista");
  const { sala } = estado;

  if (!sala) {
    raiz.append(criarTituloVista("Sala"), el("p", "carregando", "Carregando sala…"));
    trocarConteudo(vista, raiz);
    return;
  }

  const ctx = derivarSala(sala);
  const dono = sala.assentos.find((a) => a.usuario_id === sala.dono_id);
  const topo = el("div", "sala-topo");
  const titulo = criarTituloVista(ctx.souDono ? `Sua sala ${sala.formato}` : `Sala ${sala.formato} de ${dono?.nome ?? "outro jogador"}`);
  titulo.title = titulo.textContent;
  topo.append(titulo, el("p", "dica", ctx.duplas ? "Parceiros sentam frente a frente." : "Um contra um."));

  // A mesa vista de cima, como na mesa de jogo: você embaixo e os outros em volta.
  const feltro = el("div", "feltro");
  feltro.append(criarCentroSala(sala, ctx));
  const ordem = (assento) => ORDEM_POSICOES.indexOf(ctx.posicaoDe(assento.assento));
  for (const assento of [...sala.assentos].sort((a, b) => ordem(a) - ordem(b))) {
    feltro.append(criarAssento(assento, sala, ctx));
  }
  const mesa = el("div", "mesa");
  mesa.append(feltro);

  raiz.append(topo, mesa, criarBarraSala(ctx));
  trocarConteudo(vista, raiz);
}

// ---------- Ranking ----------

async function carregarRanking() {
  estado.ranking = { situacao: "carregando" };
  renderizarRanking();
  try {
    estado.ranking = { situacao: "pronto", linhas: await obterRanking() };
  } catch (erro) {
    if (sessaoEncerrada(erro)) return;
    estado.ranking = { situacao: "erro", mensagem: textoDoErro(erro) };
  }
  renderizarRanking();
}

// Painel do ranking: os 10 primeiros, com a linha do usuário logado em destaque. Se ele
// estiver mais abaixo, a linha dele aparece no fim, depois de um separador.
function renderizarRanking() {
  const titulo = el("h2", "ranking-titulo", "Ranking");
  titulo.id = "ranking-titulo";
  const conteudo = [titulo, el("p", "ranking-subtitulo", "Quem mais venceu")];

  const { situacao } = estado.ranking;
  if (situacao === "carregando") {
    conteudo.push(el("p", "ranking-situacao", "Carregando…"));
  } else if (situacao === "erro") {
    const tentar = el("button", "botao botao-pequeno", "Tentar de novo");
    tentar.type = "button";
    tentar.addEventListener("click", carregarRanking);
    conteudo.push(el("p", "ranking-situacao", estado.ranking.mensagem), tentar);
  } else if (estado.ranking.linhas.length === 0) {
    conteudo.push(el("p", "ranking-situacao", "Ninguém jogou ainda."));
  } else {
    const { linhas } = estado.ranking;
    conteudo.push(criarTabelaRanking(linhas));
    if (!linhas.some((linha) => linha.usuario_id === usuario.id)) {
      conteudo.push(el("p", "ranking-situacao", "Você entra no ranking depois da primeira partida."));
    }
  }
  trocarConteudo(painelRanking, ...conteudo);
}

function criarTabelaRanking(linhas) {
  const tabela = el("table", "ranking-tabela");
  const cabeca = el("tr");
  for (const [texto, classe] of [["#", "posicao"], ["Jogador", "nome"], ["Vitórias", "numero"], ["Partidas", "numero"]]) {
    const celula = el("th", classe, texto);
    celula.scope = "col";
    cabeca.append(celula);
  }
  const thead = el("thead");
  thead.append(cabeca);

  const corpo = el("tbody");
  const primeiras = linhas.slice(0, TAMANHO_RANKING);
  for (const linha of primeiras) corpo.append(criarLinhaRanking(linha));
  const minha = linhas.find((linha) => linha.usuario_id === usuario.id);
  if (minha && !primeiras.includes(minha)) {
    const separador = el("tr", "separador");
    const celula = el("td", "", "…");
    celula.colSpan = 4;
    separador.append(celula);
    corpo.append(separador, criarLinhaRanking(minha));
  }

  tabela.append(thead, corpo);
  return tabela;
}

// O nome de cada jogador leva ao histórico dele.
function criarLinhaRanking(linha) {
  const souEu = linha.usuario_id === usuario.id;
  const tr = el("tr", souEu ? "eu" : "");
  const nome = el("td", "nome");
  const celula = el("div", "celula-nome");
  const link = el("a", "nome-jogador", linha.nome);
  link.href = enderecoDoHistorico(linha.usuario_id);
  link.title = linha.nome;
  celula.append(link);
  if (souEu) celula.append(el("span", "voce", "(você)"));
  nome.append(celula);
  tr.append(
    el("td", "posicao", `${linha.posicao}º`),
    nome,
    el("td", "numero", String(linha.vitorias)),
    el("td", "numero", String(linha.partidas)),
  );
  return tr;
}

// ---------- Aviso ----------

// Mostra um aviso discreto no pé da área principal, que some sozinho. "daAtualizacao" marca
// os erros da atualização periódica: eles somem assim que uma atualização der certo.
function mostrarAviso(texto, tipo = "erro", daAtualizacao = false) {
  const repetido = estado.aviso?.texto === texto && estado.aviso?.tipo === tipo;
  estado.aviso = { texto, tipo, daAtualizacao };
  clearTimeout(temporizadorAviso);
  temporizadorAviso = setTimeout(esconderAviso, DURACAO_AVISO_MS);
  // O mesmo aviso de novo (uma atualização que volta a falhar) só ganha mais tempo: redesenhar
  // faria o leitor de tela repetir a frase a cada 3 segundos.
  if (!repetido) renderizarAviso();
}

function esconderAviso() {
  clearTimeout(temporizadorAviso);
  estado.aviso = null;
  renderizarAviso();
}

function renderizarAviso() {
  const { aviso } = estado;
  if (!aviso) {
    areaAviso.replaceChildren();
    return;
  }
  const caixa = el("div", `aviso-caixa ${aviso.tipo}`);
  const fechar = el("button", "aviso-fechar", "×");
  fechar.type = "button";
  fechar.setAttribute("aria-label", "Fechar aviso");
  fechar.addEventListener("click", esconderAviso);
  caixa.append(el("p", "aviso-texto", aviso.texto), fechar);
  areaAviso.replaceChildren(caixa);
}

// ---------- Troca de vista ----------

// Abre a vista da sala com os dados recebidos e guarda a sala na URL. A URL é trocada sem
// criar entrada no histórico: o botão Voltar do navegador sai do lobby, como antes.
function abrirSala(sala) {
  versao++;
  estado.salaId = sala.id;
  estado.salas = null;
  estado.sala = null;
  estado.estavaNaSala = false;
  history.replaceState(null, "", `?sala=${encodeURIComponent(sala.id)}`);
  receberSala(sala);
  garantirFoco();
  agendarAtualizacao();
}

// Volta para a lista de salas, com um aviso opcional ("Você foi removido da sala.", por exemplo).
function voltarParaLista(aviso) {
  versao++;
  estado.salaId = null;
  estado.sala = null;
  estado.salas = null;
  estado.estavaNaSala = false;
  history.replaceState(null, "", location.pathname);
  if (aviso) mostrarAviso(aviso, "info");
  renderizar();
  garantirFoco();
  atualizarAgora();
}

// A página vai ser trocada: a atualização periódica para de vez.
function pararTudo() {
  saindo = true;
  clearTimeout(temporizador);
}

function irParaLogin() {
  pararTudo();
  location.replace(PAGINA_LOGIN);
}

// Vai para a mesa da partida. Antes, a URL do lobby perde a sala: assim, o botão Voltar do
// navegador, na mesa, traz de volta à lista de salas, e não a esta sala, que já começou.
function irParaMesa(partidaId) {
  pararTudo();
  history.replaceState(null, "", location.pathname);
  location.assign(`${PAGINA_MESA}?partida=${encodeURIComponent(partidaId)}`);
}

// ---------- Dados recebidos ----------

function receberLista(salas) {
  estado.salas = salas;
  renderizar();
}

// Aplica uma versão nova da sala, vinda da atualização periódica ou da resposta de uma ação.
function receberSala(sala) {
  const estou = sala.assentos.some((a) => a.usuario_id === usuario.id);
  // A partida começou: quem está na sala vai para a mesa; quem só olhava volta para a lista.
  if (sala.partida_id) {
    if (estou) irParaMesa(sala.partida_id);
    else voltarParaLista("A partida desta sala já começou.");
    return;
  }
  if (sala.status !== "aguardando") {
    voltarParaLista("A sala foi encerrada.");
    return;
  }
  if (estado.estavaNaSala && !estou) {
    voltarParaLista("Você foi removido da sala.");
    return;
  }
  estado.sala = sala;
  estado.estavaNaSala = estou;
  renderizar();
}

// ---------- Ações ----------

// Executa a requisição de um botão. Enquanto ela não termina, todos os botões ficam
// desabilitados (contra o clique duplo) e a atualização periódica espera. Um erro vira aviso,
// e a vista é atualizada na hora, porque os dados na tela podem estar velhos (é o caso de
// "assento ocupado").
async function executar(chave, requisicao) {
  if (estado.acao || saindo) return;
  const chaveFocada = document.activeElement?.dataset.chave;
  versao++;
  estado.acao = chave;
  renderizar();
  try {
    await requisicao();
  } catch (erro) {
    if (!sessaoEncerrada(erro)) {
      mostrarAviso(textoDoErro(erro));
      atualizarDeNovo = true;
    }
  } finally {
    estado.acao = null;
  }
  if (saindo) return;
  renderizar();
  garantirFoco(chaveFocada);
  continuarAtualizacao();
}

async function criarEAbrir(formato) {
  abrirSala(await criarSala(formato));
}

// Entra no primeiro assento livre da sala e abre a vista dela.
async function entrarEAbrir(sala) {
  const livre = sala.assentos.find((assento) => !ocupado(assento));
  abrirSala(await entrarNaSala(sala.id, livre.assento));
}

// Senta no assento vago; para quem já está na sala, é uma troca de assento.
async function sentar(numero) {
  receberSala(await entrarNaSala(estado.salaId, numero));
}

async function colocarBot(numero) {
  receberSala(await adicionarBot(estado.salaId, numero));
}

async function removerDoAssento(numero) {
  receberSala(await liberarAssento(estado.salaId, numero));
}

// Só o dono vê o botão. Com o partida_id da resposta, vai direto para a mesa; os outros
// jogadores vão quando a atualização periódica trouxer a sala com o partida_id.
async function comecarPartida() {
  const { partida_id: partidaId } = await iniciarPartida(estado.salaId);
  irParaMesa(partidaId);
}

// Sai da sala e volta para a lista. Se o servidor responder que a sala não existe mais ou
// que o usuário já não está nela, o resultado é o mesmo: volta para a lista.
async function sairDaSalaAtual() {
  try {
    await sairDaSala(estado.salaId);
  } catch (erro) {
    if (!(erro instanceof ErroApi) || ![404, 409].includes(erro.status)) throw erro;
  }
  voltarParaLista();
}

// Logout: sai da sala em que estiver sentado (para não deixar um lugar ocupado à toa), apaga
// a sessão e volta para a tela de login. Se a saída da sala falhar, o logout acontece igual.
async function sairDaConta() {
  if (estado.salaId && estado.estavaNaSala) {
    try {
      await sairDaSala(estado.salaId);
    } catch {
      // Segue para o logout.
    }
  }
  sair();
  irParaLogin();
}

// ---------- Atualização periódica ----------

// Com a aba oculta, a lista de salas para de atualizar. A sala de espera não para: é o GET
// da sala que mantém o jogador no assento (o servidor tira quem some por um tempo).
function pausadaPelaAba() {
  return document.hidden && !estado.salaId;
}

// Pede agora os dados da vista atual. Se já houver um pedido ou uma ação em andamento, a
// atualização é feita logo depois que eles terminarem. Na lista com a aba oculta, não faz
// nada: a atualização volta quando a aba aparece.
function atualizarAgora() {
  clearTimeout(temporizador);
  temporizador = null;
  if (saindo || pausadaPelaAba()) return;
  if (atualizando || estado.acao) {
    atualizarDeNovo = true;
    return;
  }
  buscarDados();
}

// Agenda a próxima atualização para daqui a 3 segundos.
function agendarAtualizacao() {
  clearTimeout(temporizador);
  temporizador = null;
  if (saindo || pausadaPelaAba() || atualizando || estado.acao) return;
  temporizador = setTimeout(atualizarAgora, INTERVALO_ATUALIZACAO_MS);
}

// Depois de um pedido ou de uma ação: atualiza de novo na hora, se alguém pediu, ou agenda.
function continuarAtualizacao() {
  if (atualizarDeNovo) {
    atualizarDeNovo = false;
    atualizarAgora();
  } else {
    agendarAtualizacao();
  }
}

// Um pedido de atualização. A resposta é descartada se a tela mudou enquanto ela não chegava
// (troca de vista ou ação), porque pode trazer dados de antes da mudança. Um erro não
// interrompe a atualização periódica: vira aviso, e a próxima tentativa vem no horário.
async function buscarDados() {
  atualizando = true;
  const versaoDoPedido = versao;
  const { salaId } = estado;
  try {
    const dados = salaId ? await obterSala(salaId) : await listarSalas();
    if (versaoDoPedido === versao) {
      if (estado.aviso?.daAtualizacao) esconderAviso();
      if (salaId) receberSala(dados);
      else receberLista(dados);
    }
  } catch (erro) {
    if (!sessaoEncerrada(erro) && versaoDoPedido === versao) {
      if (salaId && erro instanceof ErroApi && erro.status === 404) {
        voltarParaLista(estado.sala ? "A sala foi encerrada." : erro.mensagem);
      } else {
        mostrarAviso(textoDoErro(erro), "erro", true);
      }
    }
  } finally {
    atualizando = false;
  }
  continuarAtualizacao();
}

// ---------- Início ----------

function iniciar() {
  usuario = obterUsuario();
  // Token sem os dados do usuário (sessão corrompida): sem o id, a tela não sabe qual assento
  // é o do jogador. Melhor entrar de novo.
  if (!usuario?.id) {
    sair();
    irParaLogin();
    return;
  }

  estado.salaId = new URLSearchParams(location.search).get("sala") || null;
  renderizar();
  renderizarAviso();
  tela.hidden = false;
  carregarRanking();
  atualizarAgora();

  // Aba oculta: a lista para de atualizar; a sala de espera continua. Ao voltar, atualiza na
  // hora e retoma o ritmo.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      atualizarAgora();
    } else if (pausadaPelaAba()) {
      clearTimeout(temporizador);
      temporizador = null;
    }
  });

  // Voltando pelo histórico, o navegador pode devolver a página congelada do jeito que estava
  // (com a atualização parada). Nesse caso, recarrega para começar do zero.
  window.addEventListener("pageshow", (evento) => {
    if (evento.persisted) location.reload();
  });
}

// Sem sessão, exigirLogin() manda para o login; com um token que o Auth recusa, conferirSessao()
// manda para o login com o aviso de sessão expirada. Nos dois casos a página não é montada.
if (exigirLogin() && (await conferirSessao())) iniciar();
