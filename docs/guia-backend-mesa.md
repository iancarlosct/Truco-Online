# Guia do backend: o que a tela da mesa espera do serviço Game

Este guia é para quem vai implementar o serviço Game em Python com FastAPI. Ele explica o que o servidor precisa enviar e receber para a tela da mesa (`frontend/mesa.html`) funcionar conectada a ele, no lugar dos estados falsos (mocks) que ela usa hoje. Não é preciso conhecer FastAPI nem WebSocket: o guia explica o necessário e traz um exemplo pronto para rodar.

**De onde vêm as informações**

- **Código da tela**: `frontend/mesa.html`, `frontend/js/paginas/mesa.js`, `frontend/js/cartas.js` e `frontend/js/mock/estados.js`, na branch `feature/frontend-mesa` em 10/10/2026. Tudo o que o guia afirma que a tela lê, mostra ou envia saiu desse código e foi conferido rodando a tela no navegador com variações do estado.
- **Documento de requisitos e contratos** (link no [README](../README.md)): usado para o que o código ainda não cobre, como o endereço do WebSocket e as demais mensagens do protocolo.

Quando os dois não batem, ou quando o código depende de algo que não está escrito em lugar nenhum, o texto traz um código como **P3**. Ele aponta para o item correspondente da seção 9, Pontos em aberto.

**Importante:** a tela ainda não abre conexão com servidor nenhum. Hoje o estado vem dos mocks e as ações do jogador só são escritas no console do navegador (P1). A ligação com o WebSocket será feita no frontend; este guia descreve o lado do servidor.

## 1. Como a tela funciona

A tela não tem nenhuma regra de truco. Ela faz só duas coisas:

1. **Desenha o que recebe.** A função `renderizarMesa(estado)` apaga a tela e redesenha tudo a partir de um objeto de estado. Ela não guarda nada do estado anterior.
2. **Envia intenções do jogador.** Cada clique vira uma mensagem pequena ("quero jogar o 7 de ouros", "peço truco"). Todas saem por uma única função, `enviar(mensagem)`.

Quem decide se a jogada vale, de quem é a vez, quem ganhou a rodada e quanto vale a mão é o servidor.

```text
jogador clica -> tela envia a intenção -> servidor valida e atualiza o estado
              -> servidor envia "estado" a todos -> cada tela se redesenha
```

O que isso significa para o servidor:

- Toda mensagem `estado` precisa ser **completa**. A tela não sabe aplicar "só o que mudou".
- Nada muda na tela até chegar um novo `estado`. Se o jogador clica numa carta, ela continua na mão dele até o servidor mandar o estado sem ela.
- A tela habilita e desabilita botões olhando o estado (seção 4.4). Isso é comodidade para o jogador, não segurança: o servidor valida tudo de novo.

O pouco que a tela calcula sozinha serve só para exibir: a posição de cada jogador em volta da mesa (a partir de `meu_assento`), "Nós" e "Eles" no placar (a partir do time do jogador), a manilha (valor seguinte ao da `vira`) e o texto do botão de truco (a partir de `valor`).

## 2. Checklist do que o backend precisa entregar

Na ordem recomendada. Cada etapa termina em algo que dá para ver funcionando.

**Etapa 1: a tela abre com dados vindos do servidor**

- [ ] Projeto FastAPI rodando, com o Uvicorn instalado como `uvicorn[standard]` (seção 7).
- [ ] Endpoint WebSocket em `/ws/partidas/{partida_id}` que aceita a conexão (seção 3).
- [ ] Ao conectar, envio imediato de uma mensagem `estado` completa. Pode ser fixa (seção 4).
- [ ] Leitura das mensagens recebidas como JSON, sem derrubar a conexão quando chegar algo inválido.

**Etapa 2: cada jogador vê a sua própria mesa**

- [ ] Validação do token (`?token=<jwt>`) e descoberta do assento do jogador na partida.
- [ ] Recusa de token inválido, partida inexistente ou usuário que não está na partida.
- [ ] Registro das conexões abertas por partida e assento, com remoção ao desconectar.
- [ ] Visão filtrada por jogador: `meu_assento`, `mao` só do próprio, `qtd_cartas` de todos, carta coberta sem valor (seção 4.3).
- [ ] Envio do `estado` a todos os conectados sempre que ele mudar.
- [ ] Chat: a mensagem entra em `chat` com o nome do autor e o `estado` volta para todos.

**Etapa 3: uma partida 1x1 do começo ao fim**

- [ ] Partida criada já com a primeira mão distribuída (P9).
- [ ] `jogar_carta` com validação e atualização de `rodadas`, `qtd_cartas` e `vez_assento`.
- [ ] Fim de rodada (`vencedor_time`) e abertura da rodada seguinte antes da primeira carta dela (P10).
- [ ] Fim de mão: `placar` atualizado e nova mão (`numero`, `pe`, `vira`, cartas e `valor` inicial).
- [ ] `pedir_truco` e `responder_truco`, mantendo `valor`, `truco_pendente` e `ultimo_aumento_time`.
- [ ] Ação inválida não muda o estado e gera `erro` só para quem enviou.
- [ ] Fim de partida aos 12 pontos (P9).

**Etapa 4: comportamento completo**

- [ ] 2x2: quatro assentos, times alternados, resposta ao truco pelo time (P11).
- [ ] Carta coberta a partir da segunda rodada.
- [ ] Mão de onze: `tipo`, `aguardando_decisao_mao_de_onze` e `decidir_mao_de_onze` (P4, P6).
- [ ] Mão de ferro (P13).
- [ ] Demais mensagens do contrato: `truco_pedido`, `rodada_encerrada`, `mao_encerrada`, `partida_encerrada` e `chat` (P16).
- [ ] Bots conectando como clientes comuns.
- [ ] Queda de conexão e volta do jogador (P8, P20).

## 3. Conexão WebSocket

### 3.1 O que é e por que usar aqui

Numa requisição HTTP comum, o navegador pergunta e o servidor responde. O servidor não consegue avisar o navegador por conta própria. No truco isso não basta: quando um jogador joga uma carta, os outros precisam ficar sabendo na hora, sem perguntar.

O WebSocket resolve isso. A conexão começa como uma requisição HTTP normal (o "aperto de mão") e depois fica aberta. Enquanto ela estiver aberta, os dois lados podem enviar mensagens quando quiserem. Aqui cada mensagem é um texto em JSON. Cada jogador mantém uma conexão aberta por partida: é por ela que chegam os estados e saem as jogadas.

### 3.2 Endereço

Pelo documento de contratos, a conexão é em:

```text
/ws/partidas/{partida_id}?token=<jwt>
```

Quem atende é o Game. O gateway (Nginx) encaminha para ele tudo o que começa com `/ws` (P22).

