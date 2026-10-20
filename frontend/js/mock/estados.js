// Estados falsos no formato da mensagem "estado" do servidor (já filtrada para o jogador).
// Servem apenas para desenvolver a tela da mesa sem backend.

// 1. Início de mão no 1x1: sua vez, nenhuma carta jogada.
export const inicio1x1 = {
  partida_id: "mock-inicio-1x1",
  formato: "1x1",
  status: "em_andamento",
  meu_assento: 0,
  jogadores: [
    { assento: 0, nome: "Ian", time: "A", bot: false, mao: ["3P", "KC", "6O"], qtd_cartas: 3 },
    { assento: 1, nome: "Bot 1", time: "B", bot: true, qtd_cartas: 3 },
  ],
  placar: { A: 0, B: 0 },
  mao_atual: {
    numero: 1,
    pe: 1,
    vira: "5C",
    valor: 1,
    tipo: "normal",
    truco_pendente: null,
    ultimo_aumento_time: null,
    aguardando_decisao_mao_de_onze: false,
    rodadas: [],
    vez_assento: 0,
  },
  chat: [],
};

// 2. Meio de mão no 2x2: segunda rodada, primeira vencida pelo seu time,
//    uma carta coberta na mesa e vez de outro jogador.
export const meio2x2 = {
  partida_id: "mock-meio-2x2",
  formato: "2x2",
  status: "em_andamento",
  meu_assento: 0,
  jogadores: [
    { assento: 0, nome: "Ian", time: "A", bot: false, mao: ["3P", "KC"], qtd_cartas: 2 },
    { assento: 1, nome: "Bot 1", time: "B", bot: true, qtd_cartas: 2 },
    { assento: 2, nome: "Maria", time: "A", bot: false, qtd_cartas: 1 },
    { assento: 3, nome: "João", time: "B", bot: false, qtd_cartas: 2 },
  ],
  placar: { A: 4, B: 7 },
  mao_atual: {
    numero: 6,
    pe: 3,
    vira: "QE",
    valor: 3,
    tipo: "normal",
    truco_pendente: null,
    ultimo_aumento_time: "B",
    aguardando_decisao_mao_de_onze: false,
    rodadas: [
      {
        jogadas: [
          { assento: 0, carta: "4C", coberta: false },
          { assento: 1, carta: "2O", coberta: false },
          { assento: 2, carta: "JP", coberta: false },
          { assento: 3, carta: "AC", coberta: false },
        ],
        vencedor_time: "A",
      },
      {
        jogadas: [{ assento: 2, carta: null, coberta: true }],
        vencedor_time: null,
      },
    ],
    vez_assento: 3,
  },
  chat: [
    { de: "Maria", texto: "vamos!" },
    { de: "João", texto: "essa não vale, foi sorte" },
    { de: "Ian", texto: "boa, parceira" },
  ],
};

// 3. Truco pendente no 2x2: o time adversário pediu Seis e você precisa responder.
//    Aqui o jogador está no assento 1 (time B) para exercitar as posições relativas.
export const trucoPendente2x2 = {
  partida_id: "mock-truco-2x2",
  formato: "2x2",
  status: "em_andamento",
  meu_assento: 1,
  jogadores: [
    { assento: 0, nome: "Ana", time: "A", bot: false, qtd_cartas: 3 },
    { assento: 1, nome: "Ian", time: "B", bot: false, mao: ["2P", "6E", "QO"], qtd_cartas: 3 },
    { assento: 2, nome: "Bot 2", time: "A", bot: true, qtd_cartas: 3 },
    { assento: 3, nome: "Maria", time: "B", bot: false, qtd_cartas: 2 },
  ],
  placar: { A: 8, B: 6 },
  mao_atual: {
    numero: 9,
    pe: 2,
    vira: "AO",
    valor: 3,
    tipo: "normal",
    truco_pendente: { pedido_por_time: "A", valor_proposto: 6 },
    ultimo_aumento_time: "B",
    aguardando_decisao_mao_de_onze: false,
    rodadas: [
      {
        jogadas: [{ assento: 3, carta: "KO", coberta: false }],
        vencedor_time: null,
      },
    ],
    vez_assento: 0,
  },
  chat: [
    { de: "Maria", texto: "truco!" },
    { de: "Ana", texto: "SEIS!" },
    { de: "Maria", texto: "e agora, Ian?" },
  ],
};

// 4. Mão de onze no 1x1: seu time tem 11 pontos e precisa decidir se joga.
export const maoDeOnze1x1 = {
  partida_id: "mock-onze-1x1",
  formato: "1x1",
  status: "em_andamento",
  meu_assento: 0,
  jogadores: [
    { assento: 0, nome: "Ian", time: "A", bot: false, mao: ["3O", "AE", "5P"], qtd_cartas: 3 },
    { assento: 1, nome: "Carla", time: "B", bot: false, qtd_cartas: 3 },
  ],
  placar: { A: 11, B: 8 },
  mao_atual: {
    numero: 14,
    pe: 0,
    vira: "7C",
    valor: 3,
    tipo: "mao_de_onze",
    truco_pendente: null,
    ultimo_aumento_time: null,
    aguardando_decisao_mao_de_onze: true,
    rodadas: [],
    vez_assento: 1,
  },
  chat: [{ de: "Carla", texto: "vai correr?" }],
};
