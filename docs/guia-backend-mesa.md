# Guia do backend: o que a tela da mesa espera do serviço Game

Este guia é para quem vai implementar o serviço Game em Python com FastAPI. Ele explica o que o servidor precisa enviar e receber para a tela da mesa (`frontend/mesa.html`) funcionar conectada a ele, no lugar dos estados falsos (mocks) que ela usa hoje. Não é preciso conhecer FastAPI nem WebSocket: o guia explica o necessário e traz um exemplo pronto para rodar.

**De onde vêm as informações**

- **Código da tela**: `frontend/mesa.html`, `frontend/js/paginas/mesa.js`, `frontend/js/cartas.js` e `frontend/js/mock/estados.js`, na branch `feature/frontend-mesa` em 10/10/2026. Tudo o que o guia afirma que a tela lê, mostra ou envia saiu desse código e foi conferido rodando a tela no navegador com variações do estado. Atualizado em 20/10/2026 (branch `feature/frontend-partida`): a mesa passou a se conectar sozinha, pelo `frontend/js/ws.js`, e ganhou a espera, a reconexão, a tela de fim de partida e a saída.
- **Decisões de protocolo de 20/10/2026**: só as mensagens `estado` e `erro` do servidor, o campo `status`, os códigos de erro e de fechamento, a mão do parceiro na mão de onze, a primeira resposta do time no 2x2, a criação da rodada e a pausa entre as mãos. Elas aparecem como regras no texto e ainda não estão no documento de contratos. Os pontos em aberto que elas fecham estão marcados como resolvidos na seção 9.
- **Documento de requisitos e contratos** (link no [README](../README.md)): usado para o que o código ainda não cobre, como o endereço do WebSocket.

Quando os dois não batem, ou quando o código depende de algo que não está escrito em lugar nenhum, o texto traz um código como **P3**. Ele aponta para o item correspondente da seção 9, Pontos em aberto.

**Importante:** a tela já se conecta, mas hoje conversa com um servidor simulado, que roda dentro do navegador (`frontend/js/mock/servidor-game.js`). No topo de `frontend/js/ws.js`, a constante `USAR_MOCK_GAME` está em `true`. Com `false`, a mesma conexão vai para o Game de verdade, em `/ws/partidas/...` no mesmo endereço da página, sem nenhuma outra mudança no código (seção 8.3). O servidor simulado não é o motor de regras: ele existe só para testar a tela. Este guia descreve o lado do servidor.

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

Na ordem recomendada. Cada etapa termina em algo que dá para ver funcionando.

**Etapa 1: a tela abre com dados vindos do servidor**

- [ ] Projeto FastAPI rodando, com o Uvicorn instalado como `uvicorn[standard]` (seção 7).
- [ ] Endpoint WebSocket em `/ws/partidas/{partida_id}` que aceita a conexão (seção 3).
- [ ] Ao conectar, envio imediato de uma mensagem `estado` completa. Pode ser fixa (seção 4).
- [ ] Leitura das mensagens recebidas como JSON, sem derrubar a conexão quando chegar algo inválido.

**Etapa 2: cada jogador vê a sua própria mesa**

- [ ] Validação do token (`?token=<jwt>`) e descoberta do assento do jogador na partida.
- [ ] Recusa de token inválido, partida inexistente ou usuário que não está na partida, com os códigos 4401, 4404 e 4403 (seção 3.4).
- [ ] Registro das conexões abertas por partida e assento, com remoção ao desconectar.
- [ ] Visão filtrada por jogador: `meu_assento`, `mao` só do próprio, `qtd_cartas` de todos, carta coberta sem valor (seção 4.3).
- [ ] Envio do `estado` a todos os conectados sempre que ele mudar.
- [ ] Chat: a mensagem entra em `chat` com o nome do autor e o `estado` volta para todos.

**Etapa 3: uma partida 1x1 do começo ao fim**

- [ ] Partida criada já com a primeira mão distribuída: todo `estado` precisa de `mao_atual` (seção 3.3).
- [ ] `jogar_carta` com validação e atualização de `rodadas`, `qtd_cartas` e `vez_assento`.
- [ ] Fim de rodada (`vencedor_time`), com a rodada seguinte criada só na primeira carta dela (seção 6.4).
- [ ] Fim de mão: `placar` atualizado e, depois de uns 2 segundos, nova mão (`numero`, `pe`, `vira`, cartas e `valor` inicial).
- [ ] `pedir_truco` e `responder_truco`, mantendo `valor`, `truco_pendente` e `ultimo_aumento_time`.
- [ ] Ação inválida não muda o estado e gera `erro` só para quem enviou, com um dos códigos da seção 6.2.
- [ ] Fim de partida aos 12 pontos: `"status": "encerrada"` e `vencedor_time` (seção 6.4).

**Etapa 4: comportamento completo**