| Situação | URL usada pelo navegador |
|---|---|
| Tudo rodando pelo Docker Compose | `ws://localhost/ws/partidas/<partida_id>?token=<jwt>` |
| Game rodando sozinho, como no exemplo da seção 7 | `ws://localhost:8001/ws/partidas/<partida_id>?token=<jwt>` |

`ws://` está para o WebSocket como `http://` está para as páginas. Com HTTPS, usa-se `wss://`.

Como chegam os dois dados:

- **`partida_id`** vem no caminho da URL. É o id devolvido por `POST /api/lobby/salas/{id}/iniciar`. O Lobby consegue esse id chamando `POST /interno/partidas` no Game.
- **`token`** vem depois do `?` (a query string). É o JWT recebido no login. Ele vai na URL porque o navegador não permite colocar cabeçalhos como `Authorization` numa conexão WebSocket.

Com o token, o Game descobre quem é o usuário sem consultar o Auth. Com a lista de assentos recebida na criação da partida (`usuario_id`, `nome`, `bot`), descobre em que assento ele está. Esse assento é o `meu_assento` da mensagem `estado` (P17).

Um detalhe para saber: o token aparece inteiro nos logs de acesso do Uvicorn e do Nginx, porque faz parte da URL.

### 3.3 O que o servidor faz ao receber uma conexão

1. Lê o `partida_id` do caminho e o `token` da query string.
2. Valida o token, localiza a partida e descobre o assento do usuário nela. Se algo falhar, encerra a conexão (seção 3.4).
3. Aceita a conexão e a guarda, associada à partida e ao assento.
4. **Envia na hora a mensagem `estado`** na visão daquele jogador. Sem ela a tela não tem o que desenhar.
5. Fica lendo as mensagens daquele jogador até a conexão cair.
6. Quando cair, tira a conexão da lista. O estado da partida continua guardado.

A tela não tem estado de "aguardando jogadores" nem de "partida encerrada": todo `estado` precisa trazer os 2 ou 4 jogadores e uma `mao_atual` preenchida (P9).

### 3.4 Como recusar uma conexão

Há duas formas, e o navegador enxerga cada uma de um jeito:

| O servidor faz | O navegador recebe |
|---|---|
| `close()` sem ter chamado `accept()` | Falha de conexão com código 1006 e sem motivo. O servidor responde HTTP 403. |
| `accept()` e depois `close(code=4401, reason="token inválido")` | Fechamento com o código 4401 e o motivo informado. |

A segunda forma permite que a tela diferencie "token inválido" de "partida não existe". Os códigos de 4000 a 4999 são livres para a aplicação. Quais usar ainda não foi combinado (P18).

Um caminho errado na URL também aparece como 403 e 1006. Se a conexão "falha sem motivo", confira primeiro o caminho.

### 3.5 Atrás do Docker e do Nginx

- Dentro do Docker, suba o Uvicorn com `--host 0.0.0.0`. O padrão é `127.0.0.1`, que só aceita conexões vindas de dentro do próprio contêiner.
- O Nginx precisa repassar o pedido de troca de protocolo no bloco do `/ws`, senão o aperto de mão falha. O trecho abaixo é a configuração padrão da documentação do Nginx. Ele não foi testado aqui, porque o gateway ainda não existe no repositório.

