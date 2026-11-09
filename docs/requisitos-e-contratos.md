# Truco Online: requisitos e contratos

## Visão geral

Sistema web para jogar truco paulista online, em partidas 1x1 e 2x2, contra outras pessoas ou bots. O backend é dividido em microserviços em Python (FastAPI) e o frontend usa HTML, CSS e JavaScript puro.

Fora do escopo nesta versão: matchmaking automático, espectadores, mão de ferro com cartas às cegas e outras variantes de truco. A reconexão a uma partida em andamento está no escopo: ao reconectar, o jogador recebe o estado atual.

## Requisitos funcionais

| Código | Requisito | Serviço |
|---|---|---|
| RF01 | O usuário deve poder se cadastrar com nome, e-mail e senha | Auth |
| RF02 | O usuário deve poder entrar e sair da conta (sair apaga o token do navegador) | Auth |
| RF03 | O usuário deve poder criar uma sala escolhendo o formato 1x1 ou 2x2 | Lobby |
| RF04 | O usuário deve poder ver a lista de salas abertas e entrar em uma delas | Lobby |
| RF05 | No formato 2x2, o usuário deve poder escolher o assento e, assim, o time | Lobby |
| RF06 | O dono da sala deve poder adicionar bots aos assentos vazios | Lobby, Bots |
| RF07 | O dono da sala deve poder iniciar a partida quando todos os assentos estiverem ocupados | Lobby, Game |
| RF08 | O sistema deve distribuir 3 cartas a cada jogador e revelar a vira, definindo as manilhas | Game |
| RF09 | O jogador da vez deve poder jogar uma carta aberta ou, a partir da segunda rodada, coberta | Game |
| RF10 | O jogador deve poder pedir truco e aumentar para 3, 6, 9 e 12 | Game |
| RF11 | O time desafiado deve poder aceitar, correr ou aumentar a aposta | Game |
| RF12 | O sistema deve determinar o vencedor de cada rodada e de cada mão, incluindo empates | Game |
| RF13 | O sistema deve aplicar a mão de onze e a mão de ferro | Game |
| RF14 | O sistema deve encerrar a partida quando um time atingir 12 pontos | Game |
| RF15 | Os jogadores devem ver as jogadas dos outros em tempo real | Game |
| RF16 | Os jogadores devem poder trocar mensagens no chat da mesa | Game |
| RF17 | Os bots devem jogar automaticamente, apenas com jogadas válidas | Bots |
| RF18 | O usuário deve poder consultar o ranking geral e seu histórico de partidas | Ranking |

## Requisitos não funcionais

| Código | Requisito |
|---|---|
| RNF01 | O backend deve ser dividido em microserviços independentes, cada um com seu próprio banco de dados: um Postgres para o Auth, o Lobby e o Ranking (`auth-db`, `lobby-db` e `ranking-db`) e um Redis para o Game (`game-redis`). Os eventos entre os serviços passam por outro Redis, o broker `eventos` |
| RNF02 | Toda jogada deve ser validada no servidor; o cliente envia apenas a intenção da ação |
| RNF03 | Nenhum jogador deve receber as cartas dos adversários ou do parceiro, exceto na mão de onze |
| RNF04 | As atualizações da partida devem chegar aos jogadores em tempo real via WebSocket |
| RNF05 | As senhas devem ser armazenadas com hash (argon2) |
| RNF06 | As requisições autenticadas devem usar JWT, validado por cada serviço sem consultar o Auth |
| RNF07 | A falha do serviço de Ranking não deve impedir o andamento das partidas |
| RNF08 | O sistema completo deve subir com um único comando via Docker Compose |
| RNF09 | O motor de regras deve ter testes unitários automatizados |
| RNF10 | O frontend deve usar apenas HTML, CSS e JavaScript, sem frameworks |

## Serviços

