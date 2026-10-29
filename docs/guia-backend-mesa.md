# Guia do backend: o que a tela da mesa espera do serviço Game

Este guia é para quem vai implementar o serviço Game em Python com FastAPI. Ele explica o que o servidor precisa enviar e receber para a tela da mesa (`frontend/mesa.html`) funcionar conectada a ele, no lugar dos estados falsos (mocks) que ela usa hoje. Não é preciso conhecer FastAPI nem WebSocket: o guia explica o necessário e traz um exemplo pronto para rodar.

**De onde vêm as informações**

- **Código da tela**: `frontend/mesa.html`, `frontend/js/paginas/mesa.js`, `frontend/js/cartas.js` e `frontend/js/mock/estados.js`, na branch `feature/frontend-mesa` em 10/10/2026. Tudo o que o guia afirma que a tela lê, mostra ou envia saiu desse código e foi conferido rodando a tela no navegador com variações do estado. Atualizado em 20/10/2026 (branch `feature/frontend-partida`): a mesa passou a se conectar sozinha, pelo `frontend/js/ws.js`, e ganhou a espera, a reconexão, a tela de fim de partida e a saída.
- **Decisões de protocolo de 20/10/2026**: só as mensagens `estado` e `erro` do servidor, o campo `status`, os códigos de erro e de fechamento, a mão do parceiro na mão de onze, a primeira resposta do time no 2x2, a criação da rodada e a pausa entre as mãos. Elas aparecem como regras no texto e ainda não estão no documento de contratos. Os pontos em aberto que elas fecham estão marcados como resolvidos na seção 9.
- **Documento de requisitos e contratos** (link no [README](../README.md)): usado para o que o código ainda não cobre, como o endereço do WebSocket.
- **Serviço Game de verdade** (`services/game/`, branch `feature/backend-game`, 28/10/2026): o motor de regras e a camada de serviço seguem este guia. O que a implementação decidiu está na seção 10, e os pontos em aberto que ela fechou (P12, P13, P17, P19, P20, P21 e P22) estão marcados como resolvidos na seção 9. Tudo foi conferido com os testes do serviço e com uma partida 1x1 completa na tela real, entre dois usuários do Auth, passando pelo gateway.
- **Serviço de Bots** (`services/bots/`, branch `feature/backend-bots`, 28/10/2026): o bot é um cliente do Game como a tela, e a seção 10.7 registra como ele usa este protocolo. Conferido com os testes do serviço, com partidas 1x1 e 2x2 criadas pelo Lobby e com uma partida 1x1 na tela real, de um usuário do Auth contra um bot.

Quando os dois não batem, ou quando o código depende de algo que não está escrito em lugar nenhum, o texto traz um código como **P3**. Ele aponta para o item correspondente da seção 9, Pontos em aberto.

**Importante:** a tela fala com o Game de verdade. No topo de `frontend/js/ws.js`, a constante `USAR_MOCK_GAME` está em `false` desde a fase 3, junto com o Lobby de verdade, que é quem cria as partidas no Game: a conexão vai para `/ws/partidas/...` no mesmo endereço da página. Com `true`, a mesa volta a conversar com o servidor simulado, que roda dentro do navegador (`frontend/js/mock/servidor-game.js`) e continua no repositório até o fechamento do projeto. O servidor simulado não é o motor de regras: ele existe só para testar a tela. O script `services/game/scripts/partida_de_teste.py` ainda cria uma partida sem passar pelo Lobby, para testes do Game ([README](../README.md)).

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

O pouco que a tela calcula sozinha serve só para exibir: a posição de cada jogador em volta da mesa (a partir de `meu_assento`), "Nós" e "Eles" no placar (a partir do time do jogador), a manilha (valor seguinte ao da `vira`), o texto do botão de truco (a partir de `valor`) e a rodada da próxima carta (a partir de `rodadas`, seção 4.1).

Além da mesa, a tela tem três situações que dependem da conexão e do `status`:

- **Espera.** Até chegar o primeiro `estado`, a tela mostra só "Conectando à partida…".
- **Queda.** Se a conexão cai, a mesa continua na tela com "Conexão perdida. Reconectando…" e os controles desabilitados, e a tela tenta conectar de novo sozinha (seção 6.6).
- **Fim de partida.** Com `"status": "encerrada"`, aparece sobre a mesa o resultado, o placar final e o botão "Voltar ao lobby" (seção 6.4).

## 2. Checklist do que o backend precisa entregar

Na ordem recomendada. Cada etapa termina em algo que dá para ver funcionando. Os itens marcados estão feitos no serviço real (`services/game/`).

**Etapa 1: a tela abre com dados vindos do servidor**

- [x] Projeto FastAPI rodando, com o Uvicorn instalado como `uvicorn[standard]` (seção 7).
- [x] Endpoint WebSocket em `/ws/partidas/{partida_id}` que aceita a conexão (seção 3).
- [x] Ao conectar, envio imediato de uma mensagem `estado` completa. Pode ser fixa (seção 4).
- [x] Leitura das mensagens recebidas como JSON, sem derrubar a conexão quando chegar algo inválido.

**Etapa 2: cada jogador vê a sua própria mesa**

- [x] Validação do token (`?token=<jwt>`) e descoberta do assento do jogador na partida.
- [x] Recusa de token inválido, partida inexistente ou usuário que não está na partida, com os códigos 4401, 4404 e 4403 (seção 3.4).
- [x] Registro das conexões abertas por partida e assento, com remoção ao desconectar.
- [x] Visão filtrada por jogador: `meu_assento`, `mao` só do próprio, `qtd_cartas` de todos, carta coberta sem valor (seção 4.3).
- [x] Envio do `estado` a todos os conectados sempre que ele mudar.
- [x] Chat: a mensagem entra em `chat` com o nome do autor e o `estado` volta para todos.

**Etapa 3: uma partida 1x1 do começo ao fim**

- [x] Partida criada já com a primeira mão distribuída: todo `estado` precisa de `mao_atual` (seção 3.3).
- [x] `jogar_carta` com validação e atualização de `rodadas`, `qtd_cartas` e `vez_assento`.
- [x] Fim de rodada (`vencedor_time` e `vencedor_assento`), com a rodada seguinte criada só na primeira carta dela (seção 6.4).
- [x] Fim de mão: `placar` atualizado e, depois de uns 2 segundos, nova mão (`numero`, `pe`, `vira`, cartas e `valor` inicial).
- [x] `pedir_truco` e `responder_truco`, mantendo `valor`, `truco_pendente` e `ultimo_aumento_time`.
- [x] Ação inválida não muda o estado e gera `erro` só para quem enviou, com um dos códigos da seção 6.2.
- [x] Fim de partida aos 12 pontos: `"status": "encerrada"` e `vencedor_time` (seção 6.4).

**Etapa 4: comportamento completo**

- [x] 2x2: quatro assentos, times alternados, resposta ao truco pelo time, valendo a primeira (seção 5.3).
- [x] Carta coberta a partir da segunda rodada.
- [x] Mão de onze: `tipo`, `aguardando_decisao_mao_de_onze` e `decidir_mao_de_onze` (P4), com a mão do parceiro para o time com 11 (seção 4.3).
- [x] Mão de ferro (P13).
- [x] Bots conectando como clientes comuns: o serviço de Bots (seção 10.7), com o token da seção 10.5.
- [x] Volta do jogador depois de uma queda: a nova conexão recebe o estado atual (seção 6.6; P20).

## 3. Conexão WebSocket

### 3.1 O que é e por que usar aqui

Numa requisição HTTP comum, o navegador pergunta e o servidor responde. O servidor não consegue avisar o navegador por conta própria. No truco isso não basta: quando um jogador joga uma carta, os outros precisam ficar sabendo na hora, sem perguntar.

O WebSocket resolve isso. A conexão começa como uma requisição HTTP normal (o "aperto de mão") e depois fica aberta. Enquanto ela estiver aberta, os dois lados podem enviar mensagens quando quiserem. Aqui cada mensagem é um texto em JSON. Cada jogador mantém uma conexão aberta por partida: é por ela que chegam os estados e saem as jogadas.

