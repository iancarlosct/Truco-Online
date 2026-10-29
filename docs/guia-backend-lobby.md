# Guia do backend: o que a tela do lobby espera dos serviços Lobby e Ranking

Este guia é para quem vai implementar os serviços Lobby e Ranking em Python com FastAPI e Postgres. Ele explica o que cada serviço precisa receber e responder para a tela do lobby (`frontend/lobby.html`) funcionar ligada a eles. Não é preciso conhecer FastAPI: o guia explica o necessário e traz um exemplo pronto para rodar.

**De onde vêm as informações**

- **Código da tela**: `frontend/lobby.html`, `frontend/js/paginas/lobby.js` e as funções e o mock do Lobby e do Ranking em `frontend/js/api.js`, na branch `feature/frontend-lobby` em 14/10/2026. Tudo o que o guia afirma que a tela envia, lê ou mostra saiu desse código e foi conferido no navegador: com o mock e, com ele desligado, falando com os exemplos da seção 8.
- **Mock dentro de `api.js`**: respondia no lugar dos serviços até a fase 3 e foi apagado no fechamento do projeto. Os códigos de erro dele são os definitivos, por decisão do grupo.
- **Decisões do grupo**: a rota de remover assento, os códigos de erro, o nome dos bots, a sala encerrada, uma sala por vez, o link de convite, a presença e o ranking. Elas aparecem como regras, principalmente na seção 6, e não como pontos em aberto.
- **Documento de requisitos e contratos** (link no [README](../README.md)): usado para o que a tela não enxerga, como a chamada do Lobby ao Game (`POST /interno/partidas`) e os eventos no Redis Streams. Os trechos que vêm só do documento estão marcados.

Quando essas fontes não definem algo, ou quando o guia propõe uma forma de fazer, o texto traz um código como **P3**. Ele aponta para o item correspondente da seção 10, Pontos em aberto.

**Importante:** os dois serviços existem (`services/lobby/` e `services/ranking/`, no Docker Compose desde a fase 3), e a tela fala só com eles: os mocks que a tela usava antes foram apagados no fechamento do projeto (seção 1.6). A seção 11 registra o que a implementação decidiu além das seções anteriores; os exemplos da seção 8 continuam como material de estudo.

## 1. Como a tela funciona

A tela não tem regra de sala nem de ranking. Ela faz só três coisas:

1. **Pede os dados de tempos em tempos** e desenha o que recebe.
2. **Envia o que o jogador quer fazer** (criar sala, entrar, pôr um bot, iniciar) e se redesenha com a resposta.
3. **Mostra a `mensagem` dos erros** num aviso discreto, no pé da tela.

Quem decide se uma ação vale é o servidor. A tela esconde ou desabilita os botões que não fazem sentido para o jogador, mas isso é comodidade, não segurança: qualquer pessoa pode chamar as rotas direto.

### 1.1 Duas vistas e um painel

A página tem duas vistas, trocadas sem recarregar, e o painel do ranking sempre à direita:

```text
Lista de salas (lobby.html)
  GET /api/lobby/salas a cada 3 s
  "Criar sala 1x1/2x2"  -> POST /api/lobby/salas              -> abre a sala criada
  "Entrar" num cartão   -> POST /api/lobby/salas/{id}/entrar  -> abre a sala

Sala de espera (lobby.html?sala={id})
  GET /api/lobby/salas/{id} a cada 3 s
  clicar numa vaga      -> POST .../entrar                  (sentar ou trocar de assento)
  "Adicionar bot"       -> POST .../bot                     (só o dono)
  "Remover"             -> DELETE .../assentos/{assento}    (só o dono)
  "Sair da sala"        -> POST .../sair                    -> volta à lista
  "Iniciar partida"     -> POST .../iniciar                 (só o dono) -> mesa.html?partida={partida_id}

Painel do ranking
  GET /api/ranking uma vez, ao abrir a página
  nome de um jogador    -> historico.html?jogador={usuario_id}

Cabeçalho
  "Meu histórico"       -> historico.html    (GET /api/ranking/jogadores/{id}, seção 11.5)
```

A sala aberta fica na URL (`lobby.html?sala={id}`). Depois de um F5, a tela volta a ela.

### 1.2 Atualização periódica

Não há WebSocket no lobby. A tela pergunta ao servidor a cada 3 segundos (polling):

- Na lista, pede `GET /api/lobby/salas`. Na sala, `GET /api/lobby/salas/{id}`.
- O próximo pedido só sai quando o anterior termina. A tela espera cada resposta por até 10 segundos.
- Com a aba do navegador oculta (outra aba na frente, janela minimizada), os pedidos da lista param. Os da sala de espera continuam, para o jogador não perder o assento (seção 6.5). Quando a aba volta, sai um pedido na hora.
- Um erro não para a atualização: vira aviso, e a próxima tentativa sai no horário.
- O ranking é pedido uma vez só, ao abrir a página.

O que isso significa para o servidor:

- Cada aba aberta faz uns 20 pedidos por minuto. As rotas de leitura precisam ser leves.
- O `GET /api/lobby/salas/{id}` de quem está sentado vale como sinal de presença (seção 6.5). Quem passa 60 segundos sem pedir a sala sai dela.
- Uma mudança feita por outro jogador aparece na tela em até 3 segundos.

### 1.3 Ações e respostas

- Enquanto uma ação está em andamento, todos os botões ficam desabilitados, contra o clique duplo. Mesmo assim, dois pedidos podem chegar juntos (duas abas, dois jogadores), e o servidor precisa tratar isso (seção 6.8).
- **A tela se redesenha com a sala que a ação devolve.** Por isso criar, entrar, bot e `DELETE` precisam devolver a sala inteira, já atualizada. A resposta do `/sair` não é lida, e a do `/iniciar` só precisa do `partida_id`.
- Num erro, a tela mostra a `mensagem` e pede os dados de novo na hora, porque o que está na tela pode estar velho.
- O botão "Entrar" de um cartão escolhe sozinho o primeiro assento vago, a partir da lista que a tela tem, que pode ter até 3 segundos. O servidor pode responder `sala_cheia` ou `assento_ocupado`, e está certo.

### 1.4 O que a tela deduz da sala

Tudo o que a tela mostra vem do objeto da sala (seção 4). Ela deduz:

| A tela precisa saber | Como descobre |
|---|---|
| Qual é o assento do jogador | O assento cujo `usuario_id` é igual ao `usuario.id` recebido no login. Por isso o `sub` do token tem que ser esse mesmo id (seção 6.1). |
| Se ele é o dono | `dono_id` igual ao `usuario.id`. Só então aparecem "Adicionar bot", "Remover" e "Iniciar partida". |
| Se um assento está ocupado | `bot` é `true` ou `usuario_id` não é `null`. |
| O time de cada assento | Pela paridade do número: pares no time A, ímpares no time B. |
| Onde desenhar cada assento | Pela diferença entre o número do assento e o do jogador: ele embaixo, o seguinte à direita, depois em frente e à esquerda, como na mesa ([guia da mesa](guia-backend-mesa.md), seção 4.1). Quem não está sentado vê a mesa a partir do assento 0. |
| Se o jogador foi tirado da sala | Ele estava sentado na versão anterior da sala e não está mais. A tela volta para a lista com "Você foi removido da sala." |
| Se a sala acabou | `status` diferente de `"aguardando"` e `partida_id` vazio. A tela volta para a lista com "A sala foi encerrada." |
| Se a partida começou | `partida_id` preenchido. Quem está sentado vai para `mesa.html?partida={partida_id}`; quem só olhava volta para a lista com "A partida desta sala já começou." |

Quem abre o link de uma sala sem estar sentado nela vê a mesa e escolhe uma vaga ("Sentar aqui"). É o link de convite (seção 6.3). Não tem relação com espectadores de partida, que o documento de contratos deixa fora do escopo.

### 1.5 Sessão

Toda chamada passa pela função `requisitar`, de `api.js`, que manda o cabeçalho `Authorization: Bearer <token>` ([guia do login](guia-backend-login.md), seção 1.3). Se uma rota do Lobby ou do Ranking responder **401**, a tela apaga a sessão e volta para a tela de login. Isso vale para todas as rotas, menos login e cadastro. A tela não olha o código do erro, só o status. Antes de montar a página, o lobby confere o token no Auth (`GET /api/auth/me`, função `conferirSessao`): um token vencido, ou de um usuário que não existe mais, volta direto para o login com "Sua sessão expirou. Entre novamente." ([guia do login](guia-backend-login.md), P2).

O botão Sair do lobby chama `POST .../sair` antes do logout quando a sala de espera está aberta e o jogador está sentado nela.

### 1.6 O mock (apagado no fechamento)

Até a fase 3, um mock dentro de `frontend/js/api.js` fazia o papel do Lobby e do Ranking, guardando as salas no `localStorage` do navegador. Ele seguia as rotas e os códigos de erro deste guia, que continuam os mesmos. Desde a fase 3 a tela fala com os serviços de verdade, e no fechamento do projeto o código do mock foi apagado. As regras que o mock não tinha (a sala encerrada, a presença, o ranking com empates e os dois códigos de token) são as das seções 5 e 6, e o serviço as segue.

## 2. Checklist do que os serviços precisam entregar

Na ordem recomendada. Cada etapa termina em algo que dá para ver funcionando. Tudo feito: na fase 3, e o último item no fechamento do projeto.

**Etapa 1: o Lobby respondendo no formato certo**

- [x] Projeto FastAPI rodando com o Uvicorn (seção 8).
- [x] Token conferido em todas as rotas, com o mesmo segredo do Auth (seção 6.1).
- [x] `GET` e `POST /api/lobby/salas` e `GET /api/lobby/salas/{id}`, com a sala no formato da seção 4.
- [x] `entrar` e `sair`, inclusive a troca de assento.
- [x] Erros no formato `{"erro": "...", "mensagem": "..."}`, inclusive os que o FastAPI gera sozinho (seção 5).

Com isso a lista, a criação e a sala de espera já funcionam com a tela (seção 9.4).

**Etapa 2: regras do dono e das salas**

- [x] `bot` e `DELETE .../assentos/{assento}`, só para o dono (seção 6.2).
- [x] Uma sala aberta por usuário (seção 6.3).
- [x] Dono que sai encerra a sala (seção 6.4).
- [x] Um pedido de cada vez por sala, para dois jogadores não sentarem no mesmo assento (seção 6.8).

**Etapa 3: presença**

- [x] Hora do último `GET` de cada jogador sentado. Depois de 60 segundos sem ele, o jogador sai da sala, e o dono ausente encerra a sala (seção 6.5).

**Etapa 4: início da partida**

- [x] `POST .../iniciar` pedindo a partida ao Game em `POST /interno/partidas` (seção 6.6).
- [x] Um evento `bot.solicitado` no Redis Streams para cada bot da sala (seções 6.6 e 7.4).

**Etapa 5: Ranking**

- [x] Leitura do evento `partida.finalizada`, sem contar a mesma partida duas vezes (seções 6.7 e 7.4).
- [x] `GET /api/ranking` com os 10 primeiros, a linha do usuário logado quando ele está abaixo deles e empates dividindo a posição (seção 3.10).

**Etapa 6: Postgres, Docker e gateway**

- [x] Tabelas do Lobby e do Ranking no Postgres (seção 7).
- [x] Serviços no Docker Compose, com o Uvicorn em `--host 0.0.0.0` e um processo só (seção 6.8).
- [x] Rotas `/api/lobby/` e `/api/ranking` no Nginx, e `/interno` fora dele (seção 3.1).
- [x] A tela falando com o Lobby e o Ranking de verdade, desde a fase 3.
- [x] O mock apagado de `api.js`, no fechamento do projeto.

## 3. Rotas

### 3.1 Resumo, gateway e cabeçalhos

| Método | Rota | Corpo enviado | Resposta de sucesso | Quem pode |
|---|---|---|---|---|
| GET | `/api/lobby/salas` | nenhum | 200, lista das salas `"aguardando"` | Qualquer usuário logado |
| POST | `/api/lobby/salas` | `formato` | 201, a sala criada | Quem não está em outra sala aberta |
| GET | `/api/lobby/salas/{id}` | nenhum | 200, a sala | Qualquer usuário logado |
| POST | `/api/lobby/salas/{id}/entrar` | `assento` | 200, a sala | Qualquer usuário logado |
| POST | `/api/lobby/salas/{id}/sair` | nenhum | 200, a sala | Quem está sentado na sala |
| POST | `/api/lobby/salas/{id}/bot` | `assento`, `nivel` | 200, a sala | O dono |
| DELETE | `/api/lobby/salas/{id}/assentos/{assento}` | nenhum | 200, a sala | O dono |
| POST | `/api/lobby/salas/{id}/iniciar` | nenhum | 200, `{"partida_id"}` | O dono |
| GET | `/api/ranking` | nenhum | 200, lista de linhas | Qualquer usuário logado |

O documento de contratos tem também `GET /api/ranking/jogadores/{id}`, o histórico do jogador. Ela não é chamada pelo lobby, e sim pela tela do histórico (`frontend/historico.html`), no formato da seção 11.5 (P15).

O caminho chega inteiro ao serviço, como no guia do login (seção 3.1 de lá): as rotas são declaradas com o prefixo completo (`APIRouter(prefix="/api/lobby")`). Assim a mesma URL funciona direto no serviço e pelo gateway (P17). O trecho abaixo é o esboço original; a configuração em uso está em `gateway/nginx.conf`, com um `upstream` por serviço e o `resolve` (o gateway acompanha um container recriado sem reiniciar):

```nginx
location /api/lobby/ {
    proxy_pass http://lobby:8000;     # nome e porta do serviço no docker-compose, sem barra no fim
    proxy_set_header Host $host;
}

location /api/ranking {
    proxy_pass http://ranking:8000;
    proxy_set_header Host $host;
}
```

- `/api/ranking` fica sem barra no fim porque a tela pede `/api/ranking`, sem barra.
- `/interno/...`, a rota do Game que o Lobby chama, não entra no Nginx: só os serviços a enxergam (seção 6.6).

Em todo pedido, a tela manda:

| Cabeçalho | Valor | Quando |
|---|---|---|
| `Accept` | `application/json` | Sempre |
| `Authorization` | `Bearer <token>` | Sempre (o lobby só abre com sessão) |
| `Content-Type` | `application/json` | Só quando há corpo: criar, entrar e bot |

`sair` e `iniciar` são `POST` sem corpo nenhum. Essas rotas não podem exigir corpo.

