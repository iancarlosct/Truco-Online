// Tela de login e cadastro.
// O HTML da tela é fixo (index.html); este módulo cuida das abas, da validação dos campos
// e do envio dos formulários. Quem fala com o backend é o api.js.

import { cadastrar, login, ErroApi } from "../api.js";
import { estaLogado, salvarSessao } from "../auth.js";

// Página aberta depois do login. Ainda não existe: será criada junto com o lobby.
const PAGINA_APOS_LOGIN = "lobby.html";

// Limites dos campos do cadastro.
const NOME_MAX = 20;
const SENHA_MIN = 6;

// Formato básico de e-mail: algo@algo.algo, sem espaços.
const FORMATO_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Aviso para quem chega com "?sessao=expirada": é para onde o api.js manda quem teve a sessão
// recusada pelo servidor (resposta 401).
const AVISO_SESSAO_EXPIRADA = "Sua sessão expirou. Entre novamente.";

// Texto do botão de cada formulário: parado e enquanto a requisição está em andamento.
const TEXTO_BOTAO = {
  entrar: { parado: "Entrar", enviando: "Entrando…" },
  cadastro: { parado: "Criar conta", enviando: "Criando conta…" },
};

const conjunto = document.getElementById("conjunto");
const mensagem = document.getElementById("mensagem");

// As duas abas do cartão, cada uma com o botão da aba, o painel, o formulário e o botão
// de envio do formulário.
const abas = {};
for (const nome of ["entrar", "cadastro"]) {
  const formulario = document.getElementById(`form-${nome}`);
  abas[nome] = {
    botao: document.getElementById(`aba-${nome}`),
    painel: document.getElementById(`painel-${nome}`),
    formulario,
    botaoEnviar: formulario.querySelector(".botao-principal"),
  };
}

// Verdadeiro enquanto há uma requisição em andamento (evita envio duplo).
let enviando = false;

// ---------- Validação ----------

// Quantidade de caracteres de verdade: um emoji conta 1, e não 2 como em texto.length.
function tamanho(texto) {
  return [...texto].length;
}

// Cada regra recebe o valor do campo (e, se precisar, todos os valores do formulário)
// e devolve o texto do erro, ou "" quando o valor é válido.

function validarNome(nome) {
  if (!nome) return "Informe seu nome.";
  if (tamanho(nome) > NOME_MAX) return `O nome pode ter no máximo ${NOME_MAX} caracteres.`;
  return "";
}

function validarEmail(email) {
  if (!email) return "Informe seu e-mail.";
  if (!FORMATO_EMAIL.test(email)) return "Informe um e-mail válido, como nome@exemplo.com.";
  return "";
}

function validarSenhaInformada(senha) {
  return senha ? "" : "Informe sua senha.";
}

function validarSenhaNova(senha) {
  if (!senha) return "Informe sua senha.";
  if (tamanho(senha) < SENHA_MIN) return `A senha precisa ter no mínimo ${SENHA_MIN} caracteres.`;
  return "";
}

function validarConfirmacao(confirmacao, valores) {
  if (!confirmacao) return "Repita a senha.";
  if (confirmacao !== valores.senha) return "As senhas não são iguais.";
  return "";
}

// Regras de cada formulário, pelo "name" do campo. No login a senha só precisa estar
// preenchida: o tamanho mínimo vale para quem está criando a conta.
const REGRAS = {
  entrar: { email: validarEmail, senha: validarSenhaInformada },
  cadastro: {
    nome: validarNome,
    email: validarEmail,
    senha: validarSenhaNova,
    confirmacao: validarConfirmacao,
  },
};

// Valores digitados, pelo "name" de cada campo. Nome e e-mail vão sem espaços nas pontas;
// as senhas vão exatamente como foram digitadas.
function lerValores(formulario) {
  const valores = Object.fromEntries(new FormData(formulario));
  for (const nome of ["nome", "email"]) {
    if (nome in valores) valores[nome] = valores[nome].trim();
  }
  return valores;
}

// Mostra o erro logo abaixo do campo. Com texto vazio, limpa o erro.
function mostrarErroCampo(campo, texto) {
  const erro = document.getElementById(campo.getAttribute("aria-describedby"));
  erro.textContent = texto;
  erro.hidden = !texto;
  if (texto) campo.setAttribute("aria-invalid", "true");
  else campo.removeAttribute("aria-invalid");
}

// Valida o formulário inteiro, mostra os erros junto aos campos e põe o foco no primeiro
// campo inválido. Devolve true quando está tudo certo.
function validar(formulario, regras, valores) {
  let primeiroInvalido = null;
  for (const [nome, regra] of Object.entries(regras)) {
    const campo = formulario.elements[nome];
    const erro = regra(valores[nome], valores);
    mostrarErroCampo(campo, erro);
    if (erro && !primeiroInvalido) primeiroInvalido = campo;
  }
  primeiroInvalido?.focus();
  return !primeiroInvalido;
}

// ---------- Abas e mensagem do cartão ----------

// Mensagem geral do cartão, usada para os erros vindos da API e, com o tipo "info", para o
// aviso de sessão expirada, num tom mais discreto. Com texto vazio, esconde.
function mostrarMensagem(texto, tipo = "erro") {
  mensagem.textContent = texto;
  mensagem.hidden = !texto;
  mensagem.classList.toggle("info", tipo === "info");
}