### 3.2 Endereço

Pelo documento de contratos, a conexão é em:

```text
/ws/partidas/{partida_id}?token=<jwt>
```

Quem atende é o Game. O gateway (Nginx) encaminha para ele tudo o que começa com `/ws/`, com o caminho e a query string inteiros (P22, resolvido).

| Situação | URL usada pelo navegador |
|---|---|
| Tudo rodando pelo Docker Compose | `ws://localhost/ws/partidas/<partida_id>?token=<jwt>` |
| Game rodando sozinho, como no exemplo da seção 7 | `ws://localhost:8001/ws/partidas/<partida_id>?token=<jwt>` |

`ws://` está para o WebSocket como `http://` está para as páginas. Com HTTPS, usa-se `wss://`.

Como chegam os dois dados:

- **`partida_id`** vem no caminho da URL. É o id devolvido por `POST /api/lobby/salas/{id}/iniciar`. O Lobby consegue esse id chamando `POST /interno/partidas` no Game.
- **`token`** vem depois do `?` (a query string). É o JWT recebido no login. Ele vai na URL porque o navegador não permite colocar cabeçalhos como `Authorization` numa conexão WebSocket.

Com o token, o Game descobre quem é o usuário sem consultar o Auth. Com a lista de assentos recebida na criação da partida (`usuario_id`, `nome`, `bot`), descobre em que assento ele está. Esse assento é o `meu_assento` da mensagem `estado` (P17, resolvido: o `sub` do token é comparado com o `usuario_id` de cada assento; os bots usam um token próprio, seção 10.5).

Um detalhe para saber: o token aparece inteiro nos logs de acesso do Uvicorn e do Nginx, porque faz parte da URL.

### 3.3 O que o servidor faz ao receber uma conexão

1. Lê o `partida_id` do caminho e o `token` da query string.
2. Valida o token, localiza a partida e descobre o assento do usuário nela. Se algo falhar, encerra a conexão (seção 3.4).
3. Aceita a conexão e a guarda, associada à partida e ao assento.
4. **Envia na hora a mensagem `estado`** na visão daquele jogador. Sem ela a tela não tem o que desenhar.
5. Fica lendo as mensagens daquele jogador até a conexão cair.
6. Quando cair, tira a conexão da lista. O estado da partida continua guardado.

Até o primeiro `estado`, a tela mostra "Conectando à partida…". Ela não tem uma tela de "aguardando jogadores": todo `estado` precisa trazer os 2 ou 4 jogadores e uma `mao_atual` preenchida, por isso a partida já nasce com a primeira mão distribuída. O fim da partida vem no próprio `estado`, pelo `status` (seção 6.4).

### 3.4 Como recusar uma conexão

Há duas formas, e o navegador enxerga cada uma de um jeito:

| O servidor faz | O navegador recebe |
|---|---|
| `close()` sem ter chamado `accept()` | Falha de conexão com código 1006 e sem motivo. O servidor responde HTTP 403. |
| `accept()` e depois `close(code=4401, reason="token inválido")` | Fechamento com o código 4401 e o motivo informado. |

Para recusar, use sempre a segunda forma, com um destes códigos:

| Código | Quando | O que a tela faz |
|---|---|---|
| 4401 | Token ausente, inválido ou vencido | Apaga a sessão e volta para o login, que mostra "Sua sessão expirou. Entre novamente.", como num 401 das rotas HTTP |
| 4403 | O usuário do token não está na partida | Mostra "Você não faz parte desta partida." e volta para o lobby em 5 segundos |
| 4404 | Não existe partida com esse `partida_id` | Mostra "Esta partida não existe." e volta para o lobby em 5 segundos |
| 4409 | O mesmo jogador abriu outra conexão com a partida (outra aba, por exemplo), e esta, a mais antiga, foi substituída (P19) | Mostra "Esta partida foi aberta em outra aba." e volta para o lobby em 5 segundos |
| Qualquer outro, inclusive o 1006 | Queda | Tenta conectar de novo, sozinha (seção 6.6) |

**O servidor precisa chamar `accept()` antes de fechar com 4401, 4403 ou 4404.** Uma recusa sem `accept()` chega à tela como queda (1006): ela não sai da partida e fica tentando reconectar indefinidamente. Um caminho errado na URL também aparece como 403 e 1006. Se a conexão "falha sem motivo", confira primeiro o caminho.

### 3.5 Atrás do Docker e do Nginx

- Dentro do Docker, suba o Uvicorn com `--host 0.0.0.0`. O padrão é `127.0.0.1`, que só aceita conexões vindas de dentro do próprio contêiner.
- O Nginx precisa repassar o pedido de troca de protocolo no bloco do `/ws`, senão o aperto de mão falha. O trecho abaixo é o essencial do `gateway/nginx.conf`, testado com o Game: lá, o `upstream game` aponta para `game:8000`, e o `map` troca o cabeçalho `Connection` por `upgrade` só quando o navegador pede o WebSocket.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