### 3.2 `GET /api/lobby/salas`

Lista as salas com `status: "aguardando"`, inclusive as cheias (a tela mostra "Sala cheia" com o botão desabilitado). Salas em partida e encerradas ficam de fora.

Resposta, com status **200**: uma lista de salas no formato da seção 4. Sem nenhuma sala, `[]`.

```json
[
  {
    "id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
    "formato": "2x2",
    "dono_id": "u-ana",
    "status": "aguardando",
    "partida_id": null,
    "assentos": [
      {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": false},
      {"assento": 1, "usuario_id": null, "nome": null, "bot": false},
      {"assento": 2, "usuario_id": null, "nome": null, "bot": false},
      {"assento": 3, "usuario_id": null, "nome": null, "bot": false}
    ]
  }
]
```

Nos exemplos deste guia, os ids de usuário foram encurtados (`u-ana`) para facilitar a leitura. No serviço real eles são o `sub` do token, que no Auth é um UUID (seção 6.1).

- A tela desenha um cartão por sala, na ordem da lista. Sugestão: da mais antiga para a mais nova.
- Do cartão, ela tira o formato, a ocupação ("3/4 jogadores"), o nome do dono e o primeiro assento vago, usado pelo botão "Entrar".
- Se o usuário está sentado numa sala da lista, o cartão mostra "Voltar à sala", que abre a sala sem pedir para entrar de novo.
- A resposta tem que ser uma lista. Um objeto, como `{"salas": [...]}`, faz a tela mostrar "Algo deu errado. Tente de novo.".

### 3.3 `POST /api/lobby/salas`

Corpo enviado pela tela:

```json
{"formato": "2x2"}
```

Resposta de sucesso, com status **201**: a sala criada, com quem criou no assento 0, como dono, e os outros assentos vazios (P6). A tela aceita qualquer status de 200 a 299.

```json
{
  "id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "formato": "2x2",
  "dono_id": "u-ana",
  "status": "aguardando",
  "partida_id": null,
  "assentos": [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": false},
    {"assento": 1, "usuario_id": null, "nome": null, "bot": false},
    {"assento": 2, "usuario_id": null, "nome": null, "bot": false},
    {"assento": 3, "usuario_id": null, "nome": null, "bot": false}
  ]
}
```

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token ausente, inválido ou vencido | 401 | `token_invalido` ou `token_expirado` |
| Corpo sem `formato`, ou que não é JSON | 422 | `dados_invalidos` |
| `formato` diferente de `"1x1"` e `"2x2"` | 422 | `dados_invalidos` ("Formato de sala inválido.") |
| O usuário já está sentado numa sala `"aguardando"` | 409 | `ja_esta_em_outra_sala` |

O que o servidor faz:

1. Faz as conferências da tabela, nessa ordem.
2. Cria a sala com 2 assentos (1x1) ou 4 (2x2), todos vazios, e grava o criador como dono.
3. Senta o criador no assento 0, com o nome que vem no token, e começa a contar a presença dele (seção 6.5).
4. Responde 201 com a sala. A tela abre a sala de espera com essa resposta.

### 3.4 `GET /api/lobby/salas/{id}`

Responde a sala para qualquer usuário logado, sentado nela ou não. É o que faz o link de convite funcionar (seção 6.3).

Resposta: **200** com a sala no formato da seção 4. Uma sala encerrada também responde 200, com `"status": "encerrada"` (seção 6.4).

| Erro | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Sala que nunca existiu | 404 | `sala_nao_encontrada` |

O que o servidor faz:

1. Confere o token.
2. Aplica a regra de presença (seção 6.5).
3. Busca a sala. Se ela não existe, responde 404.
4. Se quem pediu está sentado nela e a sala está `"aguardando"`, renova a presença dele.
5. Responde 200 com a sala.

A tela trata qualquer 404 desta rota como "a sala acabou" e volta para a lista com aviso. Por isso, uma rota que não existe (caminho errado no Nginx, por exemplo) também tira o jogador da sala de espera.

### 3.5 `POST /api/lobby/salas/{id}/entrar`

Serve para entrar na sala e para trocar de assento: se o usuário já está sentado nela, ele passa para o assento pedido, e o antigo fica vago.

```json
{"assento": 1}
```

`assento` é um número de 0 a 1 no 1x1, ou de 0 a 3 no 2x2.

Resposta: **200** com a sala atualizada. Se o usuário pediu o assento em que já está, responde 200 sem mudar nada.

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Corpo sem `assento`, ou `assento` que não é número | 422 | `dados_invalidos` |
| Sala inexistente ou encerrada | 404 | `sala_nao_encontrada` |
| Sala em partida | 409 | `partida_ja_iniciada` |
| `assento` fora da sala | 422 | `dados_invalidos` ("Assento inválido.") |
| Sala sem vaga, para quem não está nela | 409 | `sala_cheia` |
| Assento pedido ocupado | 409 | `assento_ocupado` |
| Quem não está na sala já está sentado em outra sala aberta | 409 | `ja_esta_em_outra_sala` |

"Sala cheia" vem antes de "assento ocupado": numa sala cheia, quem está de fora sempre recebe `sala_cheia`.

O que o servidor faz:

1. Faz as conferências da tabela, nessa ordem.
2. Se o usuário já está na sala, esvazia o assento antigo. Se ele é o dono, continua dono.
3. Senta o usuário no assento pedido, com o nome do token, e começa a contar a presença dele.
4. Responde 200 com a sala.

### 3.6 `POST /api/lobby/salas/{id}/sair`

Sem corpo. Tira o usuário da sala. **Se ele é o dono, a sala é encerrada** (seção 6.4).

Resposta: **200** com a sala atualizada. Quando o dono sai, a resposta já vem com `"status": "encerrada"`:

```json
{
  "id": "20c3da2c-0ce0-4ce4-bb10-cee609f18554",
  "formato": "1x1",
  "dono_id": "u-beto",
  "status": "encerrada",
  "partida_id": null,
  "assentos": [
    {"assento": 0, "usuario_id": null, "nome": null, "bot": false},
    {"assento": 1, "usuario_id": null, "nome": null, "bot": false}
  ]
}
```

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Sala inexistente ou encerrada | 404 | `sala_nao_encontrada` |
| Sala em partida | 409 | `partida_ja_iniciada` |
| O usuário não está sentado na sala | 409 | `nao_esta_na_sala` |

A tela não lê a resposta: volta para a lista. Ela também volta para a lista quando recebe 404 ou 409 aqui, porque nos dois casos o jogador já não está na sala. Com outro erro (500, sem rede), mostra o aviso e continua na sala.

### 3.7 `POST /api/lobby/salas/{id}/bot`

Só o dono. Põe um bot num assento vago.

```json
{"assento": 2, "nivel": "padrao"}
```

A tela sempre manda `"nivel": "padrao"`.

Resposta: **200** com a sala atualizada. O bot ocupa o assento com `usuario_id` nulo, `bot` verdadeiro e o nome "Bot 1", "Bot 2"..., com o menor número ainda livre na sala:

```json
{"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true}
```

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Corpo sem `assento` | 422 | `dados_invalidos` |
| Sala inexistente ou encerrada | 404 | `sala_nao_encontrada` |
| Quem pediu não é o dono | 403 | `apenas_dono` |
| Sala em partida | 409 | `partida_ja_iniciada` |
| `assento` fora da sala | 422 | `dados_invalidos` ("Assento inválido.") |
| `nivel` diferente de `"padrao"` | 422 | `dados_invalidos` ("Nível de bot inválido.", P7) |
| Assento ocupado | 409 | `assento_ocupado` |

O nível não aparece na sala, mas o servidor precisa guardá-lo: ele vai no evento `bot.solicitado` (seção 6.6).

### 3.8 `DELETE /api/lobby/salas/{id}/assentos/{assento}`

Só o dono. Tira o bot ou o jogador do assento, que fica vago. Esta rota faz parte do contrato, por decisão do grupo. Não tem corpo; o assento vai no caminho, por exemplo `DELETE /api/lobby/salas/54200ad3-e277-4d64-9ab8-eb4cebf843df/assentos/1`.

Resposta: **200** com a sala atualizada.

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| `{assento}` que não é número | 422 | `dados_invalidos` |
| Sala inexistente ou encerrada | 404 | `sala_nao_encontrada` |
| Quem pediu não é o dono | 403 | `apenas_dono` |
| Sala em partida | 409 | `partida_ja_iniciada` |
| `{assento}` fora da sala | 422 | `dados_invalidos` ("Assento inválido.") |
| Assento já vazio | 409 | `assento_vazio` |
| O dono tentando tirar a si mesmo | 422 | `dados_invalidos` ("Para sair da sala, use o botão Sair da sala.") |

O jogador removido não recebe aviso por esta rota. A tela dele percebe no próximo `GET` da sala e volta para a lista com "Você foi removido da sala." (seção 1.4).

### 3.9 `POST /api/lobby/salas/{id}/iniciar`

Só o dono, com todos os assentos ocupados. Sem corpo.

Resposta de sucesso, com status **200**:

```json
{"partida_id": "teste-c98e3107-b801-4d67-afe0-ee24d2e5cff3"}
```

O dono vai direto para `mesa.html?partida={partida_id}`. Sem `partida_id` na resposta, a tela abre `mesa.html?partida=undefined`.

Os outros jogadores vão para a mesa quando o `GET` da sala trouxer `"status": "em_partida"` e o mesmo `partida_id`:

```json
{
  "id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "formato": "2x2",
  "dono_id": "u-ana",
  "status": "em_partida",
  "partida_id": "teste-c98e3107-b801-4d67-afe0-ee24d2e5cff3",
  "assentos": [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": false},
    {"assento": 1, "usuario_id": null, "nome": "Bot 2", "bot": true},
    {"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true},
    {"assento": 3, "usuario_id": null, "nome": "Bot 3", "bot": true}
  ]
}
```

| Erro, na ordem em que é conferido | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Sala inexistente ou encerrada | 404 | `sala_nao_encontrada` |
| Quem pediu não é o dono | 403 | `apenas_dono` |
| Sala já em partida | 409 | `partida_ja_iniciada` |
| Algum assento vago | 409 | `sala_incompleta` |
| O Game não respondeu | 503 | `game_indisponivel` (P1) |

O que o servidor faz (detalhes na seção 6.6):

1. Faz as conferências da tabela, nessa ordem.
2. Pede a partida ao Game, em `POST /interno/partidas`, e recebe o `partida_id`.
3. Grava `"status": "em_partida"` e o `partida_id` na sala.
4. Publica um `bot.solicitado` para cada assento de bot.
5. Responde 200 com o `partida_id`.

### 3.10 `GET /api/ranking`

Resposta: **200** com uma lista de linhas no formato da seção 4.4. Pelas regras do grupo (seção 6.7):

- Vêm os 10 primeiros, em ordem de vitórias.
- Se o usuário logado está abaixo do 10º, a linha dele vem no fim, como 11ª.
- Quem nunca jogou não aparece. Sem nenhuma partida registrada, a resposta é `[]`.
- Empate em vitórias divide a posição.

```json
[
  {"posicao": 1, "usuario_id": "u-carla", "nome": "Carla", "vitorias": 31, "partidas": 48},
  {"posicao": 2, "usuario_id": "u-joao", "nome": "João", "vitorias": 27, "partidas": 50},
  {"posicao": 2, "usuario_id": "u-maria", "nome": "Maria", "vitorias": 27, "partidas": 39},
  {"posicao": 4, "usuario_id": "u-bia", "nome": "Bia", "vitorias": 19, "partidas": 33}
]
```

Com o usuário logado em 23º lugar, a lista teria 11 itens, e o último seria a linha dele:

```json
{"posicao": 23, "usuario_id": "u-ian", "nome": "Ian", "vitorias": 3, "partidas": 9}
```

| Erro | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |

O que a tela faz com a lista:

- Mostra as 10 primeiras linhas. Das seguintes, mostra só a do usuário logado, depois de uma linha com "…"; as outras são ignoradas.
- Destaca a linha cujo `usuario_id` é o do usuário logado.
- Se o usuário não está na lista, escreve "Você entra no ranking depois da primeira partida.". Com a lista vazia, "Ninguém jogou ainda.".
- Se o pedido falhar, o painel mostra a mensagem e um botão "Tentar de novo". O resto do lobby continua funcionando, como pede o RNF07.

## 4. Formatos

### 4.1 A sala

Todas as rotas do Lobby que devolvem uma sala usam este formato.

Como ler a coluna **Obrigatório**: *Sim* quer dizer que, sem o campo, a tela quebra ou mostra informação errada; o que ela faz está na última coluna.

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `id` | texto | **Sim** | Vai na URL (`?sala=`) e nas rotas. A tela não interpreta: pode ser um UUID ou qualquer texto. |
| `formato` | texto | Sim, pelo contrato | `"1x1"` ou `"2x2"`. Aparece no título e no cartão. A quantidade de assentos a tela tira de `assentos`, e não daqui. |
| `dono_id` | texto | **Sim** | Id de quem criou a sala. Se ele faltar, ninguém vê os botões do dono, e o título diz "Sala 2x2 de outro jogador". |
| `status` | texto | **Sim** | `"aguardando"`, `"em_partida"` ou `"encerrada"`. A sala de espera só aparece com `"aguardando"`. Sem o campo, ou com outro valor e `partida_id` vazio, a tela volta para a lista com "A sala foi encerrada." |
| `partida_id` | texto ou `null` | **Sim** depois do início | `null` enquanto a sala espera. Preenchido, leva os jogadores sentados para a mesa. |
| `assentos` | lista | **Sim** | Exatamente 2 itens (1x1) ou 4 (2x2), em ordem de assento. Com outra quantidade, a sala de espera quebra: a tela mostra "Algo deu errado. Tente de novo." e um erro no console. Na lista, o cartão ainda aparece. |

### 4.2 Cada assento

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `assento` | inteiro | **Sim** | 0 e 1 no 1x1; de 0 a 3 no 2x2. Define o time e o lugar na mesa. Sem ele, o assento é desenhado fora de posição. |
| `usuario_id` | texto ou `null` | **Sim** | Id do jogador sentado. `null` para assento vazio e para bot. |
| `nome` | texto ou `null` | **Sim** | Nome na plaquinha. Jogador: o nome do token. Bot: "Bot 1", "Bot 2"... Assento vazio: `null`. |
| `bot` | booleano | **Sim** | `true` mostra o selo "BOT". Como o bot tem `usuario_id: null`, é o `bot: true` que faz a tela ver o assento como ocupado: sem ele, o bot aparece como vaga. |