- [ ] 2x2: quatro assentos, times alternados, resposta ao truco pelo time, valendo a primeira (seção 5.3).
- [ ] Carta coberta a partir da segunda rodada.
- [ ] Mão de onze: `tipo`, `aguardando_decisao_mao_de_onze` e `decidir_mao_de_onze` (P4), com a mão do parceiro para o time com 11 (seção 4.3).
- [ ] Mão de ferro (P13).
- [ ] Bots conectando como clientes comuns.
- [ ] Volta do jogador depois de uma queda: a nova conexão recebe o estado atual (seção 6.6; P20).

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
| Qualquer outro, inclusive o 1006 | Queda | Tenta conectar de novo, sozinha (seção 6.6) |

**O servidor precisa chamar `accept()` antes de fechar com 4401, 4403 ou 4404.** Uma recusa sem `accept()` chega à tela como queda (1006): ela não sai da partida e fica tentando reconectar indefinidamente. Um caminho errado na URL também aparece como 403 e 1006. Se a conexão "falha sem motivo", confira primeiro o caminho.

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

Partida 2x2 na segunda rodada, enviada ao jogador do assento 0. A primeira rodada foi vencida pelo time A, a Maria abriu a segunda com uma carta coberta e agora é a vez do João.

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
- `coberta`: sempre presente. Só vai `true` quando a caixa "Jogar coberta" está marcada e a carta é da segunda rodada em diante.

O que o servidor faz:

1. Confere que é a vez do jogador, que não há truco nem decisão de mão de onze pendente, que a carta está na mão dele e que `coberta` só vem `true` a partir da segunda rodada.
2. Tira a carta da mão e acrescenta a jogada ao final de `jogadas` da rodada atual. Se a lista está vazia ou a última rodada já tem vencedor, cria antes a rodada nova, com esta carta como a primeira jogada. Depois passa `vez_assento` para o próximo.
3. Se a rodada terminou, preenche `vencedor_time` e passa `vez_assento` para quem abre a próxima, ou encerra a mão (seção 6.4).
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

O momento exato em que `valor` e `ultimo_aumento_time` mudam é regra do motor e precisa ser confirmado (P12).

### 5.4 `decidir_mao_de_onze`

```json
{"tipo": "decidir_mao_de_onze", "jogar": true}
```

- `jogar`: `true` no botão "Jogar a mão", `false` no botão "Correr".

Enquanto `aguardando_decisao_mao_de_onze` é `true`, a tela bloqueia as cartas de todos os jogadores. No 2x2, os dois parceiros do time com 11 pontos veem os botões, e vale a primeira decisão, como no truco.

O que o servidor faz:

1. Confere que há decisão pendente e que quem enviou é do time com 11 pontos.
2. Com `true`: `aguardando_decisao_mao_de_onze` passa a `false` e a mão segue. Com `false`: a mão termina, o outro time pontua e começa a próxima mão. Quantos pontos vale cada caso é regra do motor.
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

1. **Fim de rodada.** O estado sai com a rodada completa, `vencedor_time` preenchido e `vez_assento` em quem abre a próxima. A rodada nova **não** entra em `rodadas` agora: ela só é criada quando a primeira carta dela for jogada (seção 5.1). Assim a rodada encerrada continua na mesa até alguém abrir a seguinte, sem pausa nenhuma.
2. **Fim de mão.** O estado sai com a última rodada completa, o `placar` atualizado e `"vez_assento": null` (a tela mostra "Fim da mão."). O servidor espera uns 2 segundos e só então envia a mão nova: `numero`, `pe`, `vira`, cartas, `valor` inicial e `"rodadas": []`. Use `await asyncio.sleep(2)`. Nunca use `time.sleep`, que trava o servidor inteiro, para todas as partidas. Durante a pausa o chat continua funcionando, e as outras ações recebem `erro`.
3. **Fim de partida.** Quando um time chega a 12, o estado sai na hora com `"status": "encerrada"`, `vencedor_time` e a última mão em `mao_atual`, com `"vez_assento": null`. Não há mão nova. A tela mostra sobre a mesa o resultado, o placar final e o botão "Voltar ao lobby". Daí em diante só o chat vale, e quem conectar recebe o mesmo estado encerrado.

Não existem mensagens próprias para esses momentos. As que o documento de contratos previa "para animações e avisos" (`truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`) deixaram de existir: tudo vem no `estado`.

### 6.5 Mensagens ao mesmo tempo

- Processe uma mensagem por vez em cada partida, por exemplo com um `asyncio.Lock` por partida. Dois jogadores podem enviar no mesmo instante (os dois parceiros respondendo a um truco, por exemplo). Se o servidor ler, alterar e salvar o estado das duas ao mesmo tempo, uma das alterações se perde.
- Rode o Game com um único processo, sem a opção `--workers`. No exemplo 7.2 a lista de conexões fica na memória do processo. Com mais de um processo, jogadores da mesma partida podem estar conectados a processos diferentes e deixar de receber o estado uns dos outros (P21).