location /ws/ {
    proxy_pass http://game;   # sem barra no fim: o caminho chega inteiro ao Game
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_read_timeout 120s;
}
```

- O Nginx fecha conexões que ficam 60 segundos sem receber dados do servidor. O Uvicorn envia um sinal de vida (ping) a cada 20 segundos por padrão, o que mantém a conexão aberta. Não é preciso criar mensagens de "ping" no protocolo.

## 4. A mensagem `estado`

É a única mensagem que a tela usa para se desenhar. O contrato a descreve assim: "a mensagem `estado` é a fonte da verdade para a tela: o frontend sempre redesenha a mesa a partir dela". O servidor só manda dois tipos de mensagem: o `estado` e o `erro` (seção 6.2).

### 4.1 Campos

A mensagem é um objeto JSON com `"tipo": "estado"` e os campos abaixo, todos no primeiro nível.

Como ler a coluna **Obrigatório**: *Sim* quer dizer que, sem o campo, a tela quebra (aparece um erro no console do navegador e ela fica parada no desenho anterior) ou mostra informação errada. *Não* quer dizer que a tela funciona sem ele; o que ela assume na ausência está na última coluna.

**Primeiro nível**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `tipo` | texto | **Sim** | Sempre `"estado"`. É ele que separa o `estado` da mensagem `erro`: sem ele, a tela ignora a mensagem. |
| `status` | texto | **Sim** | `"em_andamento"` ou `"encerrada"`. Com `"encerrada"`, a tela mostra o fim de partida sobre a mesa e desabilita os controles de jogo; o chat continua. Ausente, a tela trata como `"em_andamento"`. |
| `vencedor_time` | texto | Só com `"encerrada"` | `"A"` ou `"B"`. A tela compara com o time do jogador e escreve "Você venceu!" ou "Você perdeu" no 1x1, "Vocês venceram!" ou "Vocês perderam" no 2x2. |
| `meu_assento` | inteiro | **Sim** | Assento do jogador que recebe a mensagem. Tem que ser igual ao `assento` de um dos `jogadores`, senão a tela quebra. Não existe no estado guardado no servidor: é acrescentado na visão de cada jogador. Faz parte do protocolo (P3). |
| `jogadores` | lista | **Sim** | Exatamente 2 itens (1x1) ou 4 itens (2x2). Com outra quantidade a tela quebra. A ordem da lista não importa: vale o campo `assento`. |
| `placar` | objeto | **Sim** | `{"A": 4, "B": 7}`. As duas chaves, com números. |
| `mao_atual` | objeto | **Sim** | Nunca `null`, nem depois do fim da partida (seção 6.4). |
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
| `mao` | lista de cartas | No item do próprio jogador e, na mão de onze, no do parceiro (seção 4.3) | Códigos das cartas que ele tem na mão (seção 4.2). Ausente equivale a mão vazia. No item de outro jogador, a tela mostra essas cartas abertas e menores, junto ao jogador, no lugar dos versos. |
| `qtd_cartas` | inteiro | **Sim** nos outros jogadores | Quantidade de versos que a tela desenha quando o item não traz `mao`. No item do próprio jogador a tela não lê: usa o tamanho de `mao`. |

A tela posiciona cada jogador pela diferença entre o `assento` dele e o `meu_assento`: o próprio jogador fica embaixo, o assento seguinte à direita, depois em cima e por fim à esquerda (no 1x1, embaixo e em cima). Pelo contrato, a ordem de jogo segue a numeração dos assentos, então na tela a vez anda no sentido anti-horário. No 2x2 os assentos 0 e 2 são o time A e os assentos 1 e 3 o time B, por isso o parceiro aparece em frente. A tela não deduz o time pelo assento: ela lê `time`.

**`mao_atual`**

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `numero` | inteiro | **Sim** | Aparece no placar como "Mão 6". |
| `vira` | carta | **Sim** | Sempre um código de carta válido. `null` quebra a tela (P13). A manilha é calculada pela tela. |
| `valor` | inteiro | **Sim** | 1, 3, 6, 9 ou 12. Aparece como "Valendo 3" e define o texto do botão de truco: 1 mostra "Truco", 3 "Seis", 6 "Nove", 9 "Doze" (P12). |
| `tipo` | texto | **Sim** | `"normal"`, `"mao_de_onze"` ou `"mao_de_ferro"`. Os dois últimos mostram um selo no placar. Qualquer valor diferente de `"normal"` desabilita o botão de truco. |
| `rodadas` | lista | **Sim** | `[]` no começo da mão: cada rodada só entra na lista com a primeira carta dela (seção 6.4). Formato mais abaixo. |
| `vez_assento` | inteiro ou `null` | **Sim** | Assento de quem joga agora. Com `null` (ou sem o campo) ninguém fica destacado, nenhuma carta fica clicável e a barra de ações mostra "Fim da mão.". É assim entre as mãos e depois do fim da partida (seção 6.4). |
| `truco_pendente` | objeto ou `null` | Não | `null` ou ausente quando não há pedido em aberto. Formato mais abaixo. |
| `ultimo_aumento_time` | texto ou `null` | Não | `"A"`, `"B"` ou `null`. O time indicado fica com o botão de truco desabilitado (P12). |
| `aguardando_decisao_mao_de_onze` | booleano | Não | Ausente equivale a `false`. Tem que ser `true` para os botões da mão de onze aparecerem. Faz parte do protocolo (P4). |
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
| `vencedor_assento` | inteiro ou `null` | Não | Assento de quem jogou a carta vencedora. `null` enquanto a rodada está em andamento e no empate. A tela destaca só a carta desse assento; ausente, nenhuma carta fica em destaque. Se os dois parceiros jogam a carta mais forte do time com a mesma força, vale a jogada primeiro, que também abre a rodada seguinte (seção 10.2). |

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

- No centro da mesa aparecem **só as cartas do último item** da lista. Como a rodada nova só é criada com a primeira carta dela, a rodada que acabou de terminar continua na mesa até alguém abrir a seguinte.
- A tela calcula a rodada da próxima carta: se a lista está vazia ou o último item já tem `vencedor_time`, é a rodada seguinte; senão, é a do último item.
- Os três marcadores de rodada usam o `vencedor_time` das três primeiras posições: cor do time, cinza para `"empate"`, vazio para `null`. A rodada da próxima carta ganha um contorno de "rodada atual", se alguém tem a vez.
- Na rodada decidida que continua na mesa, a carta do `vencedor_assento` sobe um pouco e ganha um contorno na cor do time. No 2x2, é só a carta vencedora, não as duas do time.
- A opção "Jogar coberta" fica disponível quando a próxima carta é da segunda rodada em diante. Marcada, as cartas da mão aparecem com a cor do verso por cima e o aviso "Coberta".

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
2. **`mao`** só aparece no item do próprio jogador, fora a exceção da regra 6. Nos demais itens ela não é enviada: a tela mostraria essas cartas abertas, e elas chegariam ao navegador, onde qualquer um poderia vê-las nas ferramentas de desenvolvedor.
3. **`qtd_cartas`** vai em todos os itens de `jogadores`.
4. **Carta coberta** vai como `"carta": null` e `"coberta": true`, para todos os jogadores, inclusive quem jogou, e em todas as rodadas da lista (não só na última). A tela decide pelo `coberta`. Se o código da carta for junto, ela mostra o verso do mesmo jeito, mas a carta fica visível nas ferramentas do navegador (P5).
5. Nada além do que está nas tabelas da seção 4.1 precisa sair do servidor (baralho, `usuario_id`, `sala_id`). Campos a mais são ignorados pela tela.
6. Na mão de onze (`"tipo": "mao_de_onze"`), no 2x2, cada jogador do time com 11 pontos recebe também a `mao` no item do parceiro, com o `qtd_cartas` junto, como em todos os itens. A tela mostra essas cartas abertas junto ao parceiro. O time adversário continua recebendo só `qtd_cartas`.

O exemplo 7.2 tem uma função `visao_do_jogador` que aplica as regras 1 a 4.

### 4.4 Campos que liberam cada ação

Lembrando: isso só define o que fica clicável. O servidor valida tudo de novo.

| Controle na tela | Fica habilitado quando |
|---|---|
| Cartas da mão | `vez_assento` é igual a `meu_assento`, `truco_pendente` é `null` e `aguardando_decisao_mao_de_onze` não é `true` |
| Botão de truco ("Truco", "Seis", "Nove" ou "Doze") | É a vez do jogador, `truco_pendente` é `null`, `valor` é menor que 12, `ultimo_aumento_time` não é o time dele e `tipo` é `"normal"` |
| "Aceitar" e "Correr" | Existe `truco_pendente` e `pedido_por_time` não é o time do jogador. No 2x2, vale para os dois jogadores do time |
| "Aumentar" | O mesmo de "Aceitar", e `valor_proposto` menor que 12 |
| Caixa "Jogar coberta" | A próxima carta é da segunda rodada em diante (seção 4.1) |
| "Jogar a mão" e "Correr" da mão de onze | Só aparecem quando `aguardando_decisao_mao_de_onze` é `true` e o time do jogador tem exatamente 11 em `placar`. No 2x2, para os dois parceiros |
| Chat | Com a conexão aberta, inclusive depois do fim da partida |

Além disso, com a conexão caída ou com `"status": "encerrada"`, todos os controles de jogo ficam desabilitados.

A barra de ações também mostra uma frase que depende do estado. Ela ajuda a conferir se o servidor mandou o que você esperava:

| Situação no estado | Frase mostrada |
|---|---|
| Conexão caída, tentando de novo | "Conexão perdida. Reconectando…" |
| Mensagem `erro` recebida nos últimos 4 segundos | A `mensagem` do erro |
| `"status": "encerrada"` | "Fim de partida." |
| Truco pendente pedido pelo outro time | "Time adversário pediu Seis!" |
| Truco pendente pedido pelo time do jogador | "Aguardando o adversário responder ao pedido de Seis…" |
| Decisão de mão de onze pendente, time do jogador com 11 | "Mão de onze: seu time decide se joga ou corre." |
| Decisão de mão de onze pendente, time adversário com 11 | "Aguardando o adversário decidir a mão de onze…" |
| Vez do jogador | "Sua vez de jogar." |
| Vez de outro jogador | "Vez de João." |
| `vez_assento` é `null` | "Fim da mão." |

### 4.5 Exemplo completo

Partida 2x2 na segunda rodada, enviada ao jogador do assento 0. A primeira rodada foi vencida pelo time A, com o valete de paus da Maria (a vira é a dama, então o valete é a manilha); a Maria abriu a segunda com uma carta coberta e agora é a vez do João.

```json
{
  "tipo": "estado",
  "partida_id": "p1",
  "formato": "2x2",
  "status": "em_andamento",
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
        "vencedor_time": "A",
        "vencedor_assento": 2
      },
      {
        "jogadas": [
          {"assento": 2, "carta": null, "coberta": true}
        ],
        "vencedor_time": null,
        "vencedor_assento": null
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

A função `enviar` manda cada mensagem pela conexão, como um texto JSON. Com a conexão caída, os controles ficam desabilitados e nada é enviado. Só nos estados falsos da tela (`mesa.html` sem `?partida=`), que não têm conexão, ela escreve a mensagem no console do navegador, no formato `[enviar] {...}`.

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
- `coberta`: sempre presente. Só vai `true` quando a caixa "Jogar coberta" está marcada e a carta é da segunda rodada em diante. O Game aceita a mensagem sem o campo, como `false`; com um valor que não é booleano, responde `acao_invalida`.

O que o servidor faz:

1. Confere que é a vez do jogador, que não há truco nem decisão de mão de onze pendente, que a carta está na mão dele e que `coberta` só vem `true` a partir da segunda rodada.
2. Tira a carta da mão e acrescenta a jogada ao final de `jogadas` da rodada atual. Se a lista está vazia ou a última rodada já tem vencedor, cria antes a rodada nova, com esta carta como a primeira jogada. Depois passa `vez_assento` para o próximo.
3. Se a rodada terminou, preenche `vencedor_time` e `vencedor_assento` e passa `vez_assento` para quem abre a próxima, ou encerra a mão (seção 6.4).
4. Envia o novo `estado` a todos.

Um clique duplo pode gerar duas mensagens seguidas. A segunda deve ser recusada como qualquer jogada fora da vez (`fora_da_vez`).

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

No 2x2, os **dois** jogadores do time desafiado veem os botões habilitados, e qualquer um deles pode responder. Vale a primeira resposta que chegar: a segunda já não encontra pedido pendente e recebe `erro` com `acao_invalida`.

O que o servidor faz:

1. Confere que existe pedido pendente e que quem respondeu é do time desafiado.
2. Aplica a resposta:
   - `aceitar`: `valor` passa a ser o `valor_proposto`, `truco_pendente` volta a `null` e `ultimo_aumento_time` recebe o time que pediu.
   - `correr`: a mão termina, o time que pediu ganha os pontos de `valor`, o `placar` é atualizado e começa a próxima mão.
   - `aumentar`: o time que respondeu faz um novo pedido, um nível acima. `truco_pendente` passa a ter esse time em `pedido_por_time` e o novo `valor_proposto`.
3. Envia o novo `estado` a todos.

`valor` é sempre quanto a mão vale agora, isto é, o que o adversário ganha se alguém correr. Ele não muda no pedido: muda no aceite e no aumento (que aceita o pedido anterior antes de fazer o seguinte). `ultimo_aumento_time` recebe o time cujo pedido foi aceito, e esse time não pede de novo até o adversário pedir (P12, resolvido). Exemplo: o time A pede truco (`valor` 1); o B aumenta para seis (`valor` passa a 3, `ultimo_aumento_time` "A"); se o A correr, o B ganha 3.

### 5.4 `decidir_mao_de_onze`

```json
{"tipo": "decidir_mao_de_onze", "jogar": true}
```

- `jogar`: `true` no botão "Jogar a mão", `false` no botão "Correr".

Enquanto `aguardando_decisao_mao_de_onze` é `true`, a tela bloqueia as cartas de todos os jogadores. No 2x2, os dois parceiros do time com 11 pontos veem os botões, e vale a primeira decisão, como no truco.

O que o servidor faz:

1. Confere que há decisão pendente e que quem enviou é do time com 11 pontos.
2. Com `true`: `aguardando_decisao_mao_de_onze` passa a `false`, `valor` passa a 3 e a mão segue, sem truco. Com `false`: a mão termina, o outro time ganha 1 ponto (o `valor` mostrado durante a decisão) e começa a próxima mão.
3. Envia o novo `estado` a todos.

### 5.5 `chat`

```json
{"tipo": "chat", "texto": "boa, parceira"}
```

- `texto`: o que o jogador digitou, sem espaços no começo e no fim. A tela não envia texto vazio e o campo aceita até 200 caracteres. O servidor confere de novo.

O que o servidor faz:

1. Confere que `texto` é um texto não vazio e corta em 200 caracteres.
2. Acrescenta `{"de": "<nome do jogador>", "texto": "..."}` ao final de `chat` e guarda só as 50 últimas mensagens.
3. Envia o novo `estado` a todos, inclusive a quem escreveu. A tela só mostra a própria mensagem quando ela volta no `estado`.

## 6. Comportamentos esperados

### 6.1 Depois de cada ação válida

- Atualizar o estado, salvar e enviar `estado` a **todos** os conectados da partida, cada um com a sua visão (seção 4.3). Isso inclui quem fez a ação.
- Enviar sempre o estado inteiro.

### 6.2 Ações inválidas

- Não alterar o estado e não avisar os outros jogadores.
- Responder só a quem enviou, com a mensagem `erro`:

```json
{"tipo": "erro", "codigo": "fora_da_vez", "mensagem": "Não é a sua vez."}
```

- Usar um destes códigos. A divisão entre eles é a do servidor simulado da tela (`frontend/js/mock/servidor-game.js`):

| `codigo` | Quando | Exemplo de `mensagem` |
|---|---|---|
| `fora_da_vez` | Jogar uma carta ou pedir truco fora da vez | "Não é a sua vez." |
| `carta_invalida` | Carta que não está na mão do jogador, ou coberta na primeira rodada | "Você não tem essa carta." |
| `nao_autorizado` | Ação que este jogador não pode fazer: responder ao truco do próprio time, decidir a mão de onze sem ser do time com 11 | "Quem responde ao truco é o time adversário." |
| `acao_invalida` | Ação que não cabe agora (nenhum pedido para responder, truco bloqueado, mão de onze já decidida, pausa entre as mãos, partida encerrada) ou mensagem malformada | "Não há pedido de truco para responder." |

- Não fechar a conexão por causa de uma jogada inválida.
- Tratar do mesmo jeito, com `acao_invalida`, as mensagens malformadas: texto que não é JSON, objeto sem `tipo`, `tipo` desconhecido, campo faltando. O servidor nunca pode cair por causa de uma mensagem.

A tela mostra a `mensagem` por 4 segundos na barra de ações, no lugar da frase de situação, sem bloquear a mesa. Escreva para o jogador: em português, curta, sem nomes internos. O `codigo` a tela não lê. Como ela só muda quando chega um `estado`, a ação recusada não tem nenhum outro efeito na tela.

### 6.3 Chat

- O chat volta para a tela dentro da lista `chat` do `estado`. A tela redesenha a lista inteira e rola até a última mensagem.
- Não existe mensagem `chat` separada, do servidor para o cliente: tudo vem no `estado`.
- A lista leva só as 50 últimas mensagens, cada uma com até 200 caracteres.

### 6.4 Fim de rodada, de mão e de partida

A tela não tem animação nem pausa própria. Ela mostra o último `estado` recebido e, no centro, só a última rodada da lista. Por isso a ordem e o ritmo dos estados ficam com o servidor:

1. **Fim de rodada.** O estado sai com a rodada completa, `vencedor_time` e `vencedor_assento` preenchidos e `vez_assento` em quem abre a próxima. A rodada nova **não** entra em `rodadas` agora: ela só é criada quando a primeira carta dela for jogada (seção 5.1). Assim a rodada encerrada continua na mesa até alguém abrir a seguinte, sem pausa nenhuma.
2. **Fim de mão.** O estado sai com a última rodada completa, o `placar` atualizado e `"vez_assento": null` (a tela mostra "Fim da mão."). O servidor espera uns 2 segundos e só então envia a mão nova: `numero`, `pe`, `vira`, cartas, `valor` inicial e `"rodadas": []`. Use `await asyncio.sleep(2)`. Nunca use `time.sleep`, que trava o servidor inteiro, para todas as partidas. Durante a pausa o chat continua funcionando, e as outras ações recebem `erro`.
3. **Fim de partida.** Quando um time chega a 12, o estado sai na hora com `"status": "encerrada"`, `vencedor_time` e a última mão em `mao_atual`, com `"vez_assento": null`. Não há mão nova. A tela mostra sobre a mesa o resultado, o placar final e o botão "Voltar ao lobby". Daí em diante só o chat vale, e quem conectar recebe o mesmo estado encerrado.

Não existem mensagens próprias para esses momentos. As que o documento de contratos previa "para animações e avisos" (`truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`) deixaram de existir: tudo vem no `estado`.

### 6.5 Mensagens ao mesmo tempo

- Processe uma mensagem por vez em cada partida, por exemplo com um `asyncio.Lock` por partida. Dois jogadores podem enviar no mesmo instante (os dois parceiros respondendo a um truco, por exemplo). Se o servidor ler, alterar e salvar o estado das duas ao mesmo tempo, uma das alterações se perde.
- Rode o Game com um único processo, sem a opção `--workers`. No exemplo 7.2 a lista de conexões fica na memória do processo. Com mais de um processo, jogadores da mesma partida podem estar conectados a processos diferentes e deixar de receber o estado uns dos outros (P21, resolvido: o serviço real roda num processo só, num container só, e a limitação está documentada em `services/game/app/partidas.py`).

### 6.6 Queda de conexão

- Quando a conexão cai, tire-a da lista e mantenha o estado da partida.
- A tela tenta conectar de novo sozinha, esperando 1, 2, 4 e 8 segundos entre as tentativas e, daí em diante, 10 segundos. Enquanto isso, a mesa continua na tela com "Conexão perdida. Reconectando…". Depois de 4401, 4403 ou 4404 ela não tenta de novo (seção 3.4).
- Quando o mesmo jogador conectar de novo (um F5 na página também é uma volta), envie o `estado` atual, como em qualquer conexão. A tela se redesenha inteira a partir dele.
- Se o mesmo jogador aparecer com duas conexões ao mesmo tempo, por exemplo em duas abas, vale a mais recente: ela recebe o estado e passa a jogar, e a anterior é fechada com 4409. A tela trata o 4409 como recusa (seção 3.4) e não reconecta, senão as duas abas ficariam se derrubando (P19, resolvido).
- Enquanto um jogador está fora, a partida espera por ele, sem prazo: ninguém joga no lugar dele e o time não perde por isso. Os outros continuam conectados, recebem o estado e podem conversar no chat (P20, resolvido por decisão do grupo).

### 6.7 Bots

Os bots conectam no mesmo endereço, recebem o mesmo tipo de `estado` (na visão deles) e enviam as mesmas mensagens da seção 5. Para a tela, um bot é só um jogador com `"bot": true`, que ganha o selo "BOT". O token que o bot usa e como o Game o confere estão na seção 10.5; o serviço que joga pelos bots, na seção 10.7. O Game não trata os bots de um jeito diferente: as mesmas regras, a mesma ordem e as mesmas recusas valem para eles.

## 7. Exemplo mínimo em FastAPI

O serviço real, em `services/game/`, faz tudo o que estes exemplos deixam de fora (seção 10). Eles continuam aqui por serem o jeito mais curto de entender o mecanismo.

Os dois exemplos abaixo foram testados com Python 3.14, FastAPI 0.143 e Uvicorn 0.54, e o estado enviado por eles foi desenhado pela tela real. Depois das decisões de 20/10/2026 eles foram atualizados e testados de novo, com FastAPI 0.153: o 7.2 com a tela conectada a ele (seção 8.3), e o 7.1 por um cliente WebSocket.

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
    "status": "em_andamento",
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
        "rodadas": [],  # a rodada só entra na lista com a primeira carta dela
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
                # Mensagem de erro do protocolo: a tela mostra a "mensagem" na barra de ações.
                await websocket.send_json(
                    {"tipo": "erro", "codigo": "acao_invalida", "mensagem": "A mensagem não é um JSON válido."}
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
        "status": "em_andamento",
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
            "rodadas": [],
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
    # Aceita e fecha com o código do protocolo, para a tela saber o motivo (seção 3.4).
    if estado is None:
        await websocket.close(code=4404, reason="partida inexistente")
        return
    if assento not in [j["assento"] for j in estado["jogadores"]]:
        await websocket.close(code=4403, reason="não pertence à partida")
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
                    {"tipo": "erro", "codigo": "acao_invalida", "mensagem": "A mensagem não é um JSON válido."}
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

**Com a tela conectada ao seu servidor.** A mesa conecta sozinha em `ws://<endereço da página>/ws/partidas/<partida_id>?token=<token do login>`. Por isso a página e o Game precisam estar no mesmo endereço, como vão estar atrás do gateway. Enquanto não há Nginx, o próprio Game pode entregar os arquivos da tela:

1. Acrescente ao fim do `main.py` (do exemplo 7.1 ou do 7.2), depois da rota do WebSocket:

```python
# SÓ PARA TESTE LOCAL, enquanto não há Nginx: o próprio Game entrega os arquivos da tela,
# para a página e o WebSocket ficarem no mesmo endereço. Fica depois da rota /ws/partidas,
# para não responder no lugar dela.
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="caminho/para/o/repositorio/frontend", html=True), name="tela")
```

2. Em `frontend/js/ws.js`, confira que `USAR_MOCK_GAME` está em `false` (o padrão desde a fase 3).
3. Suba o servidor (`uvicorn main:app --reload --port 8001`), abra `http://localhost:8001/index.html` e entre. O login pode continuar no mock: os exemplos da seção 7 não conferem o token.
4. Abra `http://localhost:8001/mesa.html?partida=p1`. A mesa desenha o `estado` do servidor, e os cliques saem pela conexão. Com o exemplo 7.2, o chat vai e volta; as outras mensagens só aparecem no terminal do servidor. O assento, nesse exemplo, vem de `?assento=` na URL do WebSocket, que a tela não manda: pela tela você é sempre o assento 0.
5. Para ver a reconexão, pare o servidor e suba de novo: a mesa mostra "Conexão perdida. Reconectando…" e volta sozinha. Com `?partida=` de uma partida que não existe, o exemplo 7.2 fecha com 4404, e a tela mostra "Esta partida não existe." e volta para o lobby.

**Sem mexer em nenhum arquivo.** A mesa aberta sem `?partida=` não conecta (mostra os estados falsos), e dá para usá-la como visualizador pelo console:

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

- Os cliques só escrevem `[enviar] {...}` no console, porque a página aberta assim não tem conexão. Para mandar a mesma mensagem ao servidor, use `ws.send(JSON.stringify({...}))`.
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
| A mesa fica em "Conectando à partida…" | O servidor aceitou a conexão, mas não enviou o `estado` (seção 3.3), ou ele veio sem `"tipo": "estado"` |
| A mesa fica em "Não foi possível conectar. Tentando de novo…" | Servidor parado, endereço diferente do da página (seção 8.3) ou recusa sem `accept()` (seção 3.4) |
| A mesa mostra "Esta partida não existe." e volta para o lobby | Fechamento 4404: o `partida_id` da URL não existe no servidor |
| A mesa volta para o login logo ao abrir | Fechamento 4401: o token foi recusado |
| A rodada encerrada some da mesa antes de alguém jogar | O servidor criou a rodada nova antes da primeira carta dela (seção 6.4) |

## 9. Pontos em aberto

### Diferenças entre a tela e o documento de contratos

- **P1. A tela ainda não se conecta. Resolvido.** A mesa abre como `mesa.html?partida={partida_id}` e conecta pelo `frontend/js/ws.js`, com o token do login. Ela chama `renderizarMesa` a cada `estado` e envia as mensagens como JSON. Hoje a conexão vai para o servidor simulado; com `USAR_MOCK_GAME = false`, para o Game (seção 8.3).
- **P2. Campo `tipo` na mensagem `estado`. Resolvido.** Os campos do estado vão no primeiro nível, junto com `"tipo": "estado"`.
- **P3. `meu_assento`. Resolvido.** Faz parte do protocolo: o `estado` enviado a cada jogador traz `meu_assento`, acrescentado na visão dele. Não existe no estado guardado no servidor (seção 4.1).
- **P4. `aguardando_decisao_mao_de_onze`. Resolvido.** Faz parte do protocolo: `mao_atual` traz o campo, `true` enquanto o time com 11 não decide. A tela o usa para mostrar os botões "Jogar a mão" e "Correr" e para bloquear as cartas (seção 4.1).
- **P5. Carta coberta. Resolvido.** Faz parte do protocolo: a carta jogada coberta vem como `{"carta": null, "coberta": true}`, para todos os jogadores. A forma `"carta": "coberta"`, citada no documento de contratos, não vale: sem `"coberta": true`, a tela mostraria uma imagem quebrada (seção 4.3).
- **P6. Mão do parceiro na mão de onze. Resolvido.** No 2x2, o time com 11 pontos recebe a `mao` também no item do parceiro, com o `qtd_cartas` junto, e a tela mostra essas cartas abertas e menores junto ao parceiro (seção 4.3).
- **P7. Chat. Resolvido.** Não existe mensagem `chat` separada: cada mensagem entra na lista `chat` do `estado`, que volta para todos com as 50 últimas (seção 6.3).
- **P8. Reconexão. Resolvido.** Ao conectar, o servidor sempre envia o estado atual, e isso vale como reconexão, inclusive depois de um F5. A tela reconecta sozinha quando a conexão cai (seção 6.6).

### O que o código da tela assume sem estar escrito

- **P9. Não existe tela de espera nem de fim de partida. Resolvido.** A tela mostra "Conectando à partida…" até o primeiro `estado` e a tela de fim de partida quando `status` é `"encerrada"`, com `vencedor_time` (seções 3.3 e 6.4). Como todo `estado` continua precisando de `mao_atual`, a partida já nasce com a primeira mão distribuída.
- **P10. Rodadas e pausas. Resolvido.** A rodada nova só é criada com a primeira carta dela, então a rodada encerrada continua na mesa sem pausa nenhuma, e a tela calcula a rodada da próxima carta sozinha. No fim de cada mão o servidor espera uns 2 segundos antes de mandar a próxima (seção 6.4).
- **P11. Quem responde pelo time no 2x2. Resolvido.** Qualquer jogador do time pode responder ao truco ou decidir a mão de onze, e vale a primeira resposta. A segunda recebe `erro` (seções 5.3 e 5.4).
- **P12. `valor` e `ultimo_aumento_time`. Resolvido.** Adotada a sugestão: `valor` é quanto a mão vale agora, isto é, o que o adversário ganha se alguém correr. Ele não muda no pedido, só no aceite e no aumento; `ultimo_aumento_time` recebe o time cujo pedido foi aceito (seção 5.3). Durante a decisão da mão de onze, `valor` é 1 (o que o adversário ganha se o time com 11 correr) e passa a 3 quando o time decide jogar (seção 5.4).
- **P13. Mão de ferro. Resolvido.** Decisão do grupo: com 11 a 11, o servidor só marca `"tipo": "mao_de_ferro"` e bloqueia o truco, sem decisão de mão de onze e sem cartas às cegas. As cartas vão em `mao` como numa mão comum, e a mão vale 1: quem vencer chega a 12 e ganha a partida. É o mesmo comportamento do servidor simulado da tela.
- **P14. Limites de nome e de chat. Em parte resolvido.** O chat ficou em 50 mensagens no histórico e 200 caracteres por mensagem, conferidos também no servidor (seção 5.5). Continua em aberto o nome: a cor do autor no chat é escolhida comparando `de` com o `nome` dos jogadores, então nomes repetidos se confundem, e a tela não corta nomes longos. Decidir o tamanho máximo do nome.

### Mensagens do contrato

- **P15. `erro`. Resolvido.** Os códigos são `fora_da_vez`, `carta_invalida`, `acao_invalida` e `nao_autorizado` (seção 6.2), e a tela mostra a `mensagem` por alguns segundos na barra de ações.
- **P16. `truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`. Resolvido.** Essas mensagens deixaram de existir. O servidor só manda `estado` e `erro`, e o fim da partida vem no `status` do `estado` (seção 6.4).

### Decisões do backend

- **P17. Token e assento. Resolvido.** O token é o JWT do Auth (HS256, com `sub`, `nome` e `exp`, assinado com `JWT_SEGREDO`), conferido pelo próprio Game. O `sub` é o id do usuário e é comparado com o `usuario_id` de cada assento. O bot usa um token assinado pelo próprio serviço de Bots, com o mesmo segredo e `sub` no formato `bot-<partida_id>-<assento>`, que diz a partida e o assento (seção 10.5).
- **P18. Códigos de fechamento. Resolvido.** 4401 para token inválido, 4403 para usuário fora da partida e 4404 para partida inexistente, sempre com `accept()` antes do `close()` (seção 3.4).
- **P19. Duas conexões do mesmo jogador. Resolvido.** A mais recente substitui a anterior, que é fechada com o código 4409. A tela trata o 4409 como recusa: mostra "Esta partida foi aberta em outra aba." e volta para o lobby, sem reconectar (seções 3.4 e 6.6). O código e o tratamento na tela foram acrescentados nesta fase.
- **P20. Jogador que cai no meio da partida. Resolvido.** Decisão do grupo: a partida espera ele voltar, sem prazo, sem bot no lugar e sem derrota do time (seção 6.6). Continua não havendo indicador de jogador desconectado na tela. O botão "Sair da partida" só fecha a conexão: para o servidor, é igual a uma queda, e o jogador pode voltar pela mesma URL.
- **P21. Um processo ou vários. Resolvido.** O Game roda num processo só, num container só, com as conexões e as travas na memória. A limitação está documentada em `services/game/app/partidas.py` e no README. Para ter vários processos, seria preciso distribuir os avisos entre eles (pub/sub do Redis, por exemplo) e trocar a trava em memória por uma no Redis.
- **P22. Caminho no Nginx. Resolvido.** O gateway repassa `/ws/partidas/...` ao Game sem alterar o caminho nem a query string (seção 3.5). A rota interna `/interno/...` não passa pelo gateway.

## 10. O serviço Game de verdade

Esta seção registra o que a implementação em `services/game/` decidiu além do que as seções anteriores pedem.

### 10.1 Como o serviço está montado

| Parte | Onde | O que faz |
|---|---|---|
| Motor de regras | `services/game/engine/` | Python puro, sem FastAPI, Redis nem I/O. Recebe o estado e uma ação e devolve o novo estado, ou levanta `ErroJogada` com o `codigo` e a `mensagem` da seção 6.2. Também monta a visão de cada jogador (`visao.py`). |
| Camada de serviço | `services/game/app/` | FastAPI: o WebSocket da mesa, a rota interna, o Redis e os eventos. |
| Banco | container `game-redis` | Redis só do Game. Cada partida fica na chave `partida:<partida_id>`, com o estado completo em JSON (formato em `engine/partida.py`). A chave vence depois de 7 dias sem mudança. |
| Broker | container `eventos` | Outro Redis, só para os eventos entre os serviços (seção 10.4). |

- Uma mudança por vez em cada partida: cada uma tem uma trava (`asyncio.Lock`). Com a trava fechada, a ação lê o estado do Redis, passa pelo motor, é gravada e o novo estado vai para todos (seção 6.5).
- O sorteio das cartas usa `random.SystemRandom`, que não dá para prever a partir das mãos anteriores.
- A pausa de 2 segundos entre as mãos roda numa tarefa à parte. Depois de um reinício do Game, uma partida que tinha parado no fim de uma mão recebe a próxima quando alguém conecta.
- Mensagens com mais de 64 KB derrubam a conexão (`--ws-max-size` do Uvicorn). As da mesa são bem menores.
- O Game roda num processo só (P21).

### 10.2 Regras adotadas pelo motor

- **Força das cartas**: 4, 5, 6, 7, Q, J, K, A, 2, 3. A manilha é o valor seguinte ao da vira; entre as manilhas, paus > copas > espadas > ouros. Fora das manilhas o naipe não conta: dois reis empatam.
- **Rodada**: vence a carta mais forte de cada time; com a mesma força, a rodada empata. Carta coberta não vale nada: perde para qualquer carta aberta, e duas cobertas empatam. Abre a rodada seguinte quem jogou a carta vencedora; depois de um empate, quem abriu a rodada empatada.
- **Mão (melhor de 3) e empates**: vence quem ganhar duas rodadas. Havendo empate, vence o time que ganhou a primeira rodada que não empatou:
  - 1ª empatada: leva quem vencer a 2ª (ou a 3ª, se a 2ª também empatar);
  - 1ª vencida e 2ª empatada: leva quem venceu a 1ª, sem jogar a 3ª;
  - uma rodada para cada e a 3ª empatada: leva quem venceu a 1ª;
  - as três empatadas: ninguém pontua.
- **Ordem**: a vez anda pela numeração dos assentos. O pé (quem dá as cartas) passa para o assento seguinte a cada mão, e joga primeiro o assento depois do pé; na primeira mão, o assento 0.
- **Truco**: 1, 3, 6, 9 e 12, com aceitar, correr e aumentar. Só na própria vez e só em mão `"normal"`. O mesmo time não aumenta duas vezes seguidas, e correr dá a quem pediu o `valor` atual (seção 5.3).
- **Mão de onze**: o time com 11 decide antes de qualquer carta (no 2x2, qualquer um dos dois, e vale a primeira decisão) e vê a mão do parceiro durante a mão inteira. Jogando, a mão vale 3; correndo, o adversário ganha 1. Sem truco.
- **Mão de ferro** (11 a 11): só o tipo e o truco bloqueado, valendo 1 (P13).
- **Fim**: aos 12 pontos. O placar não passa de 12: um time com 10 que vence uma mão valendo 3 fica com 12.
- **Chat**: texto sem espaços nas pontas, cortado em 200 caracteres, com as 50 últimas mensagens. Vale a qualquer momento, inclusive na pausa entre as mãos e depois do fim.

### 10.3 Rota interna: `POST /interno/partidas`

Quem chama é o Lobby, ao iniciar a sala ([guia do lobby](guia-backend-lobby.md), seção 6.6). A rota fica fora do gateway: só os containers da `rede-servicos` a alcançam, em `http://game:8000/interno/partidas`. O corpo é o proposto no guia do lobby (P2 de lá), sem mudanças:

```json
{
  "sala_id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "assentos": [
    {"assento": 0, "usuario_id": "a712cd19-7914-4807-b5ee-a277fde52cee", "nome": "Ana", "bot": false},
    {"assento": 1, "usuario_id": null, "nome": "Bot 1", "bot": true}
  ]
}
```

| Resposta | Quando |
|---|---|
| 201, `{"partida_id": "..."}` | Partida criada, com a primeira mão distribuída. O `partida_id` é um UUID em texto. O Game publica o `partida.criada`. |
| 422, `{"erro": "dados_invalidos", "mensagem": "..."}` | Corpo fora do formato, ou assentos que não formam uma mesa: quantidade diferente de 2 ou 4, numeração fora de 0 a N-1 ou repetida, jogador sem `usuario_id`, bot com `usuario_id`, o mesmo usuário em dois assentos, nome vazio ou com mais de 20 caracteres. A `mensagem` diz o problema. |

- `sala_id` pode ser `null`: o script de teste cria partidas sem sala.
- No 2x2, os assentos 0 e 2 formam o time A, e 1 e 3 o time B.

### 10.4 Eventos no broker: formato final para o Lobby e o Ranking

O formato é o proposto no guia do lobby (seção 7.4 de lá):

- Um stream por evento, com o nome do evento: `partida.criada` e `partida.finalizada`.
- Cada mensagem com um campo só, `dados`, com o evento em JSON.
- Quem consome lê com um grupo próprio (`XREADGROUP`: `lobby` no Lobby, `ranking` no Ranking), confirma cada mensagem com `XACK` e ignora repetidos pelo `partida_id`, porque o mesmo evento pode chegar mais de uma vez.
- O broker é o container `eventos`, na `rede-eventos`, com a senha `EVENTOS_SENHA`. O serviço que for ler entra nessa rede e recebe `EVENTOS_HOST`, `EVENTOS_PORTA` e `EVENTOS_SENHA`, como o Game no `docker-compose.yml`.

`partida.criada`, publicado quando a partida é criada:

```json
{"partida_id": "8d5b6fab-2983-475c-8b76-b38682a0cd3b", "sala_id": "54200ad3-e277-4d64-9ab8-eb4cebf843df", "formato": "1x1", "criada_em": "2026-10-28T14:39:02+00:00"}
```

`partida.finalizada`, publicado quando um time chega a 12:

```json
{
  "partida_id": "98b32790-8440-491c-a662-b983693b2411",
  "sala_id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "formato": "2x2",
  "times": {
    "A": [
      {"assento": 0, "usuario_id": "2e80dd09-a09b-4a13-aa5f-d75f358d2ddb", "nome": "Ana", "bot": false},
      {"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true}
    ],
    "B": [
      {"assento": 1, "usuario_id": "7871a853-f35d-42c5-8dd1-e78533f7b4ef", "nome": "Beto", "bot": false},
      {"assento": 3, "usuario_id": "5f1c9a2e-3b7d-4e8a-9c61-0d2e4f8a7b13", "nome": "Caio", "bot": false}
    ]
  },
  "vencedor_time": "A",
  "placar_final": {"A": 12, "B": 6},
  "encerrada_em": "2026-10-28T14:46:39+00:00"
}
```

- `times` segue o formato proposto no guia do lobby (P4 de lá), com `assento` e `bot` a mais. Bots vêm com `"usuario_id": null`.
- As datas são texto no formato ISO 8601, em UTC.
- Entrega: o evento não vai direto ao broker. Ele é gravado no `game-redis`, na fila `eventos:pendentes`, na mesma transação que o estado da partida, e uma tarefa do Game passa a fila para o broker. Com o broker fora do ar, as partidas continuam e os eventos esperam na fila. Se o Game cair no meio de uma entrega, o evento sai de novo quando ele voltar: por isso o consumidor precisa ignorar repetidos.

Para ver os eventos publicados: `docker compose exec eventos redis-cli XRANGE partida.finalizada - +`.

### 10.5 Bots: como o Game identifica e autentica

Seguindo a proposta do grupo, o serviço de Bots assina o próprio token, sem passar pelo Auth:

- HS256, com o mesmo `JWT_SEGREDO` dos outros serviços.
- `sub` no formato `bot-<partida_id>-<assento>`, por exemplo `bot-98b32790-8440-491c-a662-b983693b2411-1`. O `partida_id` tem hífens (é um UUID): o assento é o número depois do último hífen.
- `nome` com o nome do assento ("Bot 1") e `exp`, obrigatório como em qualquer token.

O bot conecta como um jogador, em `/ws/partidas/{partida_id}?token=<jwt>`. Como está na `rede-servicos`, pode usar o endereço interno `ws://game:8000/...`, sem passar pelo gateway. O Game aceita o token só na partida indicada no `sub` e só num assento criado como bot; nos outros casos, fecha com 4403.

Por que esse formato: o `sub` de um usuário é sempre um UUID, então um `sub` que começa com `bot-` nunca se confunde com um jogador; e o próprio token diz a partida e o assento, sem campo extra e sem consultar outro serviço. A conferência já está no Game (`app/seguranca.py`), com testes.

Quem assina esse token e joga pelos bots é o serviço de Bots, desde a fase 4 (seção 10.7). Ele assina um token novo a cada conexão, válido por 10 minutos: o Game só confere o token ao conectar.

### 10.6 Divergências e acréscimos em relação às seções anteriores

- **Código de fechamento 4409**, novo, para a conexão substituída por outra do mesmo jogador, com o tratamento em `frontend/js/ws.js` (P19).
- **`coberta` ausente** em `jogar_carta` vale `false` (seção 5.1). Mensagem binária no WebSocket recebe `erro` com `acao_invalida`, como um texto que não é JSON.
- **Placar limitado a 12** e **três rodadas empatadas sem ponto** (seção 10.2). O documento de contratos não trata esses casos; o servidor simulado da tela faz o mesmo.
- **`POST /interno/partidas` responde 201.** O guia do lobby pede só o corpo `{"partida_id"}`; o exemplo do Lobby aceita qualquer status 2xx.
- **`partida.finalizada` traz `assento` e `bot`** em cada jogador de `times`, além do proposto.
- **`vencedor_assento` em cada rodada**, acrescentado no fechamento do projeto: o assento da carta vencedora, calculado pelo motor (`engine/regras.py`), `null` no empate e com a rodada em andamento. A tela o usa para destacar só a carta vencedora no 2x2 (seção 4.1). Uma partida gravada antes do campo existir sai com `null` nas rodadas antigas.
- **Partida parada por 7 dias é apagada** do `game-redis`; depois disso, quem tentar conectar recebe 4404.

### 10.7 O serviço de Bots

O serviço de Bots (`services/bots/`, fase 4) joga pelos assentos de bot. Ele não importa nada do Game, nem o motor de regras: para o Game, cada bot é um cliente da mesa como a tela, que conecta ao WebSocket, recebe só a própria visão do `estado` e envia as mensagens da seção 5. Ele não acessa o `game-redis` nem nenhum banco.

| Parte | Onde | O que faz |
|---|---|---|
| Pedidos | `app/eventos.py` | Lê o `bot.solicitado` do broker, com o grupo `bots` ([guia do lobby](guia-backend-lobby.md), seção 11.3), e cria um bot para cada pedido. Todos os bots rodam no mesmo processo, cada um numa tarefa do asyncio. |
| Bot | `app/bot.py` | A conexão com a mesa: recebe o `estado`, pergunta à estratégia o que fazer, espera e envia. Trata as quedas e os fechamentos. |
| Estratégia | `app/estrategia.py`, `app/cartas.py` | Python puro, sem rede: recebe o `estado` e devolve a mensagem a enviar, ou nada. Comentada para quem está começando. |
| Token | `app/seguranca.py` | O token da seção 10.5. |
| Saúde | `app/main.py` | `GET /saude`, só para o healthcheck do Docker Compose: 200 com o broker no ar, com o número de bots jogando. O serviço não tem outras rotas, não abre porta no computador e não passa pelo gateway. |

**Conexão.** O bot conecta em `ws://game:8000/ws/partidas/{partida_id}?token=<jwt>`, pela `rede-servicos`, com um token novo a cada conexão. Ao conectar, o Game manda o estado atual (seção 6.6), e é a partir dele que o bot joga: vale para a primeira conexão, para uma reconexão e para a volta depois de um reinício do serviço.

**Ritmo.** Antes de cada ação, o bot espera de 1 a 2 segundos, sorteados, para parecer um jogador e a tela das pessoas acompanhar cada jogada. Enquanto espera, continua lendo as mensagens: se o estado mudar, ele decide de novo. Ele age uma vez só em cada momento da partida (o estado sem o chat): uma mensagem de chat, que reenvia o mesmo estado, não o faz jogar de novo.

**Fechamentos e quedas** (seção 3.4):

| O Game fecha com | O bot |
|---|---|
| 4403 ou 4404 | Desiste da partida e registra no log. O pedido é confirmado no broker. |
| 4409 | Sai sem reconectar: outra conexão entrou no assento dele. O pedido é confirmado. |
| 4401 | Registra um erro (o `JWT_SEGREDO` dele é diferente do do Game) e continua tentando: corrigido o `.env`, volta a jogar. |
| Qualquer outro, ou a conexão não abre | Tenta de novo, esperando 1, 2, 4 e 8 segundos e, daí em diante, 10, o mesmo ritmo da tela. |

Quando chega o `estado` com `"status": "encerrada"`, o bot fecha a conexão (1000) e o pedido dele é confirmado no broker. Uma ação recusada com `erro` não deveria acontecer, porque a estratégia só escolhe jogadas válidas. Se acontecer, o bot registra no log e tenta uma vez uma jogada simples (carta aberta, sem truco).

**Sem banco.** O grupo `bots` do Redis Streams guarda quais pedidos ainda não foram confirmados, e o serviço só confirma um pedido quando o bot dele termina. Os pedidos pendentes são, então, a lista dos bots ativos. Se o serviço cair ou reiniciar no meio de uma partida, ele relê os seus pendentes ao subir (consumidor de nome fixo, `bots-1`) e põe esses bots para jogar de novo, sem nenhum banco próprio. O mesmo pedido repetido (o Lobby reenvia se cair na entrega) é reconhecido pelo `partida_id` e o `assento`: com o bot ainda jogando, ou já terminado, a mensagem repetida é confirmada sem criar outro bot.

**Quem responde pelo time no 2x2.** Vale a primeira resposta do time (seções 5.3 e 5.4). Para o bot não passar na frente de uma pessoa nem responder junto com outro bot:

- com um parceiro humano, o bot não responde ao truco nem decide a mão de onze: deixa para a pessoa. Na própria vez, ele joga e pede truco normalmente;
- com um parceiro bot, responde só o de menor assento;
- no 1x1, o bot responde sempre.

**Estratégia do nível `"padrao"`**, o único por enquanto (`app/estrategia.py` explica cada regra):

- Força das cartas como na seção 10.2: 4, 5, 6, 7, Q, J, K, A, 2, 3, com as manilhas acima de todas, por naipe (paus > copas > espadas > ouros).
- Cartas: abrindo a rodada, a mais forte (a mais fraca, se o time já ganhou uma rodada da mão); com o parceiro ganhando a rodada, descarta a mais fraca; senão, a menor carta que vence a mesa; sem carta que vença, descarta a mais fraca. Descarte da segunda rodada em diante vai coberto.
- Nota da mão: zap 5, outra manilha 4, 3 vale 3, 2 vale 2, ás vale 1; mais a carta do time que está ganhando a rodada em andamento; mais 3 por rodada ganha e menos 3 por rodada perdida. Se o bot é o último a jogar a rodada que decide a mão, ele já sabe o resultado e a nota vai ao máximo (ou a zero).
- Truco: pede com nota 6 ou mais (8 ou mais para pedir seis, nove ou doze); blefa com 8% de chance, só na primeira carta da mão. Desafiado, aumenta com 8 ou mais, aceita com 3 ou mais e corre abaixo disso.
- Mão de onze: joga com nota 5 ou mais. No 2x2, a nota usa as três melhores cartas das duas mãos, porque o time com 11 vê as cartas do parceiro.
- O sorteio (blefe e atrasos) usa a semente `BOTS_SEMENTE`, se definida no `.env`: o mesmo bot repete as mesmas escolhas nas mesmas situações.

**Limitações.**

- Um processo só, por causa do nome fixo do consumidor, como no Lobby e no Ranking.
- Partida abandonada: se a pessoa não volta, o bot fica conectado esperando, como a partida (P20). Depois de 7 dias parada o Game a apaga, e o bot desiste dela com o 4404 na próxima vez que conectar.
- Pedidos de antes do serviço existir também são atendidos (o grupo é criado a partir do início do stream): numa partida da fase 3 que ainda espera alguém, os bots entram e esperam junto; numa que já terminou, entram e saem.

**Testes** (`docker compose run --rm bots pytest`, com o sistema no ar):

- `tests/estrategia`: a estratégia, sem rede. Jogada válida em situações sorteadas, manilhas, carta coberta, truco e blefe, respostas, mão de onze e a regra do parceiro.
- `tests/servico/test_partidas.py`: uma partida 1x1 de uma pessoa contra um bot e uma 2x2 de uma pessoa com três bots, criadas pelo Lobby e jogadas até o fim pelo container `bots` que está no ar. Conferem também que o bot confirma o pedido no fim e que o Ranking registra a partida da pessoa, sem o bot.
- `tests/servico/test_retomada.py`: o serviço caindo no meio de uma partida, com o bot voltando a jogar quando ele sobe de novo, e o mesmo pedido chegando várias vezes sem criar outro bot. Aqui o serviço roda dentro do teste, num banco lógico próprio do broker (o 4), com partidas criadas direto no Game.