Cada assento está sempre num destes três estados:

| Estado | `usuario_id` | `nome` | `bot` |
|---|---|---|---|
| Vazio | `null` | `null` | `false` |
| Jogador | id do usuário | nome do token | `false` |
| Bot | `null` | `"Bot 1"`, `"Bot 2"`... | `true` |

### 4.3 Exemplo completo

Sala 2x2 da Ana. O Beto está no assento 1, um bot no assento 2, e o assento 3 está vago:

```json
{
  "id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "formato": "2x2",
  "dono_id": "u-ana",
  "status": "aguardando",
  "partida_id": null,
  "assentos": [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": false},
    {"assento": 1, "usuario_id": "u-beto", "nome": "Beto", "bot": false},
    {"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true},
    {"assento": 3, "usuario_id": null, "nome": null, "bot": false}
  ]
}
```

Com essa sala, a tela da Ana (dona, assento 0) mostra:

- Ana embaixo, com "(você)" e "DONO"; Beto à direita e o Bot 1 em frente, cada um com o botão "Remover"; à esquerda, a vaga do time B, com "Trocar para cá" e "Adicionar bot".
- No centro, "3 de 4 jogadores" e "Falta 1 jogador".
- Na barra de baixo, "Complete a mesa com jogadores ou bots para iniciar." e o botão "Iniciar partida" desabilitado.

A mesma sala, na tela do Beto (assento 1):

- Beto embaixo; o Bot 1 à direita; a vaga em frente, com "Trocar para cá", porque é o lugar do parceiro dele, no time B; Ana à esquerda, com "DONO".
- Nenhum botão de dono. A barra diz "Aguardando o dono iniciar…".

### 4.4 A linha do ranking

| Campo | Tipo | Obrigatório | Valores e uso pela tela |
|---|---|---|---|
| `posicao` | inteiro | **Sim** | Mostrada como "1º", "2º"... Empates repetem o número (seção 6.7). Sem ela, aparece "undefinedº". |
| `usuario_id` | texto | **Sim** | Destaca a linha do usuário logado e acha a linha dele depois das 10 primeiras. |
| `nome` | texto | **Sim** | Nome mostrado. |
| `vitorias` | inteiro | **Sim** | Sem ele, aparece "undefined". |
| `partidas` | inteiro | **Sim** | Partidas jogadas, contando vitórias e derrotas. Sem ele, aparece "undefined". |

A tela não reordena a lista: mostra na ordem em que ela chega.

## 5. Erros

### 5.1 Formato

Todo erro é uma resposta com status HTTP de erro e este corpo, igual ao do Auth:

```json
{"erro": "sala_cheia", "mensagem": "A sala está cheia."}
```

- **`mensagem`** é o texto que a tela mostra, exatamente como veio, num aviso no pé da tela. Escreva para o jogador: em português, curta, sem nomes internos.
- **`erro`** é o código fixo, para programas. A tela do lobby não lê o código. Ela olha só o status, em três casos (seção 5.3).

O FastAPI, sem ajuste, responde erros no formato dele (`{"detail": ...}`), como explica o guia do login na seção 4.4. O exemplo da seção 8 troca esse formato pelo do contrato com dois tratadores: um para os erros de regra e outro para o corpo fora do formato.

### 5.2 Códigos

Os códigos e as mensagens são os do mock que a tela usava antes dos serviços, definitivos por decisão do grupo. A tabela traz também os dois de token, que seguem o guia do login (P19), e o `game_indisponivel`, proposta deste guia (P1).

| `erro` | Status | `mensagem` | Rotas |
|---|---|---|---|
| `sala_nao_encontrada` | 404 | "Sala não encontrada. Ela pode ter sido encerrada." | Todas com `{id}` |
| `sala_cheia` | 409 | "A sala está cheia." | entrar |
| `assento_ocupado` | 409 | "Este assento já está ocupado." | entrar, bot |
| `assento_vazio` | 409 | "Este assento já está vazio." | `DELETE` |
| `apenas_dono` | 403 | "Só o dono da sala pode fazer isso." | bot, `DELETE`, iniciar |
| `sala_incompleta` | 409 | "A partida só começa com todos os assentos ocupados." | iniciar |
| `partida_ja_iniciada` | 409 | "A partida desta sala já começou." | entrar, sair, bot, `DELETE`, iniciar |
| `ja_esta_em_outra_sala` | 409 | "Você já está em outra sala. Saia dela antes de entrar em outra." | criar, entrar |
| `nao_esta_na_sala` | 409 | "Você não está nesta sala." | sair |
| `dados_invalidos` | 422 | Depende do caso: "Formato de sala inválido.", "Assento inválido.", "Para sair da sala, use o botão Sair da sala.", "Nível de bot inválido." (P7) ou, para corpo fora do formato, "Dados inválidos." | criar, entrar, bot, `DELETE` |
| `token_invalido` | 401 | "Sessão inválida. Entre de novo." | Todas |
| `token_expirado` | 401 | "Sua sessão expirou. Entre de novo." | Todas |
| `game_indisponivel` | 503 | "Não foi possível iniciar a partida agora. Tente de novo em instantes." | iniciar (P1) |

A ordem das conferências em cada rota (seção 3) é a mesma que o mock da tela seguia. Ela importa: decide qual erro o jogador vê quando há mais de um problema ao mesmo tempo. O token é sempre conferido primeiro.

### 5.3 O que a tela faz com cada resposta

| O que chega | O que a tela faz |
|---|---|
| Erro com `mensagem`, numa ação | Mostra a mensagem por 6 segundos, libera os botões e pede os dados de novo na hora. |
| Erro com `mensagem`, na atualização periódica | Mostra a mensagem e continua tentando a cada 3 segundos. O aviso some quando uma atualização dá certo. |
| Erro sem `mensagem` (outro formato, ou corpo que não é JSON) | Mostra "Não foi possível concluir a operação (erro 422).", com o número do status, ou, de 500 a 599, "O servidor está indisponível no momento. Tente de novo em instantes." |
| Nenhuma resposta: serviço parado ou mais de 10 segundos de espera | Mostra "Não foi possível conectar ao servidor. Verifique sua conexão e tente de novo em instantes." |
| 401, em qualquer rota | Apaga a sessão e volta para a tela de login, sem aviso no lobby. |
| 404 no `GET /api/lobby/salas/{id}` | Volta para a lista com "A sala foi encerrada.", ou com a `mensagem` do servidor se a sala nem chegou a abrir. |
| 404 ou 409 no `POST .../sair` | Volta para a lista, como se a saída tivesse dado certo. |

## 6. Regras

### 6.1 Token e identidade

- O Lobby e o Ranking conferem o JWT sozinhos, com o segredo compartilhado (`JWT_SEGREDO`), sem chamar o Auth (RNF06). A conferência é a mesma do `GET /api/auth/me` do guia do login (seção 6.6 de lá).
- O `sub` do token é o id do usuário. Ele tem que ser igual ao `usuario.id` que o login devolveu: é com esse valor que a tela acha o próprio assento e descobre se é dona da sala.
- O nome que vai no assento é o campo `nome` do token. O Lobby não consulta o Auth (P16).
- O token vai em todas as rotas, inclusive nos `GET`. Sem token válido, a resposta é 401.

### 6.2 Dono, assentos e times

| Ação | Quem pode | Condição |
|---|---|---|
| Ver a lista e qualquer sala | Qualquer usuário logado | Nenhuma |
| Criar sala | Qualquer usuário logado | Não estar sentado em outra sala aberta |
| Entrar num assento vago | Qualquer usuário logado | Idem, a menos que seja uma troca de assento na mesma sala |
| Sair | Quem está sentado na sala | A sala não estar em partida |
| Pôr um bot num assento vago | Só o dono | A sala estar `"aguardando"` |
| Tirar bot ou jogador de um assento | Só o dono | Não pode tirar a si mesmo; para isso existe o `/sair` |
| Iniciar a partida | Só o dono | Todos os assentos ocupados |

- O dono é quem criou a sala (`dono_id`). Ele continua dono quando troca de assento.
- No 1x1, os assentos são 0 e 1; no 2x2, de 0 a 3. Pelo documento de contratos, 0 e 2 formam o time A, e 1 e 3 o time B, e a ordem de jogo segue a numeração. Trocar de assento é trocar de time (RF05).
- Bot no assento: `usuario_id` nulo, `bot` verdadeiro e o nome "Bot 1", "Bot 2"..., com o menor número ainda não usado na sala. Se o "Bot 1" sair, o próximo bot volta a ser "Bot 1".

### 6.3 Uma sala aberta por vez e o link de convite

- Um usuário só pode estar sentado em uma sala `"aguardando"` por vez. Criar ou entrar em outra responde 409 `ja_esta_em_outra_sala`. A troca de assento dentro da mesma sala não conta.
- Salas em partida e salas encerradas não contam: quem acabou de jogar pode criar outra sala, mesmo que a anterior continue `"em_partida"`.
- `GET /api/lobby/salas/{id}` responde também a quem não está na sala. Quem recebe o link `lobby.html?sala={id}` vê a mesa e escolhe a vaga, com `POST .../entrar`.

### 6.4 Dono sai: sala encerrada

- Quando o dono sai, pelo `/sair`, pela regra de presença ou pelo logout, a sala passa a ter `"status": "encerrada"`.
- A sala encerrada some da lista. O `GET` dela continua respondendo 200, com o status novo. É assim que a tela dos outros jogadores descobre e volta para a lista com "A sala foi encerrada.".
- Para as ações (entrar, sair, bot, `DELETE`, iniciar), uma sala encerrada responde 404 `sala_nao_encontrada`, a mesma resposta de uma sala que não existe (P8).
- Os jogadores que estavam nela ficam livres para entrar em outra sala.

### 6.5 Presença

Regra do grupo: **se o servidor ficar 60 segundos sem receber `GET /api/lobby/salas/{id}` de um jogador sentado numa sala com status `"aguardando"`, ele remove esse jogador. Se for o dono, a sala é encerrada.**

O prazo é bem maior que os 3 segundos entre os pedidos porque os navegadores reduzem a frequência dos timers (`setTimeout`) em abas ocultas: com a aba em segundo plano, o pedido seguinte pode sair muito depois dos 3 segundos. Com 60 segundos, quem só trocou de aba não perde o assento.

Como aplicar:

- Guarde, para cada jogador sentado, a hora do último `GET` da sala feito por ele (`visto_em`).
- O prazo começa quando ele senta: ao criar a sala, ao entrar e ao trocar de assento (P9).
- Só o `GET` da sala renova o prazo. Bots não entram na regra, porque nunca pedem a sala.
- A conferência pode rodar no começo de cada requisição, como no exemplo da seção 8, ou numa tarefa que roda a cada poucos segundos. Para a tela, o resultado é o mesmo.
- Tirar alguém por ausência é igual ao `/sair`: o assento fica vago e, se era o dono, a sala é encerrada.

Com a tela de hoje:

- Quem está na sala de espera pede a sala a cada 3 segundos e fica bem dentro do prazo.
- Com a aba oculta, a sala de espera continua pedindo a sala, no ritmo que o navegador permitir. Se mesmo assim passar do prazo, o jogador sai da sala, e o dono encerra a sala. Quando a aba volta, a tela mostra "Você foi removido da sala." ou "A sala foi encerrada.".
- Quem está sentado numa sala, mas com a lista aberta no lugar da sala, sai depois de 60 segundos: o `GET` da lista não renova a presença.
- Fechar a aba ou perder a conexão tem o mesmo efeito, e é para isso que a regra existe.

### 6.6 Início da partida: o Game e o `bot.solicitado`

Esta seção vem do documento de contratos, e não do código da tela. A tela não enxerga nada disso: para ela bastam a resposta `{"partida_id"}` e o `GET` da sala com `"status": "em_partida"`.

Ao receber um `POST .../iniciar` válido, o Lobby:

1. **Pede a partida ao Game.** Pelo documento, é uma rota interna, fora do Nginx: `POST /interno/partidas` no Game, chamada pelo Lobby com o `sala_id` e a lista de assentos (`usuario_id`, `nome`, `bot`), devolvendo o `partida_id`. O endereço é o da rede interna do Docker Compose, como `http://game:8000`. Os nomes `assentos` e `assento`, no corpo abaixo, são proposta deste guia: o documento não os define, e o Game precisa saber o número de cada assento para montar os times (P2).

```json
{
  "sala_id": "54200ad3-e277-4d64-9ab8-eb4cebf843df",
  "assentos": [
    {"assento": 0, "usuario_id": "u-ana", "nome": "Ana", "bot": false},
    {"assento": 1, "usuario_id": "u-beto", "nome": "Beto", "bot": false},
    {"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true},
    {"assento": 3, "usuario_id": null, "nome": "Bot 2", "bot": true}
  ]
}
```

Resposta esperada do Game: `{"partida_id": "..."}`. É com essa lista que o Game descobre em que assento está cada jogador que se conecta à mesa ([guia da mesa](guia-backend-mesa.md), seção 3.2).

2. **Grava** `"status": "em_partida"` e o `partida_id` na sala.

3. **Publica um `bot.solicitado` para cada bot.** Pelo documento, ele é publicado pelo Lobby logo depois de receber o `partida_id`, um para cada assento ocupado por bot, com os campos `partida_id`, `assento` e `nivel`; o bot então se conecta ao WebSocket da partida com um token de serviço. O evento vai para o Redis Streams; o formato da mensagem é proposta deste guia (seção 7.4, P3).

4. **Responde** `{"partida_id": "..."}` ao dono.

Se o Game não responder, o Lobby responde 503 `game_indisponivel`, e a sala continua `"aguardando"`: o dono pode tentar de novo (P1). Se a publicação no Redis falhar depois de a partida existir, os bots não chegam à mesa (P13).

O documento lista ainda dois eventos que o Lobby recebe: `partida.criada` (do Game, com `partida_id` e `sala_id`) e `partida.finalizada` (do Game, para o Lobby e o Ranking). A tela não depende de nenhum dos dois, e o documento não diz o que o Lobby faz com eles (P12).

### 6.7 Ranking

Regras do grupo:

- `GET /api/ranking` devolve os 10 primeiros e, se o usuário logado estiver fora deles, também a linha dele.
- Quem nunca jogou não aparece.
- Empates em vitórias dividem a mesma posição.

