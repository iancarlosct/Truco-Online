// Sessão do usuário logado: guarda, lê e apaga o token e os dados do usuário.
// Fica no localStorage, então a sessão continua valendo depois de fechar o navegador.

const CHAVE_TOKEN = "truco.token";
const CHAVE_USUARIO = "truco.usuario";

// Tela de login, para onde vai quem abre outra página sem estar logado.
const PAGINA_LOGIN = "index.html";

// Guarda o token (JWT) e o usuário devolvidos pelo login: { id, nome, email }.
export function salvarSessao(token, usuario) {
  localStorage.setItem(CHAVE_TOKEN, token);
  localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
}

// Token salvo, ou null quando não há sessão.
export function obterToken() {
  return localStorage.getItem(CHAVE_TOKEN);
}

// Usuário salvo ({ id, nome, email }), ou null quando não há sessão.
export function obterUsuario() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_USUARIO));
  } catch {
    // Valor corrompido no localStorage: vale como se não houvesse usuário.
    return null;
  }
}

// Apaga a sessão (logout). Não redireciona: quem chama decide para onde ir.
export function sair() {
  localStorage.removeItem(CHAVE_TOKEN);
  localStorage.removeItem(CHAVE_USUARIO);
}

export function estaLogado() {
  return Boolean(obterToken());
}

// Para as páginas que exigem login: sem token, manda para a tela de login.
// Devolve true quando há sessão; com false a página não deve continuar a se montar:
//   if (exigirLogin()) iniciar();
export function exigirLogin() {
  if (estaLogado()) return true;
  location.replace(PAGINA_LOGIN);
  return false;
}
