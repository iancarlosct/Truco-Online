// Utilitários de cartas: conversão de código ("7E") para arquivo SVG e criação de elementos.

const NAIPES = { P: "paus", C: "copas", E: "espadas", O: "ouros" };
const NOMES_VALOR = { Q: "Dama", J: "Valete", K: "Rei", A: "Ás" };

// Ordem de força das cartas no truco paulista (a manilha é a seguinte à vira).
const ORDEM = ["4", "5", "6", "7", "Q", "J", "K", "A", "2", "3"];

const PASTA = "assets/cartas";

// Separa "7E" em { valor: "7", naipe: "E" }.
function separar(codigo) {
  return { valor: codigo.slice(0, -1), naipe: codigo.slice(-1) };
}

// "7E" -> "assets/cartas/7_espadas.svg"
export function arquivoCarta(codigo) {
  const { valor, naipe } = separar(codigo);
  return `${PASTA}/${valor}_${NAIPES[naipe]}.svg`;
}

// "QC" -> "Dama de copas" (usado como texto alternativo)
function descricaoCarta(codigo) {
  const { valor, naipe } = separar(codigo);
  return `${NOMES_VALOR[valor] ?? valor} de ${NAIPES[naipe]}`;
}

function criarImagem(src, alt) {
  const img = document.createElement("img");
  img.className = "carta";
  img.src = src;
  img.alt = alt;
  img.draggable = false;
  return img;
}

// Elemento <img> de uma carta aberta.
export function criarCarta(codigo) {
  const img = criarImagem(arquivoCarta(codigo), descricaoCarta(codigo));
  img.dataset.carta = codigo;
  return img;
}

// Elemento <img> do verso (carta de outro jogador ou carta coberta).
export function criarVerso() {
  const img = criarImagem(`${PASTA}/verso.svg`, "Carta virada");
  img.classList.add("verso");
  return img;
}

// Valor da manilha a partir da vira. Aceita o código ("QE") ou só o valor ("Q").
// Depois do 3 volta para o 4.
export function proximaManilha(vira) {
  const valor = vira.length > 1 ? separar(vira).valor : vira;
  const indice = ORDEM.indexOf(valor);
  return ORDEM[(indice + 1) % ORDEM.length];
}