Como aplicar:

- A fonte é o evento `partida.finalizada`, que o Game publica no fim de cada partida. Pelo documento de contratos, ele traz `partida_id`, `sala_id`, `formato`, `times` (os jogadores de cada time), `vencedor_time`, `placar_final` e `encerrada_em`. O Ranking só recebe eventos: nenhum serviço o chama para registrar resultado.
- Para cada jogador da partida, some 1 em `partidas` e, se o time dele for o `vencedor_time`, 1 em `vitorias`. Bots não entram, porque não têm `usuario_id` (P4, P14).
- O mesmo evento pode chegar mais de uma vez (seção 7.4). Guarde os `partida_id` já contados e ignore os repetidos.
- Posição: quem tem mais vitórias fica na frente. Quem empata recebe a mesma posição, e a seguinte pula as que foram divididas: 1, 2, 2, 4. É o que o `RANK()` do Postgres faz (seção 7.3; P5).
- "Os 10 primeiros" são as 10 primeiras linhas nessa ordem. Dentro de um empate, a ordem é alfabética pelo nome (P5, P11).

### 6.8 Pedidos ao mesmo tempo

Dois jogadores podem clicar no mesmo assento no mesmo instante. Se o servidor conferir "está vago?" para os dois antes de gravar, os dois sentam no mesmo lugar.

- Faça cada alteração de sala numa transação que trava a linha da sala (`SELECT ... FOR UPDATE`, seção 7.2). O segundo pedido espera o primeiro terminar e então recebe `assento_ocupado` ou `sala_cheia`.
- A regra de uma sala por vez envolve salas diferentes: duas abas do mesmo usuário criando salas ao mesmo tempo passariam as duas. Trave também pelo usuário, com `pg_advisory_xact_lock` (seção 7.2).
- O exemplo da seção 8 usa uma trava só, na memória, para o serviço inteiro. Isso só funciona com um processo: rode o Uvicorn sem `--workers` (P18).

## 7. Banco e eventos

O SQL desta seção segue a documentação do Postgres e foi conferido só quanto à sintaxe, com o analisador do próprio Postgres (pacote `pglast`). Ele não foi executado num banco, porque não há Postgres nesta máquina. Confira ao criar as tabelas.

### 7.1 Tabelas do Lobby

```sql
CREATE TABLE salas (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    formato    TEXT        NOT NULL CHECK (formato IN ('1x1', '2x2')),
    dono_id    TEXT        NOT NULL,
    status     TEXT        NOT NULL DEFAULT 'aguardando'
                           CHECK (status IN ('aguardando', 'em_partida', 'encerrada')),
    partida_id TEXT,
    criada_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assentos (
    sala_id    UUID        NOT NULL REFERENCES salas (id),
    assento    SMALLINT    NOT NULL CHECK (assento BETWEEN 0 AND 3),
    usuario_id TEXT,
    nome       VARCHAR(20),
    bot        BOOLEAN     NOT NULL DEFAULT false,
    nivel      TEXT,
    visto_em   TIMESTAMPTZ,
    PRIMARY KEY (sala_id, assento)
);
```

- `dono_id` e `usuario_id` são `TEXT` porque vêm do `sub` do token, que é texto. Elas não apontam para a tabela de usuários: essa tabela fica no banco do Auth, e cada serviço só acessa o próprio banco (RNF01).
- `nivel` e `visto_em` são de uso interno e não vão na resposta.
- Ao criar a sala, insira as 2 ou 4 linhas de `assentos` na mesma transação.

### 7.2 Consultas e travas

Lista de salas abertas (agrupe as linhas por sala no Python):

```sql
SELECT s.id, s.formato, s.dono_id, s.status, s.partida_id, a.assento, a.usuario_id, a.nome, a.bot
FROM salas s JOIN assentos a ON a.sala_id = s.id
WHERE s.status = 'aguardando'
ORDER BY s.criada_em, a.assento;
```

Toda alteração (criar, entrar, sair, bot, `DELETE`, iniciar) roda numa transação que começa assim:

```sql
-- 1. Trava pelo usuário ($1 = usuario_id): dois pedidos dele esperam um pelo outro,
--    o que protege a regra de uma sala por vez.
SELECT pg_advisory_xact_lock(hashtext($1));

-- 2. Trava a sala ($1 = id da sala): outro pedido para a mesma sala espera esta
--    transação terminar. Não precisa no criar, porque a sala ainda não existe.
SELECT id, formato, dono_id, status, partida_id FROM salas WHERE id = $1 FOR UPDATE;
```

As duas travas são soltas sozinhas no fim da transação (commit ou rollback).

Outras consultas usadas pelas regras:

```sql
-- Sala aberta em que o usuário está sentado (regra de uma sala por vez)
SELECT a.sala_id
FROM assentos a JOIN salas s ON s.id = a.sala_id
WHERE s.status = 'aguardando' AND a.usuario_id = $1;

-- Sentar um jogador: o prazo da presença começa agora
UPDATE assentos
SET usuario_id = $3, nome = $4, bot = false, nivel = NULL, visto_em = now()
WHERE sala_id = $1 AND assento = $2;

-- GET da sala por quem está sentado nela: renova a presença
UPDATE assentos SET visto_em = now() WHERE sala_id = $1 AND usuario_id = $2;

-- Jogadores ausentes há mais de 60 segundos. Para cada um, faça o mesmo que o /sair.
SELECT a.sala_id, a.assento, a.usuario_id, s.dono_id
FROM assentos a JOIN salas s ON s.id = a.sala_id
WHERE s.status = 'aguardando'
  AND a.usuario_id IS NOT NULL
  AND a.visto_em < now() - interval '60 seconds';
```

- Nunca monte o SQL juntando textos com dados do usuário. Use sempre os parâmetros da biblioteca (`$1`, `%s`, `:id`, conforme a biblioteca).
- Confirme a transação (commit) antes de responder. O próximo `GET` da tela chega em até 3 segundos e precisa enxergar a mudança.
- O `now()` do Postgres é a hora do começo da transação. Para comparar com 60 segundos, isso basta.

### 7.3 Tabelas e consultas do Ranking

```sql
CREATE TABLE jogadores (
    usuario_id TEXT        PRIMARY KEY,
    nome       VARCHAR(20) NOT NULL,
    vitorias   INTEGER     NOT NULL DEFAULT 0,
    partidas   INTEGER     NOT NULL DEFAULT 0
);

CREATE TABLE partidas_contadas (
    partida_id TEXT        PRIMARY KEY,
    contada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Para cada `partida.finalizada`, numa transação só:

```sql
-- 1. Marca a partida como contada. Se nenhuma linha foi inserida, o evento é repetido:
--    desfaça a transação e pare aqui.
INSERT INTO partidas_contadas (partida_id) VALUES ($1) ON CONFLICT DO NOTHING;

-- 2. Para cada jogador da partida que não é bot: $3 vale 1 para quem venceu e 0 para quem perdeu.
INSERT INTO jogadores (usuario_id, nome, vitorias, partidas) VALUES ($1, $2, $3, 1)
ON CONFLICT (usuario_id) DO UPDATE
SET nome = EXCLUDED.nome,
    vitorias = jogadores.vitorias + EXCLUDED.vitorias,
    partidas = jogadores.partidas + 1;
```

Para o `GET /api/ranking` ($1 = id do usuário logado):

```sql
WITH classificacao AS (
    SELECT RANK() OVER (ORDER BY vitorias DESC) AS posicao,
           ROW_NUMBER() OVER (ORDER BY vitorias DESC, lower(nome)) AS linha,
           usuario_id, nome, vitorias, partidas
    FROM jogadores
)
SELECT posicao, usuario_id, nome, vitorias, partidas
FROM classificacao
WHERE linha <= 10 OR usuario_id = $1
ORDER BY linha;
```

- `RANK()` dá a mesma posição para quem empata e pula as posições divididas (1, 2, 2, 4).
- `ROW_NUMBER()` numera as linhas de 1 em diante, sem repetir. É ele que corta as 10 primeiras.
- Quem nunca jogou não tem linha em `jogadores`, então não aparece.

### 7.4 Redis Streams

Pelo documento de contratos, os eventos são publicados no Redis Streams: quem publica não espera resposta, e, se o consumidor estiver fora do ar, o evento fica na fila até ele voltar.

O Redis Streams em poucas palavras:

- Um stream é uma fila gravada no Redis. Quem publica acrescenta mensagens com `XADD`.
- Quem consome lê como parte de um grupo, com `XREADGROUP`, e confirma cada mensagem processada com `XACK`. O grupo lembra até onde já leu.
- Uma mensagem lida e não confirmada (o serviço caiu no meio) fica pendente e é lida de novo quando ele volta. Por isso o Ranking ignora partidas repetidas.

Proposta deste guia para o formato (P3):

- Um stream por evento, com o nome do evento: `bot.solicitado`, `partida.criada`, `partida.finalizada`.
- Cada mensagem com um campo só, `dados`, com o evento em JSON. Assim números e listas chegam como números e listas.
- Um grupo por serviço que consome: `ranking` no Ranking, `lobby` no Lobby, `bots` no Bots.

A publicação do `bot.solicitado` já está no exemplo 8.1 (função `publicar_evento`), e o consumo do `partida.finalizada` está no 8.3. O código de Redis deste guia foi testado com o fakeredis 2.40, um Redis simulado em Python, e não com um servidor Redis de verdade, que não existe nesta máquina.

## 8. Exemplo mínimo em FastAPI

Os trechos abaixo foram testados com Python 3.14, FastAPI 0.143, Uvicorn 0.54 e PyJWT 2.15; o 8.3, também com redis 8.1 e fakeredis 2.40. A tela real, falando com eles e não com os mocks da época, criou contas, encheu uma sala com dois jogadores e bots, iniciou a partida e mostrou o ranking usando estes exemplos junto com o do guia do login (seção 9.4).

Para rodar, salve cada código com o nome indicado numa pasta de testes, fora do repositório, e execute dentro dela, cada serviço num terminal:

```bash
pip install fastapi "uvicorn[standard]" pyjwt
uvicorn lobby:app --reload --port 8003
uvicorn ranking:app --reload --port 8004
```

- `lobby:app` quer dizer: arquivo `lobby.py`, variável `app`. Se o comando `uvicorn` não for encontrado, use `python -m uvicorn lobby:app --reload --port 8003`.
- As portas 8003 e 8004 evitam conflito com o frontend (8000) e com os exemplos dos guias da mesa (8001) e do login (8002).
- Os dados ficam na memória e somem a cada reinício. Com `--reload`, isso acontece também a cada vez que o arquivo é salvo.
- O segredo padrão é o mesmo do exemplo do Auth: um token emitido por ele vale aqui, e vice-versa.

### 8.1 Serviço Lobby: `lobby.py`

```python
# lobby.py: esqueleto do serviço Lobby. Salas, assentos, bots, presença e início da partida.
# As salas ficam na memória e somem quando o servidor reinicia; no serviço real ficam no
# Postgres (seção 7). O token é o JWT emitido pelo Auth (guia do login, seção 6).
import json
import os
import threading
import time
import urllib.request
import uuid

import jwt  # pacote PyJWT
from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

# O mesmo segredo do Auth: é com ele que o Lobby confere o token sozinho.
JWT_SEGREDO = os.environ.get("JWT_SEGREDO", "segredo-de-teste-troque-por-um-valor-aleatorio")

# Endereços internos do Game e do Redis. Vazios, o exemplo inventa o partida_id e só escreve
# os eventos no terminal, para dar para testar sem os outros serviços.
GAME_URL = os.environ.get("GAME_URL", "")  # no Docker Compose, algo como http://game:8000
REDIS_URL = os.environ.get("REDIS_URL", "")  # no Docker Compose, algo como redis://redis:6379

ASSENTOS_POR_FORMATO = {"1x1": 2, "2x2": 4}
PRAZO_PRESENCA = 60  # segundos sem GET /salas/{id} até o jogador ser tirado da sala

# Erros: código -> (status HTTP, mensagem). Os mesmos da seção 5.2, com os de token do
# guia do login e o "game_indisponivel", que é proposta deste guia (P1).
ERROS = {
    "sala_nao_encontrada": (404, "Sala não encontrada. Ela pode ter sido encerrada."),
    "sala_cheia": (409, "A sala está cheia."),
    "assento_ocupado": (409, "Este assento já está ocupado."),
    "assento_vazio": (409, "Este assento já está vazio."),
    "apenas_dono": (403, "Só o dono da sala pode fazer isso."),
    "sala_incompleta": (409, "A partida só começa com todos os assentos ocupados."),
    "partida_ja_iniciada": (409, "A partida desta sala já começou."),
    "ja_esta_em_outra_sala": (409, "Você já está em outra sala. Saia dela antes de entrar em outra."),
    "nao_esta_na_sala": (409, "Você não está nesta sala."),
    "dados_invalidos": (422, "Dados inválidos."),
    "token_invalido": (401, "Sessão inválida. Entre de novo."),
    "token_expirado": (401, "Sua sessão expirou. Entre de novo."),
    "game_indisponivel": (503, "Não foi possível iniciar a partida agora. Tente de novo em instantes."),
}

app = FastAPI()
rotas = APIRouter(prefix="/api/lobby")  # todas as rotas abaixo começam com /api/lobby
bearer = HTTPBearer(auto_error=False)

# "Banco" de mentira: id da sala -> sala. Além dos campos do contrato, cada assento guarda o
# nível do bot e a hora do último GET do jogador (presença), que não vão para a resposta.
SALAS: dict[str, dict] = {}

# As rotas usam "def" comum, e o FastAPI atende várias requisições ao mesmo tempo. A trava
# faz uma alteração por vez: sem ela, duas pessoas poderiam sentar no mesmo assento.
trava = threading.Lock()

if REDIS_URL:
    import redis  # pacote redis; só é preciso com o Redis no ar

    cliente_redis = redis.Redis.from_url(REDIS_URL)


class ErroLobby(Exception):
    """Erro de regra. O tratador logo abaixo transforma em resposta no formato do contrato."""

    def __init__(self, codigo: str, mensagem: str | None = None):
        self.codigo = codigo
        self.status, mensagem_padrao = ERROS[codigo]
        self.mensagem = mensagem or mensagem_padrao


@app.exception_handler(ErroLobby)
def erro_lobby(request, exc: ErroLobby):
    return JSONResponse(status_code=exc.status, content={"erro": exc.codigo, "mensagem": exc.mensagem})