```nginx
location /ws/ {
    proxy_pass http://game:8000;   # nome e porta do serviço no docker-compose
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

- O Nginx fecha conexões que ficam 60 segundos sem receber dados do servidor. O Uvicorn envia um sinal de vida (ping) a cada 20 segundos por padrão, o que mantém a conexão aberta. Não é preciso criar mensagens de "ping" no protocolo.

## 4. A mensagem `estado`

É a única mensagem que a tela usa para se desenhar. O contrato a descreve assim: "a mensagem `estado` é a fonte da verdade para a tela: o frontend sempre redesenha a mesa a partir dela".

### 4.1 Campos

A mensagem é um objeto JSON com `"tipo": "estado"` e os campos abaixo, todos no primeiro nível (P2).

Como ler a coluna **Obrigatório**: *Sim* quer dizer que, sem o campo, a tela quebra (aparece um erro no console do navegador e ela fica parada no desenho anterior) ou mostra informação errada. *Não* quer dizer que a tela funciona sem ele; o que ela assume na ausência está na última coluna.

**Primeiro nível**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `tipo` | texto | Sim, pelo contrato | Sempre `"estado"`. A função que desenha a tela ignora este campo; ele serve para separar o `estado` das outras mensagens (P2). |
| `meu_assento` | inteiro | **Sim** | Assento do jogador que recebe a mensagem. Tem que ser igual ao `assento` de um dos `jogadores`, senão a tela quebra. Não existe no estado guardado no servidor: é acrescentado na visão de cada jogador (P3). |
| `jogadores` | lista | **Sim** | Exatamente 2 itens (1x1) ou 4 itens (2x2). Com outra quantidade a tela quebra (P9). A ordem da lista não importa: vale o campo `assento`. |
| `placar` | objeto | **Sim** | `{"A": 4, "B": 7}`. As duas chaves, com números. |
| `mao_atual` | objeto | **Sim** | Nunca `null` (P9). |
| `chat` | lista | **Sim** | Pode ser `[]`, mas tem que existir. |
| `partida_id` | texto | Não | A tela não lê. |
| `formato` | texto | Não | `"1x1"` ou `"2x2"`. A tela não lê: ela usa a quantidade de `jogadores`. |

**Cada item de `jogadores`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `assento` | inteiro | **Sim** | 0 e 1 no 1x1; 0 a 3 no 2x2. Tem que ser número (`0`), não texto (`"0"`). |
| `nome` | texto | **Sim** | Aparece na plaquinha do jogador e no aviso "Vez de Fulano.". Também define a cor do autor no chat (P14). |
| `time` | texto | **Sim** | Exatamente `"A"` ou `"B"`, em maiúsculas. Qualquer outro valor é tratado como B. |
| `bot` | booleano | Não | `true` mostra o selo "BOT". Ausente equivale a `false`. |
| `mao` | lista de cartas | Só no item do próprio jogador | Códigos das cartas que ele tem na mão (seção 4.2). Ausente equivale a mão vazia. Nos outros jogadores a tela ignora este campo (P6). |
| `qtd_cartas` | inteiro | **Sim** nos outros jogadores | Quantidade de versos que a tela desenha. No item do próprio jogador a tela não lê: usa o tamanho de `mao`. |

A tela posiciona cada jogador pela diferença entre o `assento` dele e o `meu_assento`: o próprio jogador fica embaixo, o assento seguinte à direita, depois em cima e por fim à esquerda (no 1x1, embaixo e em cima). Pelo contrato, a ordem de jogo segue a numeração dos assentos, então na tela a vez anda no sentido anti-horário. No 2x2 os assentos 0 e 2 são o time A e os assentos 1 e 3 o time B, por isso o parceiro aparece em frente. A tela não deduz o time pelo assento: ela lê `time`.

**`mao_atual`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `numero` | inteiro | **Sim** | Aparece no placar como "Mão 6". |
| `vira` | carta | **Sim** | Sempre um código de carta válido. `null` quebra a tela (P13). A manilha é calculada pela tela. |
| `valor` | inteiro | **Sim** | 1, 3, 6, 9 ou 12. Aparece como "Valendo 3" e define o texto do botão de truco: 1 mostra "Truco", 3 "Seis", 6 "Nove", 9 "Doze" (P12). |
| `tipo` | texto | **Sim** | `"normal"`, `"mao_de_onze"` ou `"mao_de_ferro"`. Os dois últimos mostram um selo no placar. Qualquer valor diferente de `"normal"` desabilita o botão de truco. |
| `rodadas` | lista | **Sim** | Pode ser `[]`, mas tem que existir. Formato mais abaixo. |
| `vez_assento` | inteiro ou `null` | **Sim** | Assento de quem joga agora. Com `null` (ou sem o campo) ninguém fica destacado e nenhuma carta fica clicável (P10). |
| `truco_pendente` | objeto ou `null` | Não | `null` ou ausente quando não há pedido em aberto. Formato mais abaixo. |
| `ultimo_aumento_time` | texto ou `null` | Não | `"A"`, `"B"` ou `null`. O time indicado fica com o botão de truco desabilitado (P12). |
| `aguardando_decisao_mao_de_onze` | booleano | Não | Ausente equivale a `false`. Tem que ser `true` para os botões da mão de onze aparecerem. Não está no documento de contratos (P4). |
| `pe` | inteiro | Não | A tela não lê. |

**`truco_pendente`, quando não é `null`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `pedido_por_time` | texto | **Sim** | `"A"` ou `"B"`: o time que fez o pedido. |
| `valor_proposto` | inteiro | **Sim** | 3, 6, 9 ou 12. Vira o nome do pedido no aviso: 3 é "Truco", 6 "Seis", 9 "Nove", 12 "Doze". Outro valor aparece como "undefined". |

**Cada item de `rodadas`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `jogadas` | lista | Não | Cartas jogadas na rodada, **na ordem em que foram jogadas** (as últimas são desenhadas por cima). Ausente equivale a `[]`. |
| `vencedor_time` | texto ou `null` | Não | `"A"`, `"B"`, `"empate"` ou `null` enquanto a rodada está em andamento. Ausente equivale a `null`. |

**Cada item de `jogadas`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `assento` | inteiro | **Sim** | Quem jogou. Define para que lado da mesa a carta fica deslocada. |
| `carta` | carta ou `null` | **Sim** | Código da carta, ou `null` se ela foi jogada coberta. Com `null` a tela mostra o verso. |
| `coberta` | booleano | Não | `true` faz a tela mostrar o verso, mesmo que `carta` venha preenchida (P5). Ausente equivale a `false`. |

**Cada item de `chat`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `de` | texto | **Sim** | Nome do autor. Se for igual ao `nome` de um jogador, aparece na cor do time dele; senão, em cor neutra. |
| `texto` | texto | **Sim** | A mensagem. A tela mostra como texto puro, sem interpretar HTML. |

**Como a tela usa `rodadas`**

- No centro da mesa aparecem **só as cartas do último item** da lista.
- Os três marcadores de rodada usam o `vencedor_time` das três primeiras posições: cor do time, cinza para `"empate"`, vazio para `null`. O último item da lista, se ainda não tem vencedor, ganha um contorno de "rodada atual".
- A opção "Jogar coberta" fica disponível quando a lista tem 2 itens ou mais.

Isso traz duas exigências que não estão escritas em lugar nenhum (P10):

1. O item da nova rodada tem que entrar em `rodadas` **antes** da primeira carta dela, com `"jogadas": []`. Se ele só for criado quando a primeira carta for jogada, quem abre a segunda rodada não consegue marcar "Jogar coberta".
2. Se a nova rodada entrar na lista no mesmo instante em que a anterior termina, a última carta da rodada anterior nunca aparece na mesa. Para os jogadores verem a rodada fechada, é preciso um estado intermediário (seção 6.4).

### 4.2 Cartas

Uma carta é um texto com o valor seguido do naipe, sempre em maiúsculas.

| Parte | Valores |
|---|---|
| Valor | `4`, `5`, `6`, `7`, `Q`, `J`, `K`, `A`, `2`, `3` (da mais fraca para a mais forte) |
| Naipe | `P` paus, `C` copas, `E` espadas, `O` ouros |

Exemplos: `7O` é o 7 de ouros, `QC` é a dama de copas. A manilha é o valor seguinte ao da vira nessa ordem; depois do `3` volta para o `4`. A tela calcula isso só para escrever "Manilha: J" ao lado da vira.

Um código fora desse padrão (`7o`, `10P`) não gera erro, mas a carta aparece como imagem quebrada.

### 4.3 Filtragem por jogador

O estado completo, com as cartas de todos, fica só no servidor. Cada jogador recebe uma visão montada para ele:

1. **`meu_assento`** é o assento de quem recebe a mensagem.
2. **`mao`** só aparece no item do próprio jogador. Nos demais itens ela não é enviada. A tela até ignoraria, mas as cartas chegariam ao navegador e qualquer um poderia vê-las nas ferramentas de desenvolvedor.
3. **`qtd_cartas`** vai em todos os itens de `jogadores`.
4. **Carta coberta** vai como `"carta": null` e `"coberta": true`, para todos os jogadores, inclusive quem jogou, e em todas as rodadas da lista (não só na última). A tela decide pelo `coberta`. Se o código da carta for junto, ela mostra o verso do mesmo jeito, mas a carta fica visível nas ferramentas do navegador (P5).
5. Nada além do que está nas tabelas da seção 4.1 precisa sair do servidor (baralho, `usuario_id`, `sala_id`). Campos a mais são ignorados pela tela.
6. Na mão de onze, o contrato manda enviar também a mão do parceiro ao time com 11 pontos. A tela ainda não mostra essas cartas (P6).

O exemplo 7.2 tem uma função `visao_do_jogador` que aplica as regras 1 a 4.

### 4.4 Campos que liberam cada ação

Lembrando: isso só define o que fica clicável. O servidor valida tudo de novo.

| Controle na tela | Fica habilitado quando |
|---|---|
| Cartas da mão | `vez_assento` é igual a `meu_assento`, `truco_pendente` é `null` e `aguardando_decisao_mao_de_onze` não é `true` |
| Botão de truco ("Truco", "Seis", "Nove" ou "Doze") | É a vez do jogador, `truco_pendente` é `null`, `valor` é menor que 12, `ultimo_aumento_time` não é o time dele e `tipo` é `"normal"` |
| "Aceitar" e "Correr" | Existe `truco_pendente` e `pedido_por_time` não é o time do jogador |
| "Aumentar" | O mesmo de "Aceitar", e `valor_proposto` menor que 12 |
| Caixa "Jogar coberta" | `rodadas` tem 2 itens ou mais |
| "Jogar a mão" e "Correr" da mão de onze | Só aparecem quando `aguardando_decisao_mao_de_onze` é `true` e o time do jogador tem exatamente 11 em `placar` |
| Chat | Sempre |

A barra de ações também mostra uma frase que depende do estado. Ela ajuda a conferir se o servidor mandou o que você esperava:

| Situação no estado | Frase mostrada |
|---|---|
| Truco pendente pedido pelo outro time | "Time adversário pediu Seis!" |
| Truco pendente pedido pelo time do jogador | "Aguardando o adversário responder ao pedido de Seis…" |
| Decisão de mão de onze pendente, time do jogador com 11 | "Mão de onze: seu time decide se joga ou corre." |
| Decisão de mão de onze pendente, time adversário com 11 | "Aguardando o adversário decidir a mão de onze…" |
| Vez do jogador | "Sua vez de jogar." |
| Vez de outro jogador | "Vez de João." |
| `vez_assento` é `null` | (nenhuma frase) |

### 4.5 Exemplo completo

Partida 2x2 na segunda rodada, enviada ao jogador do assento 0. A primeira rodada foi vencida pelo time A, a Maria abriu a segunda com uma carta coberta e agora é a vez do João.

```json
{
  "tipo": "estado",
  "partida_id": "p1",
  "formato": "2x2",
  "meu_assento": 0,
  "jogadores": [
    {"assento": 0, "nome": "Ian", "time": "A", "bot": false, "mao": ["3P", "KC"], "qtd_cartas": 2},
    {"assento": 1, "nome": "Bot 1", "time": "B", "bot": true, "qtd_cartas": 2},
    {"assento": 2, "nome": "Maria", "time": "A", "bot": false, "qtd_cartas": 1},
    {"assento": 3, "nome": "João", "time": "B", "bot": false, "qtd_cartas": 2}
  ],
  "placar": {"A": 4, "B": 7},
  "mao_atual": {
    "numero": 6,
    "pe": 3,
    "vira": "QE",
    "valor": 3,
    "tipo": "normal",
    "truco_pendente": null,
    "ultimo_aumento_time": "B",
    "aguardando_decisao_mao_de_onze": false,
    "rodadas": [
      {
        "jogadas": [
          {"assento": 0, "carta": "4C", "coberta": false},
          {"assento": 1, "carta": "2O", "coberta": false},
          {"assento": 2, "carta": "JP", "coberta": false},
          {"assento": 3, "carta": "AC", "coberta": false}
        ],
        "vencedor_time": "A"
      },
      {
        "jogadas": [
          {"assento": 2, "carta": null, "coberta": true}
        ],
        "vencedor_time": null
      }
    ],
    "vez_assento": 3
  },
  "chat": [
    {"de": "Maria", "texto": "vamos!"},
    {"de": "João", "texto": "essa não vale, foi sorte"},
    {"de": "Ian", "texto": "boa, parceira"}
  ]
}
```

Com esse estado, a tela mostra:

- Ian embaixo com o 3 de paus e o rei de copas; Bot 1 à direita com dois versos e o selo "BOT"; Maria em cima com um verso; João à esquerda, destacado, com dois versos.
- No centro, um verso do lado de cima (a carta coberta da Maria), a dama de espadas como vira e "Manilha: J".
- Marcadores de rodada: o primeiro na cor do time A, o segundo com o contorno de rodada atual, o terceiro vazio.
- Placar "Nós 4", "Eles 7", "Mão 6", "Valendo 3".
- Frase "Vez de João.", todos os botões desabilitados e a caixa "Jogar coberta" habilitada.

A mesma situação enviada ao João (assento 3) muda só em `meu_assento` e em quem recebe `mao`:

```json
{
  "meu_assento": 3,
  "jogadores": [
    {"assento": 0, "nome": "Ian", "time": "A", "bot": false, "qtd_cartas": 2},
    {"assento": 1, "nome": "Bot 1", "time": "B", "bot": true, "qtd_cartas": 2},
    {"assento": 2, "nome": "Maria", "time": "A", "bot": false, "qtd_cartas": 1},
    {"assento": 3, "nome": "João", "time": "B", "bot": false, "mao": ["5O", "7P"], "qtd_cartas": 2}
  ]
}
```

## 5. Mensagens que a tela envia

Todas são objetos JSON com o campo `tipo`. Nenhuma leva o nome nem o assento do jogador: o servidor sabe quem enviou pela conexão.

Hoje a função `enviar` só escreve a mensagem no console do navegador, no formato `[enviar] {...}`. Quando a tela for ligada ao WebSocket, cada mensagem irá como um texto JSON (P1).

| `tipo` | Campos | A tela envia quando |
|---|---|---|
| `jogar_carta` | `carta`, `coberta` | O jogador clica numa carta da mão |
| `pedir_truco` | nenhum | O jogador clica no botão de truco |
| `responder_truco` | `resposta` | O jogador clica em "Aceitar", "Correr" ou "Aumentar" |
| `decidir_mao_de_onze` | `jogar` | O jogador clica em "Jogar a mão" ou "Correr" |
| `chat` | `texto` | O jogador envia uma mensagem no chat |

As condições que deixam cada controle clicável estão na seção 4.4.

### 5.1 `jogar_carta`

```json
{"tipo": "jogar_carta", "carta": "7O", "coberta": false}
```

- `carta`: código de uma das cartas da `mao` do jogador.
- `coberta`: sempre presente. Só vai `true` quando a caixa "Jogar coberta" está marcada e `rodadas` tem 2 itens ou mais.

O que o servidor faz:

1. Confere que é a vez do jogador, que não há truco nem decisão de mão de onze pendente, que a carta está na mão dele e que `coberta` só vem `true` a partir da segunda rodada.
2. Tira a carta da mão, acrescenta a jogada ao final de `jogadas` da rodada atual e passa `vez_assento` para o próximo.
3. Se a rodada terminou, preenche `vencedor_time` (seção 6.4).
4. Envia o novo `estado` a todos.

Um clique duplo pode gerar duas mensagens seguidas. A segunda deve ser recusada como qualquer jogada fora da vez.

### 5.2 `pedir_truco`

```json
{"tipo": "pedir_truco"}
```

Não tem campos. O valor proposto é decidido pelo servidor a partir de `valor`: de 1 para 3, de 3 para 6, de 6 para 9, de 9 para 12.

O que o servidor faz:

1. Confere que é a vez do jogador, que não há pedido pendente, que `valor` é menor que 12, que o time dele não fez o último aumento e que a mão é `"normal"`.
2. Preenche `truco_pendente` com `pedido_por_time` e `valor_proposto`.
3. Envia o novo `estado` a todos.

Não é preciso mexer em `vez_assento`. Com `truco_pendente` preenchido, a tela já bloqueia as cartas de todos e libera os botões de resposta para o outro time.

### 5.3 `responder_truco`

```json
{"tipo": "responder_truco", "resposta": "aceitar"}
```

- `resposta`: `"aceitar"`, `"correr"` ou `"aumentar"`.

No 2x2, os **dois** jogadores do time desafiado veem os botões habilitados. Podem chegar duas respostas para o mesmo pedido (P11).

O que o servidor faz:

1. Confere que existe pedido pendente e que quem respondeu é do time desafiado.
2. Aplica a resposta:
   - `aceitar`: `valor` passa a ser o `valor_proposto`, `truco_pendente` volta a `null` e `ultimo_aumento_time` recebe o time que pediu.
   - `correr`: a mão termina, o time que pediu ganha os pontos de `valor`, o `placar` é atualizado e começa a próxima mão.
   - `aumentar`: o time que respondeu faz um novo pedido, um nível acima. `truco_pendente` passa a ter esse time em `pedido_por_time` e o novo `valor_proposto`.
3. Envia o novo `estado` a todos.

O momento exato em que `valor` e `ultimo_aumento_time` mudam é regra do motor e precisa ser confirmado (P12).

### 5.4 `decidir_mao_de_onze`

```json
{"tipo": "decidir_mao_de_onze", "jogar": true}
```

- `jogar`: `true` no botão "Jogar a mão", `false` no botão "Correr".

Enquanto `aguardando_decisao_mao_de_onze` é `true`, a tela bloqueia as cartas de todos os jogadores. No 2x2, os dois parceiros do time com 11 pontos veem os botões (P11).

O que o servidor faz:

1. Confere que há decisão pendente e que quem enviou é do time com 11 pontos.
2. Com `true`: `aguardando_decisao_mao_de_onze` passa a `false` e a mão segue. Com `false`: a mão termina, o outro time pontua e começa a próxima mão. Quantos pontos vale cada caso é regra do motor.
3. Envia o novo `estado` a todos.

### 5.5 `chat`

```json
{"tipo": "chat", "texto": "boa, parceira"}
```

- `texto`: o que o jogador digitou, sem espaços no começo e no fim. A tela não envia texto vazio e o campo aceita até 200 caracteres, mas esses limites só existem no navegador.

O que o servidor faz:

1. Confere que `texto` é um texto não vazio e limita o tamanho.
2. Acrescenta `{"de": "<nome do jogador>", "texto": "..."}` ao final de `chat`.
3. Envia o novo `estado` a todos, inclusive a quem escreveu. A tela não mostra a própria mensagem até recebê-la de volta (P7).

## 6. Comportamentos esperados

### 6.1 Depois de cada ação válida

- Atualizar o estado, salvar e enviar `estado` a **todos** os conectados da partida, cada um com a sua visão (seção 4.3). Isso inclui quem fez a ação.
- Enviar sempre o estado inteiro.

### 6.2 Ações inválidas

- Não alterar o estado e não avisar os outros jogadores.
- Responder só a quem enviou, com a mensagem `erro` do contrato. Os códigos ainda não foram definidos (P15):

```json
{"tipo": "erro", "codigo": "fora_da_vez", "mensagem": "Não é a sua vez."}
```

- Não fechar a conexão por causa de uma jogada inválida.
- Tratar do mesmo jeito as mensagens malformadas: texto que não é JSON, objeto sem `tipo`, `tipo` desconhecido, campo faltando. O servidor nunca pode cair por causa de uma mensagem.

A tela ainda não mostra erros (P15). Como ela só muda quando chega um `estado`, uma ação recusada simplesmente não tem efeito visível. Se quiser garantir que a tela de quem errou está em dia, reenvie o `estado` só para ele.

### 6.3 Chat

- O chat volta para a tela dentro da lista `chat` do `estado`. A tela redesenha a lista inteira e rola até a última mensagem.
- O contrato também prevê uma mensagem `chat` separada, do servidor para o cliente. A tela não a usa (P7).
- A lista inteira viaja em todo `estado`. Vale limitar o histórico, por exemplo às 50 últimas mensagens (P14).

### 6.4 Fim de rodada, de mão e de partida

A tela não tem animação nem pausa própria. Ela mostra o último `estado` recebido e, no centro, só a última rodada da lista.

Para os jogadores verem a rodada completa antes de a mesa ser limpa, uma opção que funciona com a tela de hoje, sem mudar o frontend, é:

1. Enviar o estado com a rodada completa, `vencedor_time` preenchido e `"vez_assento": null`.
2. Esperar um instante, algo como 1,5 segundo. Use `await asyncio.sleep(1.5)`. Nunca use `time.sleep`, que trava o servidor inteiro, para todas as partidas.
3. Enviar o estado seguinte: a nova rodada em `rodadas` com `"jogadas": []` e `vez_assento` preenchido, ou a nova mão.

O mesmo vale para o fim da mão, para o placar atualizado aparecer antes de as cartas serem distribuídas de novo. Durante a pausa o chat deve continuar funcionando. Isso é uma sugestão: a outra saída é o frontend cuidar da pausa usando as mensagens `rodada_encerrada` e `mao_encerrada` (P10).

O contrato prevê as mensagens `truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`, "para animações e avisos". A tela ainda não trata nenhuma delas (P16). Também não existe tela de fim de partida (P9).

### 6.5 Mensagens ao mesmo tempo

- Processe uma mensagem por vez em cada partida, por exemplo com um `asyncio.Lock` por partida. Dois jogadores podem enviar no mesmo instante (os dois parceiros respondendo a um truco, por exemplo). Se o servidor ler, alterar e salvar o estado das duas ao mesmo tempo, uma das alterações se perde.
- Rode o Game com um único processo, sem a opção `--workers`. No exemplo 7.2 a lista de conexões fica na memória do processo. Com mais de um processo, jogadores da mesma partida podem estar conectados a processos diferentes e deixar de receber o estado uns dos outros (P21).

### 6.6 Queda de conexão

- Quando a conexão cai, tire-a da lista e mantenha o estado da partida.
- Se o mesmo jogador conectar de novo (um F5 na página já causa isso), envie o `estado` atual. A tela se redesenha inteira a partir dele (P8).
- Se o mesmo jogador aparecer com duas conexões ao mesmo tempo, por exemplo em duas abas, é preciso decidir qual delas vale (P19).
- O que acontece com a partida enquanto um jogador está fora ainda não foi decidido (P20).

### 6.7 Bots

Os bots conectam no mesmo endereço, recebem o mesmo tipo de `estado` (na visão deles) e enviam as mesmas mensagens da seção 5. Para a tela, um bot é só um jogador com `"bot": true`, que ganha o selo "BOT".

## 7. Exemplo mínimo em FastAPI

Os dois exemplos abaixo foram testados com Python 3.14, FastAPI 0.143 e Uvicorn 0.54, e o estado enviado por eles foi desenhado pela tela real.

Para rodar, salve o código como `main.py` numa pasta de testes e execute, dentro dela:

```bash
pip install fastapi "uvicorn[standard]"
uvicorn main:app --reload --port 8001
```

- `"uvicorn[standard]"` traz junto a biblioteca de WebSocket. Instalando só `uvicorn`, a conexão falha e o log mostra `No supported WebSocket library detected`.
- `main:app` quer dizer: arquivo `main.py`, variável `app`. Se o comando `uvicorn` não for encontrado, use `python -m uvicorn main:app --reload --port 8001`.
- `--reload` reinicia o servidor a cada vez que o arquivo é salvo. Use só durante o desenvolvimento.
- A porta 8001 evita conflito com o frontend, que costuma ser servido na 8000.

### 7.1 Esqueleto: aceita a conexão, envia um estado fixo e imprime o que recebe

```python
# main.py: esqueleto mínimo do serviço Game. Não tem regras de truco:
# aceita a conexão, envia um estado fixo e imprime o que a tela mandar.
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