O navegador só fala com o Nginx, e os serviços trocam eventos pelo broker. O diagrama completo, com as redes e os bancos, está na seção [Arquitetura do README](../README.md#arquitetura).

O Game concentra regras, estado e WebSocket; os bots se conectam a ele como jogadores comuns, e o Ranking só recebe eventos, sem ser chamado diretamente.

| Serviço | Responsabilidade | Dados |
|---|---|---|
| Gateway (Nginx) | Roteia `/api` e `/ws` e serve o frontend | Nenhum |
| Auth | Cadastro, login e emissão de JWT | Postgres próprio (`auth-db`) |
| Lobby | Salas, assentos, times, pedido de bots, início da partida | Postgres próprio (`lobby-db`) |
| Game: motor de regras | Regras do truco paulista em Python puro, sem I/O | Nenhum |
| Game: camada de serviço | FastAPI, WebSocket, chat, leitura e escrita do estado | Redis próprio (`game-redis`) |
| Bots | Joga partidas como cliente WebSocket | Nenhum |
| Ranking | Histórico e vitórias a partir de `partida.finalizada` | Postgres próprio (`ranking-db`) |
| Eventos (broker) | Leva `partida.criada`, `partida.finalizada` e `bot.solicitado` entre os serviços, com Redis Streams | Redis próprio (`eventos`), só com as mensagens em trânsito |
| Frontend | Login, lobby, mesa, animações e chat | Nenhum |

## Contratos REST

Todas as rotas públicas passam pelo Nginx com o prefixo `/api`. Exceto cadastro e login, exigem o cabeçalho `Authorization: Bearer <jwt>`. Erros seguem o formato `{"erro": "codigo", "mensagem": "texto"}`.

| Método | Rota | Corpo enviado | Resposta |
|---|---|---|---|
| POST | `/api/auth/cadastro` | `nome`, `email`, `senha` | 201 com `id`, `nome` |
| POST | `/api/auth/login` | `email`, `senha` | `token`, `usuario` |
| GET | `/api/auth/me` | | `id`, `nome`, `email` |
| POST | `/api/lobby/salas` | `formato` (`1x1` ou `2x2`) | 201 com a sala criada |
| GET | `/api/lobby/salas` | | lista de salas abertas |
| GET | `/api/lobby/salas/{id}` | | sala com assentos (responde também a quem não está nela) |
| POST | `/api/lobby/salas/{id}/entrar` | `assento` (0 a 3) | sala atualizada |
| POST | `/api/lobby/salas/{id}/sair` | | sala atualizada |
| POST | `/api/lobby/salas/{id}/bot` | `assento`, `nivel` | sala atualizada |
| DELETE | `/api/lobby/salas/{id}/assentos/{assento}` | | sala atualizada (só o dono) |
| POST | `/api/lobby/salas/{id}/iniciar` | | `partida_id` |
| GET | `/api/ranking` | | top 10 por vitórias, mais a linha do usuário se estiver fora dele |
| GET | `/api/ranking/jogadores/{id}` | | estatísticas e últimas partidas |

Regras do Lobby: um usuário fica em uma sala aberta por vez; se o dono sai, a sala passa a `encerrada`; quem fica 60 segundos sem consultar a sala perde o assento. Os códigos de erro de cada serviço estão nos guias desta pasta ([login](guia-backend-login.md), [lobby](guia-backend-lobby.md) e [mesa](guia-backend-mesa.md)).

Assentos: no 1x1 são 0 e 1; no 2x2, os assentos 0 e 2 formam o time A e os assentos 1 e 3 o time B. A ordem de jogo segue a numeração.

Rota interna, fora do Nginx: `POST /interno/partidas` no Game, chamada pelo Lobby com `sala_id` e a lista de assentos (`usuario_id`, `nome`, `bot`), devolvendo `partida_id`.

## Protocolo WebSocket

Conexão em `/ws/partidas/{partida_id}?token=<jwt>`, atendida pelo Game. Toda mensagem é um JSON com o campo `tipo`. Cartas são representadas por texto: valor (`4`, `5`, `6`, `7`, `Q`, `J`, `K`, `A`, `2`, `3`) seguido do naipe (`P` paus, `C` copas, `E` espadas, `O` ouros). Exemplo: `7O` é o 7 de ouros.

**Cliente para servidor**

| `tipo` | Campos | Quando |
|---|---|---|
| `jogar_carta` | `carta`, `coberta` (booleano) | Na vez do jogador |
| `pedir_truco` | | Na vez do jogador, sem aposta pendente |
| `responder_truco` | `resposta`: `aceitar`, `correr` ou `aumentar` | Quando o time dele foi desafiado |
| `decidir_mao_de_onze` | `jogar` (booleano) | Quando o time dele está com 11 pontos |
| `chat` | `texto` | A qualquer momento |

**Servidor para cliente**

O servidor envia apenas dois tipos de mensagem. Fim de rodada, de mão e de partida, truco pedido e chat chegam todos dentro do `estado`.

| `tipo` | Campos | Quando |
|---|---|---|
| `estado` | estado da partida na visão daquele jogador | Ao conectar e após cada ação válida, para todos os jogadores |
| `erro` | `codigo`, `mensagem` | Ação recusada: `fora_da_vez`, `carta_invalida`, `acao_invalida` ou `nao_autorizado` |

**Regras da conexão**

- Ao conectar, o servidor envia o estado atual. Isso também resolve reconexão e F5.
- Recusas fecham a conexão com 4401 (token inválido), 4403 (não pertence à partida) ou 4404 (partida inexistente). Quando o mesmo jogador abre a partida em outra conexão (outra aba, por exemplo), a anterior é fechada com 4409. O servidor aceita a conexão antes de fechar; sem isso a tela trata como queda e tenta reconectar indefinidamente.
- No 2x2, qualquer jogador do time pode responder ao truco ou decidir a mão de onze; vale a primeira resposta.
- Uma nova rodada só é criada quando a primeira carta dela é jogada. Ao fim de cada mão, o servidor espera cerca de 2 segundos antes de enviar a próxima; o estado de partida encerrada sai na hora.
- Chat: o estado traz as últimas 50 mensagens, com até 200 caracteres cada.

O frontend sempre redesenha a mesa a partir do `estado`, que é a fonte da verdade.

## Eventos assíncronos

Publicados no broker `eventos`, um Redis separado do `game-redis`, com Redis Streams (um stream por evento). Quem publica não espera resposta; se o consumidor estiver fora do ar, o evento fica na fila até ele voltar.

| Evento | Publicado por | Consumido por | Campos |
|---|---|---|---|
| `partida.criada` | Game | Nenhum (fica como registro) | `partida_id`, `sala_id`, `formato`, `criada_em` |
| `bot.solicitado` | Lobby | Bots | `partida_id`, `assento`, `nivel` |
| `partida.finalizada` | Game | Lobby, Ranking | `partida_id`, `sala_id`, `formato`, `times` (jogadores de cada time), `vencedor_time`, `placar_final`, `encerrada_em` |

O `bot.solicitado` é publicado pelo Lobby logo após receber o `partida_id`, um para cada assento ocupado por bot. O bot então se conecta ao WebSocket da partida com um token de serviço.

## Estado da partida

O Game guarda o estado completo no `game-redis`, na chave `partida:{partida_id}`. Esse objeto nunca sai do servidor como está: a mensagem `estado` enviada a cada jogador é uma visão filtrada dele.

Exemplo da mensagem `estado` como o jogador do assento 0 a recebe:

```json
{
  "tipo": "estado",
  "partida_id": "uuid",
  "formato": "2x2",
  "status": "em_andamento",
  "vencedor_time": null,
  "meu_assento": 0,
  "jogadores": [
    {"assento": 0, "nome": "Ian", "time": "A", "bot": false, "mao": ["7O", "3P", "KC"], "qtd_cartas": 3},
    {"assento": 1, "nome": "Bot 1", "time": "B", "bot": true, "qtd_cartas": 3},
    {"assento": 2, "nome": "Maria", "time": "A", "bot": false, "qtd_cartas": 3},
    {"assento": 3, "nome": "João", "time": "B", "bot": false, "qtd_cartas": 2}
  ],
  "placar": {"A": 4, "B": 7},
  "mao_atual": {
    "numero": 6,
    "pe": 2,
    "vira": "QE",
    "valor": 3,
    "tipo": "normal",
    "truco_pendente": {"pedido_por_time": "B", "valor_proposto": 6},
    "ultimo_aumento_time": "B",
    "aguardando_decisao_mao_de_onze": false,
    "rodadas": [
      {"jogadas": [{"assento": 3, "carta": null, "coberta": true}], "vencedor_time": null}
    ],
    "vez_assento": 0
  },
  "chat": [{"de": "Ian", "texto": "truco!"}]
}
```

Campos que pedem atenção:

- `status` é `em_andamento` ou `encerrada`; encerrada, `vencedor_time` traz `"A"` ou `"B"`.
- `tipo` da mão: `normal`, `mao_de_onze` ou `mao_de_ferro`. `aguardando_decisao_mao_de_onze` indica que o time com 11 ainda não decidiu se joga.
- `ultimo_aumento_time` impede que o mesmo time aumente duas vezes seguidas.
- `vencedor_time` de uma rodada pode ser `"empate"`, ou `null` enquanto ela está em andamento.
- `pe` é o assento de quem distribuiu; a primeira rodada começa no assento seguinte.
- A partida já nasce com a primeira mão distribuída: todo estado tem `mao_atual`.

Filtragem por jogador: `mao` aparece só para o próprio jogador; os outros têm apenas `qtd_cartas`. Carta jogada coberta vai como `"carta": null, "coberta": true`. Na mão de onze, o jogador do time com 11 pontos recebe também o campo `mao` no objeto do parceiro, durante a mão inteira.
