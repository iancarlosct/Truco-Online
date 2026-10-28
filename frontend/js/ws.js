// Conexão da mesa com a partida, pelo WebSocket do serviço Game.
// O servidor manda só dois tipos de mensagem: "estado" (a partida inteira, já na visão do
// jogador) e "erro" (uma ação recusada). A mesa envia as intenções do jogador por enviar().
// Se a conexão cair, ela é refeita sozinha, com uma espera maior a cada tentativa. Ao conectar
// de novo, o servidor manda o estado atual, e a mesa se redesenha a partir dele.

import { encerrarSessao } from "./api.js";
import { obterToken } from "./auth.js";
import { WebSocketSimulado } from "./mock/servidor-game.js";

// =====================================================================================
// PROVISÓRIO — REMOVER quando o serviço Game existir.
// Com true, a mesa não abre um WebSocket de verdade: conversa com o servidor simulado de
// js/mock/servidor-game.js, que imita o WebSocket do navegador e o serviço Game.
// Com false, a mesma conexão vai para o Game real, pelo gateway, no mesmo endereço da página,
// sem nenhuma outra mudança no código.
// =====================================================================================
const USAR_MOCK_GAME = true;

// Espera antes de cada nova tentativa depois de uma queda: 1 s, 2 s, 4 s, 8 s e, daí em
// diante, 10 s.
const ESPERA_INICIAL_MS = 1000;
const ESPERA_MAXIMA_MS = 10000;

// Códigos de fechamento combinados com o Game. Com eles não adianta tentar de novo.
const TOKEN_INVALIDO = 4401;
const FORA_DA_PARTIDA = 4403;
const PARTIDA_INEXISTENTE = 4404;
// O mesmo jogador abriu a partida em outra aba: vale a conexão mais recente, e o Game fecha
// esta. Se esta aba reconectasse, derrubaria a outra, e as duas ficariam se derrubando.
const CONEXAO_SUBSTITUIDA = 4409;

// Texto mostrado ao jogador quando a partida o recusa.
const MOTIVO_RECUSA = {
  [FORA_DA_PARTIDA]: "Você não faz parte desta partida.",
  [PARTIDA_INEXISTENTE]: "Esta partida não existe.",
  [CONEXAO_SUBSTITUIDA]: "Esta partida foi aberta em outra aba.",
};

// ws://<endereço da página>/ws/partidas/{partida_id}?token=<jwt>, ou wss:// com HTTPS.
function enderecoDaPartida(partidaId, token) {
  const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
  const caminho = `/ws/partidas/${encodeURIComponent(partidaId)}`;
  return `${protocolo}//${location.host}${caminho}?token=${encodeURIComponent(token)}`;
}

// Conecta à partida e devolve { enviar(mensagem), fechar() }.
// Os callbacks recebem:
//   aoReceberEstado(estado)  cada mensagem "estado"
//   aoReceberErro(erro)      cada mensagem "erro": { codigo, mensagem }
//   aoMudarConexao(situacao, motivo)
//     "conectando"    primeira tentativa
//     "conectado"     conexão aberta (o estado chega logo em seguida)
//     "reconectando"  caiu, ou não abriu, e vai tentar de novo
//     "recusada"      4403, 4404 ou 4409: a partida não aceita esta conexão; vem com o motivo
// O 4401 (token recusado) não chega à tela: encerra a sessão e volta para o login, como o 401
// das rotas HTTP.
export function conectarPartida(partidaId, { aoReceberEstado, aoReceberErro, aoMudarConexao }) {
  let socket = null;
  let falhas = 0; // tentativas seguidas que não receberam nada do servidor
  let temporizador = null;
  let encerrada = false; // fechar() foi chamado, ou o servidor recusou de vez

  function abrir() {
    temporizador = null;
    const token = obterToken();
    // Sem token (logout em outra aba, por exemplo), o servidor recusaria com 4401.
    if (!token) {
      encerrada = true;
      encerrarSessao();
      return;
    }
    const endereco = enderecoDaPartida(partidaId, token);
    socket = USAR_MOCK_GAME ? new WebSocketSimulado(endereco) : new WebSocket(endereco);
    socket.onopen = () => aoMudarConexao("conectado");
    socket.onmessage = (evento) => receber(evento.data);
    socket.onclose = (evento) => aoFechar(evento.code);
  }

  function receber(texto) {
    // A espera só volta ao começo quando o servidor responde: um servidor que aceita e fecha
    // na hora não pode virar uma tentativa por segundo.
    falhas = 0;
    let mensagem;
    try {
      mensagem = JSON.parse(texto);
    } catch {
      console.warn("[ws] Mensagem que não é JSON:", texto);
      return;
    }
    if (mensagem?.tipo === "estado") aoReceberEstado(mensagem);
    else if (mensagem?.tipo === "erro") aoReceberErro(mensagem);
    else console.warn("[ws] Mensagem de tipo desconhecido:", mensagem);
  }

  function aoFechar(codigo) {
    socket = null;
    if (encerrada) return;
    if (codigo === TOKEN_INVALIDO) {
      encerrada = true;
      encerrarSessao();
    } else if (MOTIVO_RECUSA[codigo]) {
      encerrada = true;
      aoMudarConexao("recusada", MOTIVO_RECUSA[codigo]);
    } else {
      // Qualquer outro fechamento é uma queda: tenta de novo, esperando cada vez mais.
      const espera = Math.min(ESPERA_INICIAL_MS * 2 ** falhas, ESPERA_MAXIMA_MS);
      falhas++;
      aoMudarConexao("reconectando");
      temporizador = setTimeout(abrir, espera);
    }
  }

  aoMudarConexao("conectando");
  abrir();

  return {
    // Envia uma intenção do jogador, como texto JSON. Devolve false quando a conexão não está
    // aberta: a mensagem não sai.
    enviar(mensagem) {
      if (socket?.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify(mensagem));
      return true;
    },
    // Fecha a conexão de vez, sem tentar de novo (o jogador saiu da mesa).
    fechar() {
      encerrada = true;
      clearTimeout(temporizador);
      socket?.close(1000, "saiu da partida");
    },
  };
}