# Estado fixo, igual ao mock "inicio1x1" da tela (frontend/js/mock/estados.js),
# mais o campo "tipo" que o contrato pede em toda mensagem.
# Em Python, true/false/null do JSON se escrevem True/False/None.
ESTADO_FIXO = {
    "tipo": "estado",
    "partida_id": "p1",
    "formato": "1x1",
    "meu_assento": 0,
    "jogadores": [
        {"assento": 0, "nome": "Ian", "time": "A", "bot": False, "mao": ["3P", "KC", "6O"], "qtd_cartas": 3},
        {"assento": 1, "nome": "Bot 1", "time": "B", "bot": True, "qtd_cartas": 3},
    ],
    "placar": {"A": 0, "B": 0},
    "mao_atual": {
        "numero": 1,
        "pe": 1,
        "vira": "5C",
        "valor": 1,
        "tipo": "normal",
        "truco_pendente": None,
        "ultimo_aumento_time": None,
        "aguardando_decisao_mao_de_onze": False,
        "rodadas": [{"jogadas": [], "vencedor_time": None}],
        "vez_assento": 0,
    },
    "chat": [],
}


# Caminho do contrato: /ws/partidas/{partida_id}?token=<jwt>
# "partida_id" vem do caminho; "token" vem depois do "?" na URL.
@app.websocket("/ws/partidas/{partida_id}")
async def mesa(websocket: WebSocket, partida_id: str, token: str = ""):
    # 1. Aceita a conexão. Sem isso o navegador nunca chega a "conectado".
    #    No serviço real, é aqui que o token é validado e o assento é descoberto.
    await websocket.accept()
    print(f"conectou: partida={partida_id} token={token!r}")

    # 2. Envia o estado completo logo ao conectar: é com ele que a tela se desenha.
    await websocket.send_json(ESTADO_FIXO)

    # 3. Fica esperando as mensagens da tela até a conexão cair.
    try:
        while True:
            texto = await websocket.receive_text()
            try:
                mensagem = json.loads(texto)
            except json.JSONDecodeError:
                # Mensagem de erro no formato do contrato (a tela ainda não mostra erros).
                await websocket.send_json(
                    {"tipo": "erro", "codigo": "json_invalido", "mensagem": "A mensagem não é um JSON válido."}
                )
                continue
            print("recebido:", mensagem)
            # Aqui entrarão as regras: validar a ação, atualizar o estado
            # e enviar o novo estado a todos os jogadores da partida.
    except WebSocketDisconnect:
        # A aba foi fechada, a página foi recarregada ou a rede caiu.
        print(f"desconectou: partida={partida_id}")