### 6.6 Queda de conexão

- Quando a conexão cai, tire-a da lista e mantenha o estado da partida.
- A tela tenta conectar de novo sozinha, esperando 1, 2, 4 e 8 segundos entre as tentativas e, daí em diante, 10 segundos. Enquanto isso, a mesa continua na tela com "Conexão perdida. Reconectando…". Depois de 4401, 4403 ou 4404 ela não tenta de novo (seção 3.4).
- Quando o mesmo jogador conectar de novo (um F5 na página também é uma volta), envie o `estado` atual, como em qualquer conexão. A tela se redesenha inteira a partir dele.
- Se o mesmo jogador aparecer com duas conexões ao mesmo tempo, por exemplo em duas abas, é preciso decidir qual delas vale (P19).
- O que acontece com a partida enquanto um jogador está fora ainda não foi decidido (P20).

### 6.7 Bots

Os bots conectam no mesmo endereço, recebem o mesmo tipo de `estado` (na visão deles) e enviam as mesmas mensagens da seção 5. Para a tela, um bot é só um jogador com `"bot": true`, que ganha o selo "BOT".

## 7. Exemplo mínimo em FastAPI

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

2. Em `frontend/js/ws.js`, troque `USAR_MOCK_GAME` para `false`. Não faça commit dessa troca antes de o Game estar no ar para toda a equipe.
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
- **P12. `valor` e `ultimo_aumento_time`.** A tela mostra `valor` como "Valendo N", usa `valor` para o texto do botão de truco e usa `ultimo_aumento_time` para bloquear o botão. Confirmar com o motor de regras em que momento cada um muda (no pedido, no aceite, no aumento) e qual `valor` aparece durante a decisão da mão de onze. Sugestão coerente com a tela: `valor` é quanto a mão vale agora, isto é, o que o adversário ganha se alguém correr.
- **P13. Mão de ferro.** A tela só mostra o selo "Mão de ferro" e desabilita o truco. Se a regra adotada for jogar sem ver as próprias cartas, a tela não dá suporte: `mao` precisa ter códigos válidos (um `null` na lista quebra a tela) e `jogar_carta` leva o código da carta. `vira` também é sempre obrigatória. Definir a regra e o que o servidor envia nesse tipo de mão. O servidor simulado da tela também deixa a regra de fora: com 11 a 11, ele só marca o tipo e não deixa pedir truco.
- **P14. Limites de nome e de chat. Em parte resolvido.** O chat ficou em 50 mensagens no histórico e 200 caracteres por mensagem, conferidos também no servidor (seção 5.5). Continua em aberto o nome: a cor do autor no chat é escolhida comparando `de` com o `nome` dos jogadores, então nomes repetidos se confundem, e a tela não corta nomes longos. Decidir o tamanho máximo do nome.

### Mensagens do contrato

- **P15. `erro`. Resolvido.** Os códigos são `fora_da_vez`, `carta_invalida`, `acao_invalida` e `nao_autorizado` (seção 6.2), e a tela mostra a `mensagem` por alguns segundos na barra de ações.
- **P16. `truco_pedido`, `rodada_encerrada`, `mao_encerrada` e `partida_encerrada`. Resolvido.** Essas mensagens deixaram de existir. O servidor só manda `estado` e `erro`, e o fim da partida vem no `status` do `estado` (seção 6.4).

### Decisões do backend

- **P17. Token e assento.** O contrato diz que o token vai em `?token=<jwt>` e que cada serviço valida o JWT sozinho. Não diz quais dados vêm dentro dele (qual campo identifica o usuário) nem como o bot, que usa um "token de serviço", informa em que assento está.
- **P18. Códigos de fechamento. Resolvido.** 4401 para token inválido, 4403 para usuário fora da partida e 4404 para partida inexistente, sempre com `accept()` antes do `close()` (seção 3.4).
- **P19. Duas conexões do mesmo jogador.** Decidir o que acontece se o mesmo usuário abrir a mesa em duas abas: a nova substitui a antiga, a nova é recusada ou as duas recebem o estado.
- **P20. Jogador que cai no meio da partida.** Decidir se a partida espera, se um bot assume ou se o time perde. A tela não tem indicador de jogador desconectado nem relógio de tempo de jogada. O botão "Sair da partida" da tela só fecha a conexão e volta ao lobby: para o servidor, é igual a uma queda.
- **P21. Um processo ou vários.** Se as conexões ficarem na memória do processo, como no exemplo 7.2, o Game precisa rodar com um único processo. Com mais de um, é preciso distribuir os avisos entre eles, por exemplo com o pub/sub do Redis.
- **P22. Caminho no Nginx.** Confirmar que o gateway repassa `/ws/partidas/...` ao Game sem alterar o caminho, como os exemplos deste guia assumem.