# Corpo fora do esperado (JSON quebrado, campo faltando, texto no lugar de número): o
# FastAPI responderia 422 no formato dele; aqui sai no formato do contrato.
@app.exception_handler(RequestValidationError)
def corpo_invalido(request, exc):
    return erro_lobby(request, ErroLobby("dados_invalidos"))


def usuario_logado(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Confere o token (como o GET /api/auth/me do guia do login) e devolve o usuário:
    {"id", "nome"}. O id é o "sub" do token, o mesmo "usuario.id" que a tela recebeu no login."""
    if credenciais is None:
        raise ErroLobby("token_invalido")
    try:
        conteudo = jwt.decode(
            credenciais.credentials,
            JWT_SEGREDO,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise ErroLobby("token_expirado")
    except jwt.InvalidTokenError:
        raise ErroLobby("token_invalido")
    return {"id": conteudo["sub"], "nome": conteudo.get("nome", "")}


# Corpo esperado em cada rota que recebe JSON.
class DadosNovaSala(BaseModel):
    formato: str


class DadosAssento(BaseModel):
    assento: int


class DadosBot(BaseModel):
    assento: int
    nivel: str = "padrao"


# ---------- Ajudantes ----------


def assento_vazio(numero: int) -> dict:
    return {"assento": numero, "usuario_id": None, "nome": None, "bot": False, "nivel": None, "visto_em": None}


def ocupado(assento: dict) -> bool:
    return assento["bot"] or assento["usuario_id"] is not None


def vagar(assento: dict) -> None:
    assento.update(assento_vazio(assento["assento"]))


def sentar(assento: dict, usuario: dict) -> None:
    # O prazo da presença começa a contar quando o jogador senta.
    assento.update(usuario_id=usuario["id"], nome=usuario["nome"], bot=False, nivel=None, visto_em=time.monotonic())


def assento_do_usuario(sala: dict, usuario_id: str) -> dict | None:
    return next((a for a in sala["assentos"] if a["usuario_id"] == usuario_id), None)


def sala_aberta_do_usuario(usuario_id: str) -> dict | None:
    """Sala "aguardando" em que o usuário está sentado. Pela regra, há no máximo uma."""
    return next((s for s in SALAS.values() if s["status"] == "aguardando" and assento_do_usuario(s, usuario_id)), None)


def nome_de_bot(sala: dict) -> str:
    """"Bot 1", "Bot 2"...: o menor número que ainda não está em uso na sala."""
    usados = {a["nome"] for a in sala["assentos"] if a["bot"]}
    numero = 1
    while f"Bot {numero}" in usados:
        numero += 1
    return f"Bot {numero}"


def tirar_da_sala(sala: dict, assento: dict) -> None:
    """Esvazia o assento de um jogador. Se ele era o dono, a sala é encerrada."""
    era_dono = assento["usuario_id"] == sala["dono_id"]
    vagar(assento)
    if era_dono:
        sala["status"] = "encerrada"


def tirar_ausentes() -> None:
    """Regra de presença: quem está sentado numa sala "aguardando" e passou 60 segundos sem
    pedir GET /salas/{id} sai da sala (se for o dono, a sala é encerrada). Bots não contam.
    Roda no começo de toda requisição, antes de qualquer outra regra."""
    agora = time.monotonic()
    for sala in SALAS.values():
        for assento in sala["assentos"]:
            if sala["status"] != "aguardando":
                break
            if assento["usuario_id"] and agora - assento["visto_em"] > PRAZO_PRESENCA:
                tirar_da_sala(sala, assento)


def buscar_sala(sala_id: str) -> dict:
    """Sala para as ações. Uma sala encerrada ainda responde ao GET, mas para as ações ela
    não existe mais."""
    sala = SALAS.get(sala_id)
    if sala is None or sala["status"] == "encerrada":
        raise ErroLobby("sala_nao_encontrada")
    return sala


def buscar_assento(sala: dict, numero: int) -> dict:
    if not 0 <= numero < len(sala["assentos"]):
        raise ErroLobby("dados_invalidos", "Assento inválido.")
    return sala["assentos"][numero]


def exigir_dono(sala: dict, usuario: dict) -> None:
    if sala["dono_id"] != usuario["id"]:
        raise ErroLobby("apenas_dono")


def exigir_aguardando(sala: dict) -> None:
    if sala["status"] != "aguardando":
        raise ErroLobby("partida_ja_iniciada")


def resposta(sala: dict) -> dict:
    """A sala no formato do contrato, sem os campos internos (nível do bot e presença). É um
    dicionário novo: o FastAPI só o transforma em JSON depois que a trava é solta."""
    return {
        "id": sala["id"],
        "formato": sala["formato"],
        "dono_id": sala["dono_id"],
        "status": sala["status"],
        "partida_id": sala["partida_id"],
        "assentos": [
            {"assento": a["assento"], "usuario_id": a["usuario_id"], "nome": a["nome"], "bot": a["bot"]}
            for a in sala["assentos"]
        ],
    }


def criar_partida_no_game(sala: dict) -> str:
    """POST /interno/partidas no Game (documento de contratos): manda o id da sala e os
    assentos e recebe o partida_id. O formato do corpo é proposta deste guia (P2)."""
    if not GAME_URL:
        return f"teste-{uuid.uuid4()}"  # sem o Game no ar: inventa um id, só para testar
    corpo = {"sala_id": sala["id"], "assentos": resposta(sala)["assentos"]}
    pedido = urllib.request.Request(
        f"{GAME_URL}/interno/partidas",
        data=json.dumps(corpo).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=5) as resposta_do_game:
            return json.load(resposta_do_game)["partida_id"]
    except (OSError, ValueError, KeyError):
        # Game fora do ar, erro HTTP, resposta que não é JSON ou sem partida_id.
        raise ErroLobby("game_indisponivel")


def publicar_evento(nome: str, dados: dict) -> None:
    """Publica um evento no Redis Streams (documento de contratos). Um stream por evento, com
    os dados em JSON no campo "dados", é proposta deste guia (P3)."""
    if not REDIS_URL:
        print("evento", nome, dados)  # sem o Redis no ar: só mostra no terminal
        return
    cliente_redis.xadd(nome, {"dados": json.dumps(dados)})


# ---------- Rotas ----------


@rotas.get("/salas")
def listar_salas(usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        return [resposta(s) for s in SALAS.values() if s["status"] == "aguardando"]


@rotas.post("/salas", status_code=201)
def criar_sala(dados: DadosNovaSala, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        if dados.formato not in ASSENTOS_POR_FORMATO:
            raise ErroLobby("dados_invalidos", "Formato de sala inválido.")
        if sala_aberta_do_usuario(usuario["id"]):
            raise ErroLobby("ja_esta_em_outra_sala")
        sala = {
            "id": str(uuid.uuid4()),
            "formato": dados.formato,
            "dono_id": usuario["id"],
            "status": "aguardando",
            "partida_id": None,
            "assentos": [assento_vazio(n) for n in range(ASSENTOS_POR_FORMATO[dados.formato])],
        }
        sentar(sala["assentos"][0], usuario)  # quem cria fica no assento 0
        SALAS[sala["id"]] = sala
        return resposta(sala)


@rotas.get("/salas/{sala_id}")
def obter_sala(sala_id: str, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = SALAS.get(sala_id)  # aqui uma sala encerrada também responde
        if sala is None:
            raise ErroLobby("sala_nao_encontrada")
        # Quem está sentado e pede a sala está presente: o prazo de 60 segundos recomeça.
        meu_assento = assento_do_usuario(sala, usuario["id"])
        if meu_assento and sala["status"] == "aguardando":
            meu_assento["visto_em"] = time.monotonic()
        return resposta(sala)


@rotas.post("/salas/{sala_id}/entrar")
def entrar(sala_id: str, dados: DadosAssento, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = buscar_sala(sala_id)
        exigir_aguardando(sala)
        destino = buscar_assento(sala, dados.assento)
        atual = assento_do_usuario(sala, usuario["id"])
        if destino is atual:
            return resposta(sala)  # já está nesse assento: nada muda
        if atual is None and all(ocupado(a) for a in sala["assentos"]):
            raise ErroLobby("sala_cheia")
        if ocupado(destino):
            raise ErroLobby("assento_ocupado")
        if atual is None and sala_aberta_do_usuario(usuario["id"]):
            raise ErroLobby("ja_esta_em_outra_sala")
        if atual is not None:
            vagar(atual)  # troca de assento: o antigo fica vago
        sentar(destino, usuario)
        return resposta(sala)


@rotas.post("/salas/{sala_id}/sair")
def sair(sala_id: str, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = buscar_sala(sala_id)
        exigir_aguardando(sala)
        atual = assento_do_usuario(sala, usuario["id"])
        if atual is None:
            raise ErroLobby("nao_esta_na_sala")
        tirar_da_sala(sala, atual)  # se for o dono, a sala é encerrada
        return resposta(sala)


@rotas.post("/salas/{sala_id}/bot")
def colocar_bot(sala_id: str, dados: DadosBot, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = buscar_sala(sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        alvo = buscar_assento(sala, dados.assento)
        if dados.nivel != "padrao":
            raise ErroLobby("dados_invalidos", "Nível de bot inválido.")
        if ocupado(alvo):
            raise ErroLobby("assento_ocupado")
        alvo.update(nome=nome_de_bot(sala), bot=True, nivel=dados.nivel)  # usuario_id fica null
        return resposta(sala)


@rotas.delete("/salas/{sala_id}/assentos/{assento}")
def liberar_assento(sala_id: str, assento: int, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = buscar_sala(sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        alvo = buscar_assento(sala, assento)
        if not ocupado(alvo):
            raise ErroLobby("assento_vazio")
        if alvo["usuario_id"] == usuario["id"]:
            raise ErroLobby("dados_invalidos", "Para sair da sala, use o botão Sair da sala.")
        vagar(alvo)
        return resposta(sala)


@rotas.post("/salas/{sala_id}/iniciar")
def iniciar(sala_id: str, usuario: dict = Depends(usuario_logado)):
    with trava:
        tirar_ausentes()
        sala = buscar_sala(sala_id)
        exigir_dono(sala, usuario)
        exigir_aguardando(sala)
        if not all(ocupado(a) for a in sala["assentos"]):
            raise ErroLobby("sala_incompleta")
        # No exemplo a trava vale para todas as salas, então a espera pelo Game segura as
        # outras requisições. No serviço real a trava é só a da sala (seção 7.2).
        partida_id = criar_partida_no_game(sala)
        sala["status"] = "em_partida"
        sala["partida_id"] = partida_id
        # Um bot.solicitado para cada assento de bot, logo depois de receber o partida_id.
        for alvo in sala["assentos"]:
            if alvo["bot"]:
                publicar_evento("bot.solicitado", {"partida_id": partida_id, "assento": alvo["assento"], "nivel": alvo["nivel"]})
        return {"partida_id": partida_id}


app.include_router(rotas)
```

Para quem nunca usou FastAPI, o essencial deste código:

- Toda regra que falha faz `raise ErroLobby("codigo")`. O tratador `erro_lobby` transforma isso numa resposta no formato do contrato, com o status da tabela `ERROS`.
- O parâmetro `usuario: dict = Depends(usuario_logado)` faz o FastAPI conferir o token antes de chamar a rota. Sem token válido, a rota nem roda: a resposta é 401.
- `with trava:` faz uma requisição de cada vez mexer nas salas, e `tirar_ausentes()`, no começo de cada rota, aplica a regra de presença.
- `resposta(sala)` monta a sala no formato do contrato, sem os campos internos.
- Com `GAME_URL` e `REDIS_URL` vazios, o exemplo inventa o `partida_id` (`teste-...`) e escreve os eventos no terminal. Preenchidos, ele chama o Game e publica no Redis (para isso, `pip install redis`).

O que este esqueleto ainda não faz:

- Não usa banco: falta trocar o `SALAS` pelas tabelas da seção 7.
- A trava vale para o serviço inteiro e só funciona com um processo (seção 6.8).
- Não faz nada com `partida.criada` e `partida.finalizada` (P12).

### 8.2 Serviço Ranking: `ranking.py`

```python
# ranking.py: esqueleto do serviço Ranking. Conta vitórias e partidas de cada jogador a
# partir do evento partida.finalizada e responde GET /api/ranking.
# Os dados ficam na memória e somem quando o servidor reinicia; no serviço real ficam no
# Postgres (seção 7.3).
import os
import threading

import jwt  # pacote PyJWT
from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SEGREDO = os.environ.get("JWT_SEGREDO", "segredo-de-teste-troque-por-um-valor-aleatorio")
TAMANHO = 10  # linhas do topo do ranking

app = FastAPI()
rotas = APIRouter(prefix="/api/ranking")
bearer = HTTPBearer(auto_error=False)
trava = threading.Lock()

# "Banco" de mentira: usuario_id -> {"usuario_id", "nome", "vitorias", "partidas"}
JOGADORES: dict[str, dict] = {}
# Partidas já contadas. O mesmo evento pode chegar duas vezes e não pode contar em dobro.
PARTIDAS_CONTADAS: set[str] = set()


class ErroToken(Exception):
    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem


@app.exception_handler(ErroToken)
def erro_token(request, exc: ErroToken):
    return JSONResponse(status_code=401, content={"erro": exc.codigo, "mensagem": exc.mensagem})


def usuario_logado(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Confere o token e devolve o id do usuário (o "sub")."""
    if credenciais is None:
        raise ErroToken("token_invalido", "Sessão inválida. Entre de novo.")
    try:
        conteudo = jwt.decode(
            credenciais.credentials,
            JWT_SEGREDO,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise ErroToken("token_expirado", "Sua sessão expirou. Entre de novo.")
    except jwt.InvalidTokenError:
        raise ErroToken("token_invalido", "Sessão inválida. Entre de novo.")
    return conteudo["sub"]


def registrar_partida(evento: dict) -> None:
    """Aplica um evento partida.finalizada: cada jogador ganha uma partida, e quem estava no
    time vencedor ganha também uma vitória. Bots não entram, porque não têm usuario_id. O
    formato de "times" é proposta deste guia (P4)."""
    with trava:
        if evento["partida_id"] in PARTIDAS_CONTADAS:
            return  # evento repetido: essa partida já foi contada
        PARTIDAS_CONTADAS.add(evento["partida_id"])
        for nome_time, jogadores in evento["times"].items():
            for jogador in jogadores:
                if not jogador.get("usuario_id"):
                    continue  # bot
                linha = JOGADORES.setdefault(
                    jogador["usuario_id"],
                    {"usuario_id": jogador["usuario_id"], "nome": jogador["nome"], "vitorias": 0, "partidas": 0},
                )
                linha["nome"] = jogador["nome"]  # guarda o nome mais recente
                linha["partidas"] += 1
                if nome_time == evento["vencedor_time"]:
                    linha["vitorias"] += 1


def classificar() -> list[dict]:
    """Todos os jogadores em ordem de vitórias, já com a posição. Quem empata em vitórias
    divide a posição, e a posição seguinte pula: 1, 2, 2, 4. Dentro do empate, a ordem é pelo
    nome (proposta deste guia, P5)."""
    with trava:
        jogadores = sorted(JOGADORES.values(), key=lambda j: (-j["vitorias"], j["nome"].lower()))
        linhas = []
        for indice, jogador in enumerate(jogadores):
            if indice > 0 and jogador["vitorias"] == jogadores[indice - 1]["vitorias"]:
                posicao = linhas[-1]["posicao"]
            else:
                posicao = indice + 1
            linhas.append({"posicao": posicao, **jogador})  # cópia: o JSON sai depois da trava
        return linhas


@rotas.get("")  # atende em /api/ranking
def ranking(usuario_id: str = Depends(usuario_logado)):
    linhas = classificar()
    resposta = linhas[:TAMANHO]
    # Se o usuário logado está fora dos 10 primeiros, a linha dele vai no fim.
    minha = next((linha for linha in linhas[TAMANHO:] if linha["usuario_id"] == usuario_id), None)
    if minha:
        resposta.append(minha)
    return resposta


# SÓ PARA TESTE: recebe um evento partida.finalizada por HTTP, enquanto não há Game nem
# Redis. Fica fora do /api, então o Nginx não o expõe; apague no serviço real.
@app.post("/interno/teste/partida-finalizada")
def evento_de_teste(evento: dict):
    registrar_partida(evento)
    return {"ok": True}


app.include_router(rotas)
```

- `registrar_partida` é a função que o consumidor do Redis vai chamar para cada `partida.finalizada` (seção 8.3). Enquanto não há Game nem Redis, a rota de teste `/interno/teste/partida-finalizada` chama a mesma função (seção 9.3).
- `classificar` põe os jogadores em ordem e calcula as posições com empate; a rota corta as 10 primeiras e acrescenta a linha do usuário logado.
- O que ainda não faz: não usa banco (seção 7.3), e a rota de teste tem que sair no serviço real.

### 8.3 Próximo passo: ler `partida.finalizada` do Redis Streams

Acrescente este trecho ao `ranking.py`, logo antes da última linha (`app.include_router(rotas)`), e instale o pacote do Redis com `pip install redis`:

```python
# Consumidor do Redis Streams: lê o evento partida.finalizada e aplica com registrar_partida().
import json

import redis  # pacote redis

REDIS_URL = os.environ.get("REDIS_URL", "")


def consumir_eventos(cliente: redis.Redis) -> None:
    """Lê partida.finalizada sem parar. O grupo "ranking" guarda no Redis até onde o serviço já
    leu: o que chegar com ele fora do ar espera na fila. Ao começar, relê o que ficou pendente
    (lido e não confirmado antes de uma queda); depois, só os eventos novos (">")."""
    try:
        cliente.xgroup_create("partida.finalizada", "ranking", id="0", mkstream=True)
    except redis.ResponseError:
        pass  # o grupo já existe
    a_partir_de = "0"
    while True:
        lidos = cliente.xreadgroup("ranking", "ranking-1", {"partida.finalizada": a_partir_de}, count=10, block=5000)
        mensagens = [m for _stream, lista in lidos for m in lista]
        if a_partir_de == "0" and not mensagens:
            a_partir_de = ">"  # acabaram os pendentes
        for id_mensagem, campos in mensagens:
            registrar_partida(json.loads(campos[b"dados"]))
            cliente.xack("partida.finalizada", "ranking", id_mensagem)  # confirma: sai da fila


# Com o Redis no ar, o consumidor roda numa linha de execução própria, ao lado das rotas.
if REDIS_URL:
    threading.Thread(target=consumir_eventos, args=(redis.Redis.from_url(REDIS_URL),), daemon=True).start()
```

- Com `REDIS_URL` vazio, nada muda: o consumidor não começa.
- Com o Redis no ar, suba o serviço com a variável preenchida: `REDIS_URL=redis://localhost:6379 uvicorn ranking:app --port 8004`.
- Rode o Ranking com um processo só. Com `--workers`, cada processo leria em nome de `ranking-1` ao mesmo tempo (P18).

## 9. Como testar

Suba os dois exemplos da seção 8 antes de começar: o Lobby na porta 8003 e o Ranking na 8004.

Os comandos abaixo são para bash: Linux, macOS, WSL ou Git Bash. No PowerShell do Windows eles não funcionam como estão, pelo mesmo motivo explicado no guia do login (seção 9.1).

### 9.1 Tokens de teste

Os exemplos conferem o JWT com o mesmo segredo padrão do exemplo do Auth. Para testar sem o Auth, gere tokens de teste com o PyJWT, já instalado:

```bash
token() {
  python -c "import jwt, sys, time; print(jwt.encode({'sub': sys.argv[1], 'nome': sys.argv[2], 'exp': int(time.time()) + 3600}, 'segredo-de-teste-troque-por-um-valor-aleatorio', algorithm='HS256'))" "$1" "$2"
}
ANA=$(token u-ana Ana)
BETO=$(token u-beto Beto)
URL=http://localhost:8003/api/lobby/salas
JSON="Content-Type: application/json"
```

Cada token vale por uma hora. Se aparecer `token_expirado`, rode as linhas de novo.

### 9.2 Lobby com curl

**Criar uma sala**

```bash
curl -i -X POST $URL -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"formato": "2x2"}'
```

A opção `-i` mostra o status e os cabeçalhos antes do corpo:

```text
HTTP/1.1 201 Created
...
{"id":"54200ad3-e277-4d64-9ab8-eb4cebf843df","formato":"2x2","dono_id":"u-ana","status":"aguardando","partida_id":null,"assentos":[...]}
```

Guarde o id da sala numa variável:

```bash
SALA=$(curl -s $URL -H "Authorization: Bearer $ANA" | python -c "import sys, json; print(json.load(sys.stdin)[0]['id'])")
```

**Uma partida do começo ao fim**

```bash
# Beto vê a sala sem estar nela (link de convite): 200
curl -s $URL/$SALA -H "Authorization: Bearer $BETO"

# Beto entra no assento 1: 200, com ele no assento 1
curl -s -X POST $URL/$SALA/entrar -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"assento": 1}'

# Ana põe um bot no assento 2: 200, com "Bot 1" no assento 2
curl -s -X POST $URL/$SALA/bot -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 2, "nivel": "padrao"}'

# Beto tenta pôr um bot: 403 apenas_dono
curl -s -X POST $URL/$SALA/bot -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"assento": 3, "nivel": "padrao"}'

# Ana tenta iniciar com vaga: 409 sala_incompleta
curl -s -X POST $URL/$SALA/iniciar -H "Authorization: Bearer $ANA"

# Ana tira o Beto: 200, com o assento 1 vago
curl -s -X DELETE $URL/$SALA/assentos/1 -H "Authorization: Bearer $ANA"

# Ana completa com bots e inicia: 200 com o partida_id
curl -s -X POST $URL/$SALA/bot -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 1, "nivel": "padrao"}'
curl -s -X POST $URL/$SALA/bot -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 3, "nivel": "padrao"}'
curl -i -X POST $URL/$SALA/iniciar -H "Authorization: Bearer $ANA"

# A sala agora está em partida: "status":"em_partida" e o mesmo partida_id
curl -s $URL/$SALA -H "Authorization: Bearer $BETO"
```

Depois do `iniciar`, o terminal do Lobby mostra uma linha por bot, porque o `REDIS_URL` está vazio:

```text
evento bot.solicitado {'partida_id': 'teste-c98e3107-b801-4d67-afe0-ee24d2e5cff3', 'assento': 1, 'nivel': 'padrao'}
```

**Outros casos**

| Caso | Comando | Resposta esperada |
|---|---|---|
| Sem token | `curl -i $URL` | 401 `token_invalido` |
| Formato inválido | `curl -s -X POST $URL -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"formato": "3x3"}'` | 422 `dados_invalidos` |
| Corpo que não é JSON | `curl -s -X POST $URL -H "Authorization: Bearer $BETO" -H "$JSON" -d 'oi'` | 422 `dados_invalidos` |
| Sala inexistente | `curl -s $URL/nao-existe -H "Authorization: Bearer $BETO"` | 404 `sala_nao_encontrada` |
| Ação em sala em partida | `curl -s -X POST $URL/$SALA/sair -H "Authorization: Bearer $ANA"` | 409 `partida_ja_iniciada` |

Para os casos que dependem de uma sala nova, crie uma sala do Beto e guarde o id:

```bash
SALA2=$(curl -s -X POST $URL -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"formato": "1x1"}' | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
```

| Caso | Comando | Resposta esperada |
|---|---|---|
| Uma sala aberta por vez | `curl -s -X POST $URL -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"formato": "2x2"}'` | 409 `ja_esta_em_outra_sala` |
| Assento ocupado | `curl -s -X POST $URL/$SALA2/entrar -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 0}'` | 409 `assento_ocupado` |
| Assento fora da sala | `curl -s -X POST $URL/$SALA2/entrar -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 3}'` | 422 `dados_invalidos` ("Assento inválido.") |
| Dono sai | `curl -s -X POST $URL/$SALA2/sair -H "Authorization: Bearer $BETO"` | 200, com `"status":"encerrada"` |
| Sala encerrada no `GET` | `curl -s $URL/$SALA2 -H "Authorization: Bearer $ANA"` | 200, com `"status":"encerrada"` |
| Sala encerrada nas ações | `curl -s -X POST $URL/$SALA2/entrar -H "Authorization: Bearer $ANA" -H "$JSON" -d '{"assento": 1}'` | 404 `sala_nao_encontrada` |

**Presença**

```bash
SALA3=$(curl -s -X POST $URL -H "Authorization: Bearer $BETO" -H "$JSON" -d '{"formato": "1x1"}' | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
sleep 16
curl -s $URL/$SALA3 -H "Authorization: Bearer $ANA"
```

O Beto criou a sala e ficou 16 segundos sem pedi-la. A resposta mostra a sala com `"status":"encerrada"` e o assento dele vago. Pedindo a sala a cada poucos segundos com o token do Beto, ela continuaria aberta.

### 9.3 Ranking com curl

Sem Game nem Redis, os resultados entram pela rota de teste do exemplo 8.2:

```bash
curl -s -X POST http://localhost:8004/interno/teste/partida-finalizada -H "$JSON" -d '{
  "partida_id": "p1", "sala_id": "s1", "formato": "1x1",
  "times": {"A": [{"usuario_id": "u-ana", "nome": "Ana"}], "B": [{"usuario_id": "u-beto", "nome": "Beto"}]},
  "vencedor_time": "A", "placar_final": {"A": 12, "B": 7}, "encerrada_em": "2026-10-14T15:30:00Z"}'

curl -s -X POST http://localhost:8004/interno/teste/partida-finalizada -H "$JSON" -d '{
  "partida_id": "p2", "sala_id": "s2", "formato": "2x2",
  "times": {"A": [{"usuario_id": "u-caio", "nome": "Caio"}, {"usuario_id": null, "nome": "Bot 1"}],
            "B": [{"usuario_id": "u-beto", "nome": "Beto"}, {"usuario_id": "u-duda", "nome": "Duda"}]},
  "vencedor_time": "B", "placar_final": {"A": 9, "B": 12}, "encerrada_em": "2026-10-14T16:10:00Z"}'

curl -s http://localhost:8004/api/ranking -H "Authorization: Bearer $ANA"
```

Resposta, com Ana, Beto e Duda empatados em 1º lugar, o Caio em 4º e o bot de fora:

```json
[{"posicao":1,"usuario_id":"u-ana","nome":"Ana","vitorias":1,"partidas":1},{"posicao":1,"usuario_id":"u-beto","nome":"Beto","vitorias":1,"partidas":2},{"posicao":1,"usuario_id":"u-duda","nome":"Duda","vitorias":1,"partidas":1},{"posicao":4,"usuario_id":"u-caio","nome":"Caio","vitorias":0,"partidas":1}]
```

| Caso | Como testar | Resposta esperada |
|---|---|---|
| Evento repetido | Mande de novo o primeiro evento (`"partida_id": "p1"`) e peça o ranking | Os números não mudam |
| Usuário fora dos 10 primeiros | Registre 11 partidas ganhas por outros 11 jogadores (laço abaixo) e peça o ranking com o token do Caio | 11 linhas, a última com a linha do Caio |
| Quem nunca jogou | `curl -s http://localhost:8004/api/ranking -H "Authorization: Bearer $(token u-novo Novo)"` | No máximo 10 linhas, nenhuma dele |
| Sem token | `curl -i http://localhost:8004/api/ranking` | 401 `token_invalido` |

O laço para o caso "fora dos 10 primeiros":

```bash
for i in $(seq 1 11); do
  curl -s -o /dev/null -X POST http://localhost:8004/interno/teste/partida-finalizada -H "$JSON" \
    -d "{\"partida_id\": \"extra$i\", \"times\": {\"A\": [{\"usuario_id\": \"u-extra$i\", \"nome\": \"Extra $i\"}], \"B\": []}, \"vencedor_time\": \"A\"}"
done
curl -s http://localhost:8004/api/ranking -H "Authorization: Bearer $(token u-caio Caio)"
```

### 9.4 Com a tela de verdade

A tela e as APIs precisam estar no mesmo endereço, porque a tela chama `/api/...` no endereço de onde ela mesma foi carregada. Com o gateway no ar, basta subir tudo com o Docker Compose e abrir `http://localhost`: o roteiro do teste com dois navegadores está no [README](../README.md) ("Como jogar"). O roteiro abaixo é o da época dos exemplos, sem o gateway: um arquivo de teste junta os três exemplos num processo só e ainda entrega os arquivos da tela:

1. Na pasta dos exemplos, salve o `main.py` do guia do login (seções 8.1 e 8.2 de lá) como `auth.py`, e crie o `juntos.py`, trocando o caminho pelo da pasta `frontend` do repositório:

```python
# juntos.py: SÓ PARA TESTE LOCAL, enquanto não há Nginx. Junta num processo o Auth (o main.py
# do guia do login, salvo como auth.py), o Lobby e o Ranking, e ainda entrega os arquivos da
# tela. Assim a tela e as três APIs ficam no mesmo endereço, como ficarão atrás do gateway.
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import auth
import lobby
import ranking

app = FastAPI()
for servico in (auth, lobby, ranking):
    app.include_router(servico.app.router)  # as rotas do serviço
    app.exception_handlers.update(servico.app.exception_handlers)  # e os tratadores de erro

app.mount("/", StaticFiles(directory="caminho/para/frontend", html=True))
```

2. Instale o pacote que o Auth usa e suba o `juntos.py`:

```bash
pip install argon2-cffi
uvicorn juntos:app --port 8005
```

3. Abra `http://localhost:8005/` e recarregue com Ctrl+Shift+R, para o navegador não usar uma cópia antiga do `api.js`. Se a tela pular direto para o lobby e voltar para o login, sobrou um token de outro teste, assinado com outro segredo: rode `localStorage.clear()` no Console (F12) e abra o endereço de novo.
4. Crie uma conta e uma sala. Numa janela anônima (que tem outro `localStorage`), crie outra conta e entre na sala pela lista. Ponha bots, inicie a partida e veja as duas janelas irem para a mesa. A mesa se conecta à partida pelo `?partida=` da URL: para jogar, o Game também precisa estar no ar ([guia da mesa](guia-backend-mesa.md), seção 8.3); sem ele, a mesa mostra "Não foi possível conectar. Tentando de novo…".
5. Para ver o ranking, registre resultados pela rota de teste (seção 9.3, trocando a porta para 8005). Para a sua própria linha, use o seu id, que está em `truco.usuario`, na aba Application (ou Armazenamento) das ferramentas do navegador, em Local Storage.

Abrir a tela por `python -m http.server`, como no desenvolvimento do frontend, não serve para este teste: esse servidor não tem a API.

### 9.5 Problemas comuns

| Sintoma | Causa provável |
|---|---|
| A tela abre o lobby e volta logo para o login | Toda rota respondeu 401: o token é de outro teste (sobrou no `localStorage`) ou o segredo é diferente no Auth e no Lobby (seção 6.1). |
| Quem criou a sala não vê "(você)" nem os botões de dono | O `usuario_id` e o `dono_id` não são o `usuario.id` do login: o serviço tirou o id de outro lugar que não o `sub` do token. |
| O bot aparece como vaga | Faltou `"bot": true` no assento do bot (seção 4.2). |
| A sala de espera mostra "Algo deu errado. Tente de novo." | `assentos` sem exatamente 2 ou 4 itens (seção 4.1). O console do navegador mostra o erro. |
| A lista mostra "Algo deu errado. Tente de novo." | O `GET /api/lobby/salas` não devolveu uma lista. |
| A tela mostra "Dados inválidos." ao sair ou ao iniciar | A rota declarou um corpo, mas a tela manda esses `POST` sem corpo. |
| A tela mostra "Não foi possível concluir a operação (erro 422)." | O corpo do erro não está no formato do contrato: falta o tratador de `RequestValidationError` (seção 5.1). |
| O dono vai para `mesa.html?partida=undefined` | A resposta do `/iniciar` não tem `partida_id`. |
| Só o dono vai para a mesa; os outros ficam esperando | O `GET` da sala não traz o `partida_id` depois do início. |
| Todo mundo sai da sala depois de uns segundos | A presença não é renovada no `GET` da sala, ou o prazo é contado de antes de o jogador sentar (seção 6.5). |
| O jogador sai da sala ao trocar de aba | Prazo de presença menor que 60 segundos (seção 6.5), ou o navegador usou um `lobby.js` antigo: recarregue com Ctrl+Shift+R. |
| O ranking mostra "undefinedº" ou "undefined" | Falta `posicao`, `vitorias` ou `partidas` na linha (seção 4.4). |
| Uma partida contou duas vezes no ranking | O evento chegou repetido, e o Ranking não guardou o `partida_id` (seção 6.7). |
| A tela mostra "Sala não encontrada" só pelo gateway | Caminho do Nginx diferente do declarado no serviço (seção 3.1). |

## 10. Pontos em aberto

Todos foram fechados, na fase 3, com os serviços de verdade, ou no fechamento do projeto; cada item diz como. O que ficou como limitação está no [README](../README.md#limitações-conhecidas).

### Propostas deste guia (nem a tela nem o documento de contratos definem)

- **P1. Falha do Game ao iniciar.** O documento não diz o que o Lobby responde quando o Game não atende o `POST /interno/partidas`, e o mock não tinha esse caso. Este guia propõe 503 `game_indisponivel`, com a sala continuando `"aguardando"`. A tela mostra a `mensagem` que vier, então qualquer código funciona; falta fechar. **Resolvido:** o Lobby adotou o 503 `game_indisponivel` para qualquer falha do Game (fora do ar, mais de 5 segundos sem resposta, resposta de erro ou sem `partida_id`). A sala continua `"aguardando"` e nenhum `bot.solicitado` sai; o motivo fica no log do Lobby (seção 11.2).
- **P2. Corpo do `POST /interno/partidas`.** O documento diz "`sala_id` e a lista de assentos (`usuario_id`, `nome`, `bot`)", sem os nomes dos campos. Este guia propõe `{"sala_id", "assentos": [{"assento", "usuario_id", "nome", "bot"}]}`, com o número do assento, e a resposta `{"partida_id"}`. Combinar com quem faz a camada de serviço do Game. **Resolvido:** o Game adotou o corpo proposto, responde 201 com `{"partida_id"}` e 422 `dados_invalidos` para assentos que não formam uma mesa ([guia da mesa](guia-backend-mesa.md), seção 10.3).
- **P3. Formato dos eventos no Redis Streams.** O documento diz só que os eventos vão para o Redis Streams. Este guia propõe um stream por evento, com o nome do evento, os dados em JSON no campo `dados` e um grupo por serviço consumidor (seção 7.4). Combinar com quem faz o Game e o Bots. **Resolvido:** o Game publica `partida.criada` e `partida.finalizada` assim, num Redis dedicado aos eventos, o container `eventos` (`rede-eventos`, senha `EVENTOS_SENHA`), separado do banco do Game ([guia da mesa](guia-backend-mesa.md), seção 10.4).
- **P4. Formato de `times` no `partida.finalizada`.** O documento diz "jogadores de cada time". Os exemplos usam `{"A": [{"usuario_id", "nome"}], "B": [...]}`, com bots de `usuario_id` nulo. Combinar com quem faz o Game. **Resolvido:** o Game usa esse formato, com `assento` e `bot` a mais em cada jogador; o exemplo de `registrar_partida` da seção 8.2 funciona sem mudança ([guia da mesa](guia-backend-mesa.md), seção 10.4).
- **P5. Empates no ranking.** O grupo decidiu que empate em vitórias divide a posição. Este guia propõe que a posição seguinte pule as divididas (1, 2, 2, 4, como o `RANK()`) e que, dentro do empate, a ordem seja alfabética pelo nome. Outra opção seria não pular (1, 2, 2, 3) e desempatar a ordem por menos partidas. **Resolvido:** adotada a proposta, `RANK()` (1, 2, 2, 4) e ordem alfabética dentro do empate, sem diferenciar maiúsculas; nomes iguais desempatam pelo id, para a ordem não mudar entre um pedido e outro.
- **P6. Status de sucesso.** Este guia usa 201 no `POST /api/lobby/salas` e 200 nas demais rotas. A tela aceita qualquer status de 200 a 299. **Resolvido:** adotado assim.
- **P7. Nível do bot.** O exemplo só aceita `"padrao"` e responde 422 para outro valor. O mock aceitava qualquer valor. Decidir se haverá outros níveis. **Resolvido:** só `"padrao"` por enquanto; outro valor responde 422 "Nível de bot inválido.", e o corpo sem `nivel` vale `"padrao"`. Um nível novo, se a fase 4 quiser, entra em `NIVEIS_DE_BOT` (`services/lobby/app/config.py`). A fase 4 manteve só o `"padrao"`: no serviço de Bots, cada nível é uma estratégia registrada em `ESTRATEGIAS` (`services/bots/app/bot.py`), e um nível novo precisa entrar nos dois serviços.
- **P8. Ações em sala encerrada.** Pela decisão do grupo, a sala encerrada continua existindo, com `"status": "encerrada"`. Este guia faz o `GET` dela responder 200 e as ações responderem 404 `sala_nao_encontrada`, que é o que o mock respondia para uma sala que deixou de existir. Confirmar; a alternativa seria 409 com outro código. **Resolvido:** adotado o 404 `sala_nao_encontrada`.
- **P9. Começo do prazo de presença.** A regra fala em 60 segundos sem `GET`. Este guia conta o prazo a partir do momento em que o jogador senta (criar, entrar, trocar de assento). Confirmar. **Resolvido:** adotado assim. Pedir o próprio assento ("entrar" no assento em que já está) não muda nada, nem o prazo.

### Consequências das regras para a tela

- **P10. Aba oculta tira o jogador da sala. Resolvido.** A sala de espera continua pedindo a sala com a aba oculta, e o prazo de presença passou de 15 para 60 segundos, para cobrir a redução dos timers em abas ocultas (seção 6.5). Só a lista para de atualizar com a aba oculta.
- **P11. Empate na 10ª posição.** "Os 10 primeiros" são 10 linhas. Se a 10ª e a 11ª linhas empatam, a 11ª fica de fora, mesmo tendo a mesma posição da 10ª. Mandar mais de 10 linhas não adianta: a tela mostra só as 10 primeiras e, depois delas, só a do usuário logado. Decidir se isso basta. **Resolvido:** o ranking tem 10 linhas, e a linha do usuário logado sempre aparece: quando ele está abaixo das 10, ela vem no fim, com a posição dele, mesmo que empatado com a 10ª. A única exceção é quem ainda não jogou nenhuma partida, que não tem linha: o painel mostra "Você entra no ranking depois da primeira partida.". Mudar a regra é mudar só a consulta (`services/ranking/app/banco.py`).
- **P12. A sala depois da partida.** O documento diz que o Lobby recebe `partida.criada` e `partida.finalizada`, mas não diz para quê. O `partida.criada` repete o que o Lobby já sabe pela resposta do `POST /interno/partidas`. Para o `partida.finalizada`, falta decidir se a sala muda de status (não há status para isso no contrato). Enquanto a sala tiver `partida_id`, quem estava nela e abrir o link volta para a mesa daquela partida. **Resolvido:** o Lobby lê o `partida.finalizada` e passa a sala da partida para `"encerrada"`: ela sai da lista. O `partida_id` continua gravado nela; quem estava sentado e abre o link antigo vai para a mesa daquela partida, que mostra o placar final. O `partida.criada` não é lido pelo Lobby (seção 11.3).

### Decisões do backend

- **P13. Falha ao publicar o `bot.solicitado`.** Se o Redis estiver fora do ar depois de o Game criar a partida, a sala já está `"em_partida"`, mas os bots não chegam à mesa. Decidir se o Lobby tenta de novo, desfaz a partida ou avisa o dono. **Resolvido:** como no Game, o evento entra numa fila no `lobby-db` (tabela `eventos_pendentes`), na mesma transação que inicia a partida, e uma linha de execução do Lobby o entrega ao broker. Com o broker fora do ar, a partida começa e o evento espera na fila (seção 11.3).
- **P14. Partidas contra bots no ranking.** O exemplo conta a partida para os jogadores humanos mesmo quando os adversários são bots. Assim, dá para subir no ranking jogando só contra bots. Decidir se essas partidas contam. **Resolvido (decisão do grupo):** contam normalmente para os jogadores humanos. Os bots ficam no histórico da partida, mas não no ranking.
- **P15. Histórico do jogador (RF18).** O documento tem `GET /api/ranking/jogadores/{id}` ("estatísticas e últimas partidas"), mas a tela ainda não tem onde mostrar o histórico. Quando a tela existir, a rota e o formato precisam ser detalhados como os deste guia. **Resolvido:** a rota existe, no formato da seção 11.5, e a tela do histórico (`frontend/historico.html`) a mostra desde o fechamento do projeto: "Meu histórico", no cabeçalho do lobby, e o nome de cada jogador no ranking.
- **P16. Nome do jogador.** O nome no assento vem do campo `nome` do token, que é proposta do guia do login (P12 de lá). Se o usuário puder mudar de nome, o token antigo continua com o nome velho até vencer. Nomes repetidos também se confundem na mesa ([guia da mesa](guia-backend-mesa.md), P14). **Resolvido:** o nome vem do token, e o sistema não permite trocar o nome depois do cadastro (não há rota para isso), então o token nunca fica com um nome velho. O Lobby usa o `nome` do token, e o Ranking guarda o nome que veio no evento da partida mais recente do jogador. Nomes repetidos continuam possíveis, porque o cadastro não exige nome único: isso ficou como limitação conhecida, no [README](../README.md#limitações-conhecidas).
- **P17. Prefixos no Nginx.** Decidir junto com o Auth se o gateway repassa o caminho inteiro, como este guia assume (guia do login, P15). `/api/ranking` precisa funcionar sem barra no fim, e `/interno` não pode ser exposto. **Resolvido:** o gateway repassa o caminho inteiro (`gateway/nginx.conf`), `/api/ranking` sem barra no fim, e `/interno` fica fora dele.
- **P18. Um processo ou vários.** O exemplo trava tudo na memória e lê o Redis com um nome de consumidor fixo: os dois serviços precisam rodar com um processo só. Com o Postgres e as travas da seção 7.2, o Lobby pode ter mais processos; o consumidor do Ranking precisaria de um nome por processo. **Resolvido:** os dois serviços rodam com um processo só (Dockerfile sem `--workers`). As travas do Lobby ficam no Postgres e valeriam com vários processos; o que prende os dois a um processo é o nome fixo do consumidor de eventos (`lobby-1`, `ranking-1`).
- **P19. Códigos de 401.** Os exemplos seguem o guia do login: `token_invalido` para token ausente ou inválido e `token_expirado` para token vencido. O mock respondia `token_expirado` nos dois casos. A tela não lê o código, só o status, então a diferença só importa para quem lê os logs. **Resolvido:** adotado assim. Também recebem `token_invalido` um token cujo `sub` não é um UUID (o token de um bot, por exemplo) e, no Lobby, um token sem `nome`.

## 11. Os serviços Lobby e Ranking de verdade

Esta seção registra o que a implementação em `services/lobby/` e `services/ranking/` decidiu além do que as seções anteriores pedem. As rotas, os corpos, as respostas, os status e os códigos de erro são os das seções 3 a 5, sem mudança.

### 11.1 Como os serviços estão montados

| Parte | Onde | O que faz |
|---|---|---|
| Lobby | `services/lobby/app/` | `rotas.py` tem as rotas e as regras, na ordem das tabelas da seção 3; `banco.py`, o SQL; `game.py`, a chamada ao Game; `eventos.py`, a entrega do `bot.solicitado` e a leitura do `partida.finalizada`. |
| Banco do Lobby | container `lobby-db` | Postgres só do Lobby, na `rede-lobby-db`: tabelas `salas`, `assentos` e `eventos_pendentes`. |
| Ranking | `services/ranking/app/` | `rotas.py` com as duas rotas; `banco.py` com o SQL; `eventos.py` com a leitura e a conferência do `partida.finalizada`. |
| Banco do Ranking | container `ranking-db` | Postgres só do Ranking, na `rede-ranking-db`: tabelas `partidas`, `participantes` e `jogadores`. |
| Broker | container `eventos` | O mesmo Redis em que o Game publica. Os dois serviços entram na `rede-eventos`; nenhum deles alcança o `game-redis`. |

- As tabelas são criadas pelo próprio serviço ao subir, com `CREATE TABLE IF NOT EXISTS`, como no Auth.
- Os dois conferem o JWT sozinhos, com o `JWT_SEGREDO`, sem chamar o Auth.
- O Lobby chama o Game só em `POST /interno/partidas`, pela `rede-servicos` (`GAME_URL=http://game:8000`), fora do gateway.
- Cada serviço roda num processo só, com duas linhas de execução no Lobby (entrega e leitura de eventos) e uma no Ranking (leitura), ao lado das rotas (P18).
- `/saude` responde 200 com o banco no ar. O broker não entra na conta: sem ele, as salas e o ranking continuam respondendo.
- A página de testes do FastAPI de cada um abre pelo gateway: `http://localhost/api/lobby/docs` e `http://localhost/api/ranking/docs`.

### 11.2 Lobby: regras e detalhes

- **Token.** Além da assinatura e da validade, o `sub` precisa ser um UUID (os ids do Auth são) e o `nome`, um texto de 1 a 20 caracteres. Fora disso, 401 `token_invalido`. Assim o token de um bot (`bot-<partida>-<assento>`, guia da mesa 10.5) não entra no Lobby.
- **O token vem antes de tudo.** O FastAPI lê o JSON do corpo antes de conferir o token; um pedido sem token e com o corpo quebrado receberia 422. O tratador de corpo inválido confere o token antes, e a resposta é 401, como pede a seção 5.2.
- **Tipos estritos.** `assento` precisa ser um número JSON: `"1"` (texto), `true` ou `1.5` respondem 422 `dados_invalidos`. `formato` e `nivel` precisam ser texto.
- **Id da sala.** Um `{id}` que nem é UUID responde 404 `sala_nao_encontrada`, como uma sala que nunca existiu.
- **Travas (seção 6.8).** Toda alteração abre uma transação que trava o usuário (`pg_advisory_xact_lock(hashtext(usuario_id))`) e depois a sala (`SELECT ... FOR UPDATE`). No `iniciar`, a sala fica travada enquanto o Game responde, até 5 segundos: um "entrar" ao mesmo tempo espera e não muda os assentos de uma partida que já está sendo criada. Os `GET` não esperam.
- **Presença (seção 6.5).** Conferida no começo de toda requisição, numa transação própria, com `FOR UPDATE SKIP LOCKED`: uma sala que outro pedido está alterando fica para a próxima conferência, em vez de segurar a requisição. O `GET` atrasado do próprio jogador não salva o assento: a conferência roda antes de renovar o prazo. Só o `GET` da sala renova; o da lista, não. Bots e salas em partida ficam fora.
- **Dono que sai.** A sala passa a `"encerrada"` e o assento do dono fica vago. Os outros jogadores continuam nos assentos da sala encerrada, mas ela não conta para a regra de uma sala por vez: eles ficam livres para outra sala, e a tela deles volta para a lista com "A sala foi encerrada.".
- **Nome dos bots.** "Bot 1", "Bot 2"..., o menor número livre na sala, e o nível guardado no assento (não vai na resposta).
- **Iniciar.** O corpo enviado ao Game é o da seção 10.3 do guia da mesa, com os assentos como estão na sala. Qualquer falha do Game vira 503 `game_indisponivel` (P1), inclusive um 422 dele, que seria um defeito do Lobby: o detalhe fica no log (`docker compose logs lobby`).
- **Depois da partida.** O `partida.finalizada` passa a sala para `"encerrada"`, com o `partida_id` ainda gravado (P12).

### 11.3 Eventos do Lobby

O formato é o do Game (guia da mesa, seção 10.4): um stream por evento e o evento em JSON no campo `dados`.

`bot.solicitado`, publicado pelo Lobby quando a partida começa, um para cada assento de bot:

```json
{"partida_id": "84ab7cf6-1744-4d4f-8acd-84be98f4312e", "assento": 2, "nome": "Bot 1", "nivel": "padrao"}
```

- Além dos campos da seção 6.6, vai o `nome` do assento: o serviço de Bots precisa dele no token do bot (guia da mesa, 10.5).
- Entrega: o evento entra na tabela `eventos_pendentes` do `lobby-db`, na mesma transação que grava a sala `"em_partida"` (ou os dois ficam gravados, ou nenhum). Uma linha de execução do Lobby passa a fila para o broker, na ordem, e só então apaga cada evento. Com o broker fora do ar, a partida começa e os eventos esperam (P13). Se o Lobby cair entre o envio e a retirada da fila, o evento sai de novo: o serviço de Bots precisa ignorar repetidos pelo `partida_id` e o `assento`.
- Quem lê este evento é o serviço de Bots (fase 4), com o grupo `bots` (consumidor `bots-1`). Ele cria um bot para cada pedido e só confirma o pedido (`XACK`) quando o bot termina a partida: os pedidos pendentes no grupo são os bots em jogo, e é por eles que o serviço os retoma depois de um reinício, sem banco próprio. Os repetidos são ignorados pelo `partida_id` e o `assento`, e um `nivel` desconhecido joga como `"padrao"`, com um aviso no log. Detalhes no [guia da mesa](guia-backend-mesa.md), seção 10.7.
- Para ver os publicados: `docker compose exec eventos redis-cli XRANGE bot.solicitado - +`; para ver os bots em jogo (os pedidos ainda não confirmados): `docker compose exec eventos redis-cli XPENDING bot.solicitado bots`.

`partida.finalizada`, lido com o grupo `lobby` (consumidor `lobby-1`):

- A sala com aquele `partida_id` e status `"em_partida"` passa a `"encerrada"`. O mesmo evento outra vez não acha mais a sala em partida e não muda nada: o consumo é idempotente pelo `partida_id`.
- Uma partida sem sala no Lobby (a do script de teste do Game) é confirmada sem efeito.
- O grupo é criado a partir do início do stream. Uma mensagem fora do formato vai para o log e é confirmada (`XACK`), para não travar a fila. Uma falha do banco deixa a mensagem pendente, e ela é lida de novo na próxima tentativa (a cada 5 segundos).

`partida.criada` **não é lido pelo Lobby.** Ele repetiria o `partida_id` que o Lobby já recebe na resposta do `POST /interno/partidas` e grava na mesma transação; lido de forma assíncrona, poderia até chegar antes desse commit. Sem grupo `lobby` nesse stream, nada fica pendente no broker. Um caso que ele poderia ajudar fica sem tratamento: se o Game criar a partida e a resposta não chegar ao Lobby em 5 segundos, o dono recebe 503 e a sala continua `"aguardando"`. A partida órfã fica no Game sem ninguém conectar e é apagada depois de 7 dias parada.

### 11.4 Ranking: registro das partidas

- **Tabelas.** No lugar de `partidas_contadas` (seção 7.3), a tabela `partidas` guarda cada partida registrada (formato, sala, vencedor, placar e data), com o `partida_id` como chave. `participantes` guarda quem jogou cada uma, em que assento e time, bots inclusive. `jogadores` é a da seção 7.3, com as somas de cada humano. Os nomes são `TEXT`: vêm de outro serviço, e um nome maior que o esperado não pode travar a leitura dos eventos.
- **Uma vez só.** Cada evento é gravado numa transação: `INSERT INTO partidas ... ON CONFLICT (partida_id) DO NOTHING` e, se a partida é nova, os participantes e as somas. Um evento repetido não insere nada e não soma nada.
- **Eventos de antes do Ranking.** Na primeira vez, o grupo `ranking` é criado a partir do início do stream (id `"0"`): as partidas que o Game publicou antes de o serviço existir entram no ranking. Se o grupo sumir (o broker perdeu os dados), ele é criado de novo e tudo é relido, sem duplicar.
- **Conferência do evento.** `partida_id`, `vencedor_time` (`"A"` ou `"B"`), `placar_final`, `encerrada_em` (ISO 8601; sem fuso, vale UTC) e, em cada jogador, `assento`, `nome` e `bot`; jogador humano sem `usuario_id`, assento ou jogador repetido invalidam o evento. Evento inválido vai para o log e é confirmado.
- **Quem conta.** Jogadores com `bot: false`. Partidas contra bots contam normalmente (P14), e as do script de teste do Game (`sala_id` nulo) também: são partidas de verdade entre usuários do Auth.
- **Nome.** O do evento mais recente do jogador.

### 11.5 `GET /api/ranking/jogadores/{id}`

Estatísticas e últimas partidas de um jogador (RF18). Qualquer usuário logado pode pedir a de qualquer jogador.

Resposta, com status **200**:

```json
{
  "usuario_id": "a712cd19-7914-4807-b5ee-a277fde52cee",
  "nome": "Ana",
  "posicao": 1,
  "vitorias": 1,
  "derrotas": 1,
  "partidas": 2,
  "ultimas_partidas": [
    {
      "partida_id": "98b32790-8440-491c-a662-b983693b2411",
      "formato": "2x2",
      "encerrada_em": "2026-10-28T15:30:00+00:00",
      "time": "A",
      "venceu": false,
      "placar_final": {"A": 9, "B": 12},
      "times": {
        "A": [
          {"assento": 0, "usuario_id": "a712cd19-7914-4807-b5ee-a277fde52cee", "nome": "Ana", "bot": false},
          {"assento": 2, "usuario_id": null, "nome": "Bot 1", "bot": true}
        ],
        "B": [
          {"assento": 1, "usuario_id": "7871a853-f35d-42c5-8dd1-e78533f7b4ef", "nome": "Beto", "bot": false},
          {"assento": 3, "usuario_id": "5f1c9a2e-3b7d-4e8a-9c61-0d2e4f8a7b13", "nome": "Caio", "bot": false}
        ]
      }
    }
  ]
}
```

| Campo | O que é |
|---|---|
| `posicao`, `vitorias`, `partidas` | Os mesmos da linha do ranking (seção 4.4), com a posição calculada do mesmo jeito. |
| `derrotas` | `partidas - vitorias`. |
| `ultimas_partidas` | As 10 mais recentes, da mais nova para a mais antiga (`ULTIMAS_PARTIDAS`, em `services/ranking/app/config.py`). |
| `time`, `venceu` | O time do jogador naquela partida e se ele venceu. |
| `placar_final`, `times` | Como no `partida.finalizada` (guia da mesa, 10.4), com os bots. |

| Erro | Status | `erro` |
|---|---|---|
| Token | 401 | `token_invalido` ou `token_expirado` |
| Jogador que nunca jogou (ou id que não existe) | 404 | `jogador_nao_encontrado` ("Este jogador ainda não tem partidas registradas.") |

### 11.6 Testes

Rodam dentro do container, com o Postgres e o broker de verdade, no ambiente de testes isolado do [README](../README.md#testes) (o projeto `truco-testes` do Docker Compose, com volumes próprios, apagados no fim):

```bash
./testes.sh lobby ranking
```

- Cada serviço usa um banco de teste no próprio Postgres (`lobby_teste` e `ranking_teste`, criados sozinhos) e um banco lógico próprio do broker (2 no Lobby, 3 no Ranking; o Game usa o 1 e os serviços, o 0). Não mexem nas salas, no ranking nem nos eventos de quem está usando o sistema.
- Os do Lobby usam um Game falso, um servidor HTTP dentro do próprio teste, no lugar do `POST /interno/partidas`: assim dá para simular o Game fora do ar, lento ou respondendo errado, e nenhuma partida é criada no Game de verdade.
- Os dois cobrem as rotas e a ordem dos erros, as travas com pedidos ao mesmo tempo, a presença (mudando a hora do último `GET` direto no banco), a entrega do `bot.solicitado` com o broker fora do ar, e a leitura do `partida.finalizada`: repetido, fora do formato, publicado com o serviço parado, lido e não confirmado antes de uma queda e, no Ranking, publicado antes de o serviço existir.

### 11.7 Divergências e acréscimos em relação às seções anteriores

- **`bot.solicitado` traz `nome`**, além de `partida_id`, `assento` e `nivel` (seção 11.3).
- **Tabelas do Ranking:** `partidas` e `participantes` no lugar de `partidas_contadas`, e nomes em `TEXT` (seção 11.4). **Tabela nova no Lobby:** `eventos_pendentes`.
- **Token:** `sub` precisa ser UUID nos dois serviços, e o Lobby exige o `nome` (P19).
- **401 antes de 422** mesmo com o corpo quebrado (seção 11.2).
- **Sala encerrada pelo dono** mantém os outros jogadores nos assentos (seção 11.2); **sala encerrada pela partida** mantém o `partida_id` (P12).
- **Presença** conferida por requisição, pulando as salas travadas (seção 11.2).
- **`GET /api/ranking/jogadores/{id}`** com formato definido (seção 11.5) e 404 `jogador_nao_encontrado`, código que não estava na seção 5.2.
- **Os exemplos das seções 8 e 9** continuam valendo como material de estudo, com o segredo de teste deles. Com o sistema no Docker Compose, os serviços usam o `JWT_SEGREDO` do `.env`, e um token gerado como na seção 9.1 só vale se for assinado com ele.