```

O que este esqueleto ainda não faz:

- Não valida o token nem descobre o assento. Todo mundo recebe o mesmo estado, como se fosse o assento 0.
- Não guarda as conexões, então não tem como avisar os outros jogadores.
- Não altera o estado. As mensagens só são impressas no terminal.

### 7.2 Próximo passo: vários jogadores, visão filtrada e chat

Este segundo exemplo vai além do esqueleto mínimo. Ele mostra o mecanismo que o serviço inteiro vai repetir: guardar as conexões, mudar o estado e reenviar a cada jogador a visão dele. A única ação tratada é o chat. O assento vem na URL (`?assento=1`) só para dar para testar com duas abas; no serviço real ele sai do token.

```python
# main.py: próximo passo. Vários jogadores na mesma partida, visão filtrada e chat.
# Ainda sem regras de truco e sem validar token: o assento vem na URL só para testar.
import copy
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

# Estado COMPLETO de cada partida, como o servidor guarda (no serviço real fica no Redis).
# Aqui todos os jogadores têm "mao". Este objeto nunca é enviado como está.
PARTIDAS = {
    "p1": {
        "partida_id": "p1",
        "formato": "1x1",
        "jogadores": [
            {"assento": 0, "nome": "Ian", "time": "A", "bot": False, "mao": ["3P", "KC", "6O"]},
            {"assento": 1, "nome": "Ana", "time": "B", "bot": False, "mao": ["2E", "7C", "QP"]},
        ],
        "placar": {"A": 0, "B": 0},
        "mao_atual": {
            "numero": 1,
            "pe": 1,
            "vira": "5C",
            "valor": 1,
            "tipo": "normal",
            "truco_pendente": None,
            "ultimo_aumento_time": None,
            "aguardando_decisao_mao_de_onze": False,
            "rodadas": [{"jogadas": [], "vencedor_time": None}],
            "vez_assento": 0,
        },
        "chat": [],
    }
}