// Quem chega depois de um 401 vê o aviso de sessão expirada. O parâmetro sai da URL logo em
// seguida, para o aviso não voltar num F5. Num acesso normal, não aparece nada.
function avisarSessaoExpirada() {
  if (new URLSearchParams(location.search).get("sessao") !== "expirada") return;
  mostrarMensagem(AVISO_SESSAO_EXPIRADA, "info");
  history.replaceState(null, "", location.pathname);
}

// Mostra a aba pedida ("entrar" ou "cadastro") e esconde a outra.
function mostrarAba(nomeAtiva) {
  for (const [nome, aba] of Object.entries(abas)) {
    const ativa = nome === nomeAtiva;
    aba.botao.setAttribute("aria-selected", String(ativa));
    aba.botao.tabIndex = ativa ? 0 : -1;
    aba.painel.hidden = !ativa;
  }
  mostrarMensagem("");
}

// ---------- Envio ----------

// Liga ou desliga o estado de envio de um formulário: botão desabilitado com texto de
// carregamento, e abas travadas para não trocar de formulário no meio da requisição.
function definirEnviando(nome, ligado) {
  enviando = ligado;
  const { botaoEnviar } = abas[nome];
  botaoEnviar.disabled = ligado;
  botaoEnviar.textContent = TEXTO_BOTAO[nome][ligado ? "enviando" : "parado"];
  for (const aba of Object.values(abas)) aba.botao.disabled = ligado;
}

// Texto para mostrar ao usuário: a mensagem do ErroApi ou, num erro inesperado (um bug),
// um aviso genérico, com o detalhe no console.
function textoDoErro(erro) {
  if (erro instanceof ErroApi) return erro.mensagem;
  console.error(erro);
  return "Algo deu errado. Tente de novo.";
}

// Faz o login, guarda a sessão e segue para a próxima página.
async function entrar({ email, senha }) {
  const resposta = await login(email, senha);
  // Sem token não há sessão: melhor acusar o erro do que guardar um login que não vale.
  if (!resposta?.token) throw new Error("Resposta do login sem token.");
  salvarSessao(resposta.token, resposta.usuario);
  location.replace(PAGINA_APOS_LOGIN);
}

// Cria a conta e já entra com os mesmos dados.
async function criarConta({ nome, email, senha }) {
  await cadastrar(nome, email, senha);
  try {
    await entrar({ email, senha });
  } catch (erro) {
    // A conta foi criada; só o login automático falhou. Repetir o cadastro daria "e-mail
    // já cadastrado", então a tela vai para a aba "Entrar" com o e-mail preenchido.
    if (!(erro instanceof ErroApi)) console.error(erro);
    abas.cadastro.formulario.reset();
    abas.entrar.formulario.elements.email.value = email;
    mostrarAba("entrar");
    abas.entrar.formulario.elements.senha.focus();
    throw new ErroApi(
      "login_automatico_falhou",
      "Sua conta foi criada, mas não foi possível entrar agora. Entre com seu e-mail e sua senha.",
    );
  }
}

const ACOES = { entrar, cadastro: criarConta };

// Envia um formulário já validado. Se a ação falhar, mostra o erro no cartão e libera o
// formulário de novo; se der certo, a página é trocada e o botão continua desabilitado.
async function enviar(nome, valores) {
  const { botaoEnviar } = abas[nome];
  const focoNoBotao = document.activeElement === botaoEnviar;
  mostrarMensagem("");
  definirEnviando(nome, true);
  try {
    await ACOES[nome](valores);
  } catch (erro) {
    definirEnviando(nome, false);
    mostrarMensagem(textoDoErro(erro));
    // Um botão desabilitado perde o foco; devolve para quem está usando o teclado.
    if (focoNoBotao && document.activeElement === document.body) botaoEnviar.focus();
  }
}

// ---------- Início ----------

function iniciar() {
  for (const [nome, aba] of Object.entries(abas)) {
    aba.botao.addEventListener("click", () => {
      mostrarAba(nome);
      aba.formulario.elements[0].focus();
    });

    // O envio do formulário cobre tanto o clique no botão quanto a tecla Enter.
    aba.formulario.addEventListener("submit", (evento) => {
      evento.preventDefault();
      if (enviando) return;
      const valores = lerValores(aba.formulario);
      if (validar(aba.formulario, REGRAS[nome], valores)) enviar(nome, valores);
    });

    // Ao corrigir um campo, o erro dele some. Mexer na senha também limpa o erro da
    // confirmação, que depende dela.
    aba.formulario.addEventListener("input", (evento) => {
      mostrarErroCampo(evento.target, "");
      const confirmacao = aba.formulario.elements.confirmacao;
      if (evento.target.name === "senha" && confirmacao) mostrarErroCampo(confirmacao, "");
    });
  }

  // Setas para a esquerda e para a direita trocam de aba, como é costume em abas.
  document.querySelector(".abas").addEventListener("keydown", (evento) => {
    if (evento.key !== "ArrowLeft" && evento.key !== "ArrowRight") return;
    const outra = abas.entrar.painel.hidden ? "entrar" : "cadastro";
    mostrarAba(outra);
    abas[outra].botao.focus();
  });

  avisarSessaoExpirada();
  conjunto.hidden = false;
  abas.entrar.formulario.elements.email.focus();
}

// Quem já está logado não precisa passar por esta tela.
if (estaLogado()) {
  location.replace(PAGINA_APOS_LOGIN);
} else {
  iniciar();
}