# Conexões abertas de cada partida: {partida_id: {assento: conexão}}
CONEXOES: dict[str, dict[int, WebSocket]] = {}


def visao_do_jogador(estado: dict, assento: int) -> dict:
    """Monta a mensagem "estado" que o jogador deste assento pode receber."""
    visao = copy.deepcopy(estado)  # cópia, para não alterar o estado guardado
    visao["tipo"] = "estado"
    visao["meu_assento"] = assento
    for jogador in visao["jogadores"]:
        jogador["qtd_cartas"] = len(jogador["mao"])
        if jogador["assento"] != assento:
            del jogador["mao"]  # as cartas dos outros nunca saem do servidor
    for rodada in visao["mao_atual"]["rodadas"]:
        for jogada in rodada["jogadas"]:
            if jogada["coberta"]:
                jogada["carta"] = None  # carta coberta vai sem o valor, para todos
    return visao


async def enviar_estado_a_todos(partida_id: str) -> None:
    """Envia o estado atual a todos os conectados, cada um com a sua visão."""
    estado = PARTIDAS[partida_id]
    for assento, conexao in list(CONEXOES.get(partida_id, {}).items()):
        try:
            await conexao.send_json(visao_do_jogador(estado, assento))
        except (WebSocketDisconnect, RuntimeError):
            pass  # este jogador caiu; os outros continuam recebendo


@app.websocket("/ws/partidas/{partida_id}")
async def mesa(websocket: WebSocket, partida_id: str, assento: int = 0):
    await websocket.accept()
    estado = PARTIDAS.get(partida_id)
    if estado is None or assento not in [j["assento"] for j in estado["jogadores"]]:
        # Aceita e fecha com um código próprio, para o cliente saber o motivo.
        await websocket.close(code=4404, reason="partida ou assento inexistente")
        return

    # Guarda a conexão deste assento e envia o estado na visão dele.
    CONEXOES.setdefault(partida_id, {})[assento] = websocket
    await websocket.send_json(visao_do_jogador(estado, assento))

    try:
        while True:
            try:
                mensagem = json.loads(await websocket.receive_text())
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"tipo": "erro", "codigo": "json_invalido", "mensagem": "A mensagem não é um JSON válido."}
                )
                continue
            print(f"assento {assento} enviou:", mensagem)

            # Única ação tratada aqui: o chat. Entra no estado e o estado volta para todos.
            if isinstance(mensagem, dict) and mensagem.get("tipo") == "chat" and mensagem.get("texto"):
                nome = next(j["nome"] for j in estado["jogadores"] if j["assento"] == assento)
                estado["chat"].append({"de": nome, "texto": str(mensagem["texto"])[:200]})
                await enviar_estado_a_todos(partida_id)
    except WebSocketDisconnect:
        # Só remove se a conexão guardada ainda for esta (o jogador pode ter reconectado).
        if CONEXOES[partida_id].get(assento) is websocket:
            del CONEXOES[partida_id][assento]
```

O que ainda falta depois deste passo:

- Validar o token e tirar o assento dele (seção 3.2).
- Guardar o estado no Redis, na chave `partida:{partida_id}`, em vez de um dicionário na memória.
- Processar uma mensagem por vez em cada partida (seção 6.5).
- As regras do jogo (o motor em `services/game/engine`) e as outras mensagens da seção 5.

## 8. Como testar sem a tela integrada

Suba um dos exemplos da seção 7 na porta 8001 antes de começar.

### 8.1 Pelo terminal

O pacote `websockets`, instalado junto com `uvicorn[standard]`, traz um cliente de linha de comando:

```bash
python -m websockets "ws://localhost:8001/ws/partidas/p1?token=teste"
```

As linhas que começam com `<` são o que o servidor enviou. Para enviar, cole uma mensagem depois do `>` e aperte Enter:

```text
{"tipo": "jogar_carta", "carta": "3P", "coberta": false}
{"tipo": "pedir_truco"}
{"tipo": "chat", "texto": "oi"}
```

O que conferir:

1. Ao conectar, chega uma linha com o `estado`.
2. No terminal do servidor aparece `recebido: ...` a cada mensagem enviada.
3. Enviando um texto que não é JSON, chega a mensagem `erro` e a conexão continua aberta.

Com o exemplo 7.2, abra dois terminais, um com `?assento=0` e outro com `?assento=1` no lugar de `?token=teste`. Cada um recebe só a própria `mao`, e um chat enviado por um chega no `estado` dos dois.

### 8.2 Pelo console do navegador

Abra uma página servida em `http://localhost` (a própria mesa, por exemplo), aperte F12 e cole no Console:

```js
const ws = new WebSocket("ws://localhost:8001/ws/partidas/p1?token=teste");
ws.onopen = () => console.log("conectou");
ws.onmessage = (e) => console.log("recebido:", JSON.parse(e.data));
ws.onclose = (e) => console.log("fechou:", e.code, e.reason);
```

Depois de aparecer "conectou", envie mensagens assim:

```js
ws.send(JSON.stringify({ tipo: "jogar_carta", carta: "3P", coberta: false }));
```

Na aba Rede (Network) das ferramentas do navegador, o filtro "WS" lista a conexão. Clicando nela, a aba de mensagens mostra tudo o que entrou e saiu.

A página `/docs` do FastAPI não lista rotas WebSocket. Isso é normal.

### 8.3 Ver o estado do seu servidor desenhado na tela de verdade

Dá para usar a tela real como visualizador, sem alterar nenhum arquivo do frontend:

1. Sirva o frontend: dentro de `frontend/`, rode `python -m http.server 8000`.
2. Abra `http://localhost:8000/mesa.html`.
3. No Console (F12), cole:

```js
const mesa = await import("/js/paginas/mesa.js");
const ws = new WebSocket("ws://localhost:8001/ws/partidas/p1?token=teste");
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  console.log("recebido:", msg);
  if (msg.tipo === "estado") mesa.renderizarMesa(msg);
};
```

A tela passa a desenhar o que o seu servidor mandar. Algumas observações:

- Os cliques continuam só escrevendo `[enviar] {...}` no console, porque a tela ainda não envia pelo WebSocket (P1). Para mandar a mesma mensagem ao servidor, use `ws.send(JSON.stringify({...}))`.
- Se a tela não mudar depois de um `estado`, olhe o console: um erro em vermelho indica campo obrigatório faltando (seção 4.1).
- Não use o seletor de mock no canto da mesa durante o teste. Ele redesenha a tela com um estado falso.
- Se o servidor reiniciar, a conexão cai. Recarregue a página e cole o trecho de novo.
- Com o exemplo 7.2, abra duas abas, uma com `?assento=0` e outra com `?assento=1` na URL do WebSocket. Cada aba mostra a mão do seu assento, e o chat enviado por uma aparece nas duas.

### 8.4 Problemas comuns

| Sintoma | Causa provável |
|---|---|
| A conexão falha na hora, com código 1006 | Caminho errado na URL, servidor parado ou conexão recusada antes do `accept()` |
| Log do Uvicorn com `No supported WebSocket library detected` | O Uvicorn foi instalado sem `[standard]` |
| Conecta, mas a tela não muda e aparece um erro em vermelho no console | Falta um campo obrigatório no `estado` (seção 4.1) |
| Cartas aparecem como imagem quebrada | Código de carta fora do padrão (seção 4.2) |
| Os botões da mão de onze não aparecem | `aguardando_decisao_mao_de_onze` ausente, ou `placar` enviado como texto em vez de número |
| O placar mostra "undefined" | `time` diferente de `"A"` e `"B"`, ou chave faltando em `placar` |

## 9. Pontos em aberto

### Diferenças entre a tela e o documento de contratos

- **P1. A tela ainda não se conecta.** Não há código de WebSocket no frontend: `enviar` só escreve no console, o estado vem dos mocks e `mesa.html` não recebe `partida_id` nem token. Falta o frontend abrir a conexão, chamar `renderizarMesa` a cada `estado` e enviar as mensagens como JSON. Para o servidor, basta cumprir o endereço do contrato.
- **P2. Campo `tipo` na mensagem `estado`.** O contrato diz que toda mensagem tem `tipo`, mas os mocks da tela são o estado puro, sem `tipo`. Este guia assume os campos do estado no primeiro nível, junto com `"tipo": "estado"`. A tela desenha normalmente com esse campo a mais. Confirmar esse formato, em vez de algo como `{"tipo": "estado", "estado": {...}}`.
- **P3. `meu_assento`.** A tela não funciona sem ele, e ele não aparece no documento de contratos, que só mostra o estado guardado no servidor. Incluir no contrato como campo da visão de cada jogador.
- **P4. `aguardando_decisao_mao_de_onze`.** A tela depende dele para mostrar os botões "Jogar a mão" e "Correr" e para bloquear as cartas. O contrato não tem esse campo em `mao_atual`. Incluir no contrato ou combinar outra forma de indicar que a decisão está pendente.
- **P5. Carta coberta.** O contrato diz que as cartas cobertas "aparecem como `"coberta"` sem o valor". A tela espera `"carta": null` com `"coberta": true`. Se o servidor mandar `"carta": "coberta"` sem `"coberta": true`, a tela mostra uma imagem quebrada. Fixar no contrato a forma `null` com `true`.
- **P6. Mão do parceiro na mão de onze.** Pelo contrato, o time com 11 pontos recebe também a mão do parceiro. A tela ignora `mao` nos outros jogadores e continua mostrando versos. Falta o frontend exibir essas cartas. Até lá, enviar `qtd_cartas` em todos os jogadores, mesmo quando `mao` for junto.
- **P7. Chat.** O contrato tem uma mensagem `chat` do servidor para o cliente ("mensagem de outro jogador") e também a lista `chat` dentro do estado. A tela só usa a lista do estado e não mostra a própria mensagem ao enviar. Decidir: ou cada mensagem de chat gera um novo `estado` para todos, o que funciona com a tela de hoje, ou o frontend passa a tratar a mensagem `chat`.
- **P8. Reconexão.** O contrato deixa "reconexão a partida em andamento" fora do escopo, mas um F5 na mesa já é uma reconexão. Como a tela se redesenha inteira a partir de qualquer `estado`, basta o servidor aceitar a nova conexão do mesmo jogador e enviar o estado atual. Decidir se isso entra.

### O que o código da tela assume sem estar escrito

- **P9. Não existe tela de espera nem de fim de partida.** Todo `estado` precisa trazer 2 ou 4 jogadores e uma `mao_atual` preenchida; com menos que isso a tela quebra. Decidir quando a primeira mão é distribuída (na criação da partida ou quando todos conectarem), o que o servidor envia depois que um time chega a 12 e o que a tela mostra nesse momento. O estado guardado tem um campo `status`, que a tela não lê.
- **P10. Rodadas e pausas.** A tela trata o último item de `rodadas` como a rodada atual e só desenha esse item. Por isso o item da nova rodada tem que existir antes da primeira carta dela, e alguém precisa manter a rodada fechada na tela por um instante (seção 6.4). Decidir se a pausa fica no servidor, com um estado intermediário e `"vez_assento": null`, que a tela já aceita, ou no frontend, usando `rodada_encerrada` e `mao_encerrada`.
- **P11. Quem responde pelo time no 2x2.** Com truco pendente, os dois jogadores do time desafiado veem "Aceitar", "Correr" e "Aumentar" habilitados. Na mão de onze, os dois parceiros veem "Jogar a mão" e "Correr". A tela não sabe quem deve responder. Decidir a regra (vale a primeira resposta? só um deles pode?) e o que fazer com a segunda resposta que chegar.
- **P12. `valor` e `ultimo_aumento_time`.** A tela mostra `valor` como "Valendo N", usa `valor` para o texto do botão de truco e usa `ultimo_aumento_time` para bloquear o botão. Confirmar com o motor de regras em que momento cada um muda (no pedido, no aceite, no aumento) e qual `valor` aparece durante a decisão da mão de onze. Sugestão coerente com a tela: `valor` é quanto a mão vale agora, isto é, o que o adversário ganha se alguém correr.
- **P13. Mão de ferro.** A tela só mostra o selo "Mão de ferro" e desabilita o truco. Se a regra adotada for jogar sem ver as próprias cartas, a tela não dá suporte: `mao` precisa ter códigos válidos (um `null` na lista quebra a tela) e `jogar_carta` leva o código da carta. `vira` também é sempre obrigatória. Definir a regra e o que o servidor envia nesse tipo de mão.
- **P14. Limites de nome e de chat.** A cor do autor no chat é escolhida comparando `de` com o `nome` dos jogadores, então nomes repetidos se confundem. A tela não corta nomes longos. A lista `chat` inteira viaja em todo `estado`. O limite de 200 caracteres por mensagem só existe no navegador. Decidir o tamanho máximo do nome, do texto e do histórico.

### Mensagens do contrato que a tela ainda não trata

- **P15. `erro`.** O contrato define os campos `codigo` e `mensagem`, mas não lista os códigos. A tela ainda não mostra erros: a ação recusada simplesmente não tem efeito. Definir a lista de códigos, por exemplo `fora_da_vez`, `carta_invalida`, `acao_invalida` e `json_invalido`.
- **P16. `truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`.** Nenhuma é tratada pela tela. Pelo contrato, servem para animações e avisos. Falta definir os campos exatos (por exemplo, como `rodada_encerrada` representa um empate) e a ordem em relação ao `estado` (antes ou depois dele).

### Decisões do backend

- **P17. Token e assento.** O contrato diz que o token vai em `?token=<jwt>` e que cada serviço valida o JWT sozinho. Não diz quais dados vêm dentro dele (qual campo identifica o usuário) nem como o bot, que usa um "token de serviço", informa em que assento está.
- **P18. Códigos de fechamento.** Não há códigos combinados para recusar uma conexão: token inválido, partida inexistente, usuário fora da partida. A tela ainda não trata o fechamento da conexão.
- **P19. Duas conexões do mesmo jogador.** Decidir o que acontece se o mesmo usuário abrir a mesa em duas abas: a nova substitui a antiga, a nova é recusada ou as duas recebem o estado.
- **P20. Jogador que cai no meio da partida.** Decidir se a partida espera, se um bot assume ou se o time perde. A tela não tem indicador de jogador desconectado nem relógio de tempo de jogada.
- **P21. Um processo ou vários.** Se as conexões ficarem na memória do processo, como no exemplo 7.2, o Game precisa rodar com um único processo. Com mais de um, é preciso distribuir os avisos entre eles, por exemplo com o pub/sub do Redis.
- **P22. Caminho no Nginx.** Confirmar que o gateway repassa `/ws/partidas/...` ao Game sem alterar o caminho, como os exemplos deste guia assumem.
