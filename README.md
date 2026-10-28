# Truco Online

Jogo de truco paulista online, com partidas 1x1 e 2x2 contra pessoas ou bots. Trabalho da disciplina Engenharia de Software (UFAL).

Requisitos completos, contratos das APIs e formato das mensagens: [documento de requisitos e contratos](https://claude.ai/code/artifact/37cda24d-3d94-4e3d-93b8-99790ba8252e).

## Stack

- Backend: Python com FastAPI
- Frontend: HTML, CSS e JavaScript puro
- Banco: Postgres, uma instância por serviço que guarda usuários e salas (`auth-db`, `lobby-db`, `ranking-db`)
- Estado das partidas: Redis só do Game (`game-redis`)
- Eventos entre os serviços: outro Redis, o broker `eventos`, com Redis Streams
- Gateway: Nginx
- Tudo roda com Docker Compose

## Serviços

| Serviço | O que faz | Situação |
|---|---|---|
| `gateway` | Nginx. Roteia `/api` para os serviços, `/ws` para o Game e serve o frontend | Pronto (`/api/auth/`, `/api/lobby/`, `/api/ranking`, `/ws/` e frontend) |
| `auth` | Cadastro, login e emissão de JWT | Pronto, com o banco `auth-db` |
| `lobby` | Salas 1x1 e 2x2, assentos, adição de bots, presença e início da partida | Pronto, com o banco `lobby-db` |
| `game` | Regras do truco, estado da partida, WebSocket e chat da mesa | Pronto, com o banco `game-redis` |
| `bots` | Jogador automático que se conecta ao Game como um cliente comum | Pronto, sem banco: os bots em jogo ficam guardados no próprio broker |
| `ranking` | Vitórias, partidas e histórico de cada jogador, a partir do evento `partida.finalizada` | Pronto, com o banco `ranking-db` |

Além dos serviços, há os containers de dados e de comunicação:

| Container | O que é | Quem acessa |
|---|---|---|
| `auth-db` | Postgres do Auth: os usuários | Só o `auth` |
| `lobby-db` | Postgres do Lobby: as salas e os assentos | Só o `lobby` |
| `ranking-db` | Postgres do Ranking: as partidas registradas e as vitórias de cada jogador | Só o `ranking` |
| `game-redis` | Redis do Game: o estado das partidas | Só o `game` |
| `eventos` | Broker de eventos (Redis Streams): `partida.criada`, `partida.finalizada` e `bot.solicitado` | O `game` publica as partidas; o `lobby` lê `partida.finalizada` e publica `bot.solicitado`; o `ranking` lê `partida.finalizada`; o `bots` lê `bot.solicitado` |

## Arquitetura

O sistema é dividido em microserviços. Cada serviço é um processo independente, num container próprio, com o seu diretório em `services/<nome>/`: código, `Dockerfile`, `requirements.txt` e testes. Nenhum serviço importa código de outro, e não há pacotes compartilhados entre eles.

```
navegador ──> gateway (Nginx, única porta aberta no computador)
                ├── /              arquivos de frontend/
                ├── /api/auth/     auth ────> auth-db (Postgres só do Auth)
                ├── /api/lobby/    lobby ───> lobby-db (Postgres só do Lobby)
                │                    ├──────> game: POST /interno/partidas (fora do gateway)
                │                    └──────> eventos (lê partida.finalizada, publica bot.solicitado)
                ├── /api/ranking   ranking ─> ranking-db (Postgres só do Ranking)
                │                    └──────> eventos (lê partida.finalizada)
                └── /ws/           game ────> game-redis (Redis só do Game: as partidas)
                                     └──────> eventos (publica partida.criada e partida.finalizada)

bots (ninguém o chama, nem o gateway) ──> eventos (lê bot.solicitado)
                                      └─> game: WebSocket da mesa, ws://game:8000 (como um jogador)
```

- **O navegador só fala com o gateway.** O Nginx é o único container com porta aberta no computador. Ele entrega o frontend, repassa cada `/api/...` ao serviço certo e o `/ws/` (WebSocket da mesa) ao Game, sempre com o caminho inteiro (`/api/auth/login` chega ao Auth como `/api/auth/login`).
- **Um banco por serviço.** Cada serviço que guarda dados tem o próprio banco, num container próprio, com volume e credenciais próprios: `auth-db`, `lobby-db` e `ranking-db` (Postgres) para o Auth, o Lobby e o Ranking, e `game-redis` (Redis) para o Game. Nenhum serviço conecta no banco de outro.
- **Dados e eventos ficam separados.** O `game-redis` guarda os dados do Game, e só o Game o acessa. O broker `eventos` é outro Redis, usado só para a comunicação entre os serviços (um stream por evento): o Game publica `partida.criada` e `partida.finalizada`; o Lobby lê `partida.finalizada` (encerra a sala) e publica `bot.solicitado`; o Ranking lê `partida.finalizada` (soma as vitórias); o Bots lê `bot.solicitado` (põe um bot na mesa). O formato dos eventos está no [guia da mesa](docs/guia-backend-mesa.md), seção 10.4, e no [guia do lobby](docs/guia-backend-lobby.md), seção 11.3.
- **Redes separadas.** Cada banco fica numa rede só com o seu serviço (`rede-auth-db`, `rede-lobby-db`, `rede-ranking-db`, `rede-game-redis`). O broker fica na `rede-eventos`, só com quem publica ou lê eventos (Game, Lobby, Ranking e Bots). O gateway e os serviços conversam na `rede-servicos`. O gateway não alcança nenhum banco nem o broker. O começo do `docker-compose.yml` explica essa organização, que se repete a cada serviço novo.
- **Comunicação só pelas interfaces públicas:** HTTP, WebSocket e eventos. Cada serviço confere o token (JWT) sozinho, com o mesmo `JWT_SEGREDO`, sem chamar o Auth. As rotas internas entre serviços, como o `POST /interno/partidas` do Game, que o Lobby chama ao iniciar a partida, ficam fora do gateway.
- Toda jogada é validada no Game. O frontend só envia a intenção ("jogar carta X").
- **Animações da mesa** (`frontend/js/animacoes.js`): carta indo para a mesa, distribuição, pedido de truco em destaque, vencedor da rodada, placar contando e comemoração no fim, derivadas da comparação entre o estado anterior e o novo, sem regras do jogo e sem atrasar nenhum estado; com o `prefers-reduced-motion` ligado no sistema, nada se move, só aparece com fades curtos.
- Nenhum jogador recebe as cartas dos outros.
- O Game roda num processo só: as conexões da mesa ficam na memória dele (detalhes em [Limitações desta fase](#limitações-desta-fase)).
- **O bot é um jogador como outro qualquer.** O serviço de Bots não importa código do Game: cada bot conecta ao WebSocket da mesa com um token que o próprio serviço assina, recebe só a visão dele do estado e envia as mesmas mensagens que a tela.

## Estrutura do repositório

```
truco-online/
├── docker-compose.yml
├── .env.example        # modelo do .env (configuração e segredos)
├── gateway/            # nginx.conf
├── frontend/           # html, css, js
├── docs/               # guias do que o frontend espera de cada serviço
└── services/
    ├── auth/
    │   ├── app/        # FastAPI: rotas, banco, senha e JWT
    │   └── tests/      # pytest
    ├── lobby/
    │   ├── app/        # FastAPI: rotas e regras das salas, banco, chamada ao Game e eventos
    │   └── tests/      # pytest, com um Game falso
    ├── game/
    │   ├── engine/     # motor de regras em Python puro, sem FastAPI, Redis nem I/O
    │   ├── app/        # FastAPI: WebSocket da mesa, rota interna, Redis e eventos
    │   ├── scripts/    # partida_de_teste.py: cria uma partida sem o Lobby
    │   └── tests/      # pytest: engine/ (motor) e app/ (serviço)
    ├── bots/
    │   ├── app/        # leitura do bot.solicitado, conexão com a mesa e a estratégia do bot
    │   └── tests/      # pytest: estrategia/ (sem rede) e servico/ (com os serviços no ar)
    └── ranking/
        ├── app/        # FastAPI: ranking, histórico, banco e leitura do partida.finalizada
        └── tests/      # pytest
```

## Como rodar

Precisa do Docker com o Docker Compose v2 (`docker compose version`).

1. Crie o `.env` a partir do modelo e troque os valores de exemplo:

   ```bash
   cp .env.example .env
   ```

   | Variável | Para quê |
   |---|---|
   | `GATEWAY_PORTA` | Porta do computador em que o sistema atende. Padrão: `80`. Se ela estiver ocupada, use outra, como `8080`. |
   | `JWT_SEGREDO` | Segredo que assina os tokens, o mesmo para todos os serviços. Mínimo de 32 caracteres. Para gerar: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
   | `AUTH_DB_NOME`, `AUTH_DB_USUARIO`, `AUTH_DB_SENHA` | Nome, usuário e senha do banco do Auth. |
   | `GAME_REDIS_SENHA` | Senha do Redis do Game (`game-redis`). |
   | `EVENTOS_SENHA` | Senha do broker de eventos. Todos os serviços que publicam ou leem eventos usam a mesma. |
   | `LOBBY_DB_NOME`, `LOBBY_DB_USUARIO`, `LOBBY_DB_SENHA` | Nome, usuário e senha do banco do Lobby (`lobby-db`). |
   | `RANKING_DB_NOME`, `RANKING_DB_USUARIO`, `RANKING_DB_SENHA` | Nome, usuário e senha do banco do Ranking (`ranking-db`). |
   | `BOTS_SEMENTE` | Opcional. Semente do sorteio dos bots: com ela, o mesmo bot repete as mesmas escolhas nas mesmas situações. Sem ela, cada partida é diferente. |

   O `.env` não vai para o repositório (está no `.gitignore`). Sem ele, o Docker Compose para com uma mensagem dizendo qual variável falta. Quem já tinha o `.env` de uma fase anterior precisa acrescentar as variáveis novas (as `LOBBY_DB_*` e `RANKING_DB_*`, da fase 3; a fase 4 não pede nenhuma obrigatória): copie as linhas do `.env.example` e troque as senhas. Para gerar uma: `python3 -c "import secrets; print(secrets.token_hex(16))"`.

2. Suba tudo:

   ```bash
   docker compose up --build
   ```

3. Acesse `http://localhost` (ou `http://localhost:<GATEWAY_PORTA>`).

Comandos do dia a dia:

| Comando | O que faz |
|---|---|
| `docker compose up --build -d` | Sobe em segundo plano |
| `docker compose ps` | Mostra os containers; os serviços e os bancos ficam `healthy` quando estão prontos |
| `docker compose logs -f lobby` | Acompanha o log de um serviço |
| `docker compose down` | Para e remove os containers. Os usuários, as salas, as partidas, o ranking e os eventos continuam nos volumes |
| `docker compose down -v` | Para e **apaga também os volumes**: usuários, salas, partidas, ranking e eventos |

- Mudanças em `frontend/` valem no próximo F5: o gateway lê os arquivos direto da pasta. Mudanças no `gateway/nginx.conf` pedem `docker compose restart gateway`, e mudanças no código de um serviço, `docker compose up --build -d`.
- O usuário e a senha de cada Postgres ficam gravados no volume na primeira vez que ele sobe. Se você trocar `AUTH_DB_*`, `LOBBY_DB_*` ou `RANKING_DB_*` depois disso, o serviço não consegue mais entrar no banco. Para recomeçar com os valores novos, rode `docker compose down -v` (apaga os dados de todos). As senhas dos dois Redis não ficam no volume: uma troca em `GAME_REDIS_SENHA` ou `EVENTOS_SENHA` vale no próximo `docker compose up -d`.
- As páginas de testes do FastAPI (o `/docs`) abrem pelo gateway: `http://localhost/api/auth/docs`, `http://localhost/api/lobby/docs` e `http://localhost/api/ranking/docs`. A do Game fica em `/interno/docs`, fora do gateway.
- Para olhar dentro dos Redis: `docker compose exec game-redis redis-cli --scan --pattern 'partida:*'` lista as partidas; `docker compose exec eventos redis-cli XRANGE partida.finalizada - +` mostra os eventos de fim de partida, `XRANGE bot.solicitado - +`, os pedidos de bot, e `XPENDING bot.solicitado bots`, quantos bots estão em jogo (os pedidos que o serviço de Bots ainda não confirmou).
- Para olhar dentro dos Postgres: `docker compose exec lobby-db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'` (troque por `ranking-db` ou `auth-db`).

### Testes

Os testes do Auth rodam dentro do container, com o Postgres de verdade. Eles usam um banco separado no `auth-db` (`auth_teste`, criado sozinho) e não mexem nos usuários cadastrados:

```bash
docker compose run --rm --build auth pytest
```

O `--build` reconstrói a imagem antes, para os testes rodarem com o código atual.

Os testes do Game também rodam no container:

```bash
docker compose run --rm --build game pytest
```

- `tests/engine`: o motor de regras. Cartas e manilhas, empates, carta coberta, truco, mão de onze, mão de ferro, visão de cada jogador e partidas completas simuladas em 1x1 e 2x2. O motor não depende de nada além do Python, então `pytest tests/engine`, dentro de `services/game`, roda também fora do Docker, só com o `pytest` instalado.
- `tests/app`: a camada de serviço, com os dois Redis de verdade. A rota interna, os eventos (inclusive com o broker fora do ar), o WebSocket com os fechamentos 4401, 4403 e 4404, a reconexão, a conexão substituída, a pausa entre as mãos e o fim da partida. Eles usam o banco lógico 1 de cada Redis (o serviço usa o 0) e não mexem nas partidas nem nos eventos de quem está usando o sistema.

Os do Lobby e do Ranking também:

```bash
docker compose run --rm --build lobby pytest
docker compose run --rm --build ranking pytest
```

- Como no Auth, cada um usa um banco de teste no próprio Postgres (`lobby_teste` e `ranking_teste`, criados sozinhos). No broker, usam bancos lógicos próprios (2 no Lobby, 3 no Ranking), então não mexem nas salas, no ranking nem nos eventos de quem está usando o sistema.
- O Lobby testa a chamada ao Game com um Game falso, dentro do próprio teste: dá para simular o Game fora do ar ou lento, e nenhuma partida é criada no Game de verdade.
- Os dois testam a leitura do `partida.finalizada` publicando no broker: o mesmo evento várias vezes, fora do formato, com o serviço parado, lido e não confirmado antes de uma queda e, no Ranking, publicado antes de o serviço existir. Detalhes no [guia do lobby](docs/guia-backend-lobby.md), seção 11.6.

Os do Bots precisam do sistema inteiro no ar, com o código atual (o `--build` do `up` reconstrói o container `bots`, que joga as partidas dos testes):

```bash
docker compose up -d --build
docker compose run --rm bots pytest
```

- `tests/estrategia`: a estratégia do bot, sem rede (jogada válida em cada situação, manilhas, carta coberta, truco, mão de onze, a regra do parceiro humano). Roda também fora do Docker: `pytest tests/estrategia`, dentro de `services/bots`.
- `tests/servico/test_partidas.py`: uma partida 1x1 de uma pessoa contra um bot e uma 2x2 de uma pessoa com três bots, criadas pelo Lobby e jogadas até o fim pelo container `bots`. Levam uns 40 segundos: os bots esperam de 1 a 2 segundos antes de cada jogada.
- `tests/servico/test_retomada.py`: o serviço caindo no meio de uma partida, com o bot voltando a jogar, e o mesmo pedido de bot chegando várias vezes sem criar outro bot. Aqui o serviço roda dentro do teste, no banco lógico 4 do broker, com partidas criadas direto no Game: o container `bots` não as vê.
- A pessoa dos testes é a "Teste dos Bots", sempre com o mesmo id, e as partidas que terminam contam para ela no ranking, como as do script de teste do Game.

### Testar o fluxo completo com dois navegadores

O fluxo normal é todo pela tela, com os serviços de verdade: cadastro, sala, partida e ranking.

1. Suba tudo (`docker compose up --build -d`) e espere o `docker compose ps` mostrar os serviços `healthy`.
2. Abra `http://localhost/` e crie uma conta, na aba "Criar conta". O cadastro já entra e abre o lobby.
3. Abra `http://127.0.0.1/` em outra aba e crie outra conta. **Para o navegador, `localhost` e `127.0.0.1` são sites diferentes: cada um guarda a sua sessão** (o token fica no `localStorage`, que é separado por endereço). Assim os dois jogadores cabem no mesmo navegador, em abas separadas. Já duas abas no mesmo endereço são o mesmo jogador. Uma janela anônima ou outro navegador também valem como outra sessão. Com outra `GATEWAY_PORTA`, use `http://localhost:8080/` e `http://127.0.0.1:8080/`.
4. Na aba de `localhost`, clique em "Criar sala 1x1". Na de `127.0.0.1`, a sala aparece na lista em até 3 segundos: clique em "Entrar".
5. Quem criou a sala (o dono) clica em "Iniciar partida". Os dois vão para a mesa: o dono na hora, o outro em até 3 segundos.
6. Joguem até um time chegar a 12 pontos. Na tela de fim de partida, cliquem em "Voltar ao lobby".
7. O painel do ranking, à direita, mostra os dois com as vitórias e as partidas atualizadas. A sala saiu da lista, e os dois já podem criar ou entrar em outra.

Outros casos para conferir:

- **2x2 com quatro pessoas:** são quatro sessões, por exemplo `localhost` e `127.0.0.1` numa janela normal e de novo numa janela anônima. A partida começa com os quatro na mesa, parceiros frente a frente.
- **Bots:** uma sala completada com bots começa, e os bots jogam sozinhos ([Testar contra bots](#testar-contra-bots)).
- **Link de convite:** o endereço da sala (`lobby.html?sala=...`) mostra a sala a quem não está nela, que escolhe uma vaga.
- **Presença:** quem fecha a aba da sala de espera sai da sala depois de 60 segundos; se for o dono, a sala é encerrada.

Se a tela pular direto para o lobby e voltar para o login, sobrou uma sessão de outro teste: veja [Mock ou serviço real](#mock-ou-serviço-real-limpe-o-localstorage).

### Testar contra bots

Com uma pessoa só, pela tela:

1. Suba tudo (`docker compose up --build -d`), abra `http://localhost/` e entre (ou crie uma conta).
2. Clique em "Criar sala 1x1". Na vaga do assento 1, clique em "Adicionar bot": entra o "Bot 1", com o selo "BOT".
3. Clique em "Iniciar partida". Na mesa, o bot joga sozinho, esperando de 1 a 2 segundos antes de cada jogada: joga as cartas, pede truco, responde e decide a mão de onze.
4. Jogue até um time chegar a 12 e clique em "Voltar ao lobby". O ranking mostra a sua partida; o bot não entra no ranking (ele fica só no histórico da partida, em `GET /api/ranking/jogadores/{id}`).

No 2x2, ponha bots nas outras três vagas: o do assento 2, seu parceiro, deixa para você responder ao truco e decidir a mão de onze (vale a primeira resposta do time); no time adversário, quem responde é o bot do assento 1.

Para acompanhar os bots: `docker compose logs -f bots` mostra cada bot que entra numa partida, as quedas de conexão e a saída no fim, com quantas ações ele fez. Para ver o bot voltar sozinho depois de um reinício, rode `docker compose restart bots` no meio de uma partida: a vez dele fica parada uns segundos, e ele volta de onde parou.

### Testar o Game sem o Lobby

O script de desenvolvimento do Game continua existindo, para testar a mesa sem passar pelo lobby. Ele cria uma partida 1x1 direto na rota interna `POST /interno/partidas`, a mesma que o Lobby chama:

```bash
docker compose exec game python scripts/partida_de_teste.py
```

Se o gateway estiver em outra porta, passe a `GATEWAY_PORTA`: `docker compose exec game python scripts/partida_de_teste.py --porta 8080`.

Ele cadastra (ou só faz o login de) dois usuários de teste no Auth, pelo gateway: `ana.teste@truco.dev` e `beto.teste@truco.dev`, os dois com a senha `truco123`. Depois cria a partida e imprime o que abrir para cada jogador: a Ana em `http://localhost/`, o Beto em `http://127.0.0.1/`. Não é preciso mudar nada no frontend. Como é uma partida de verdade entre dois usuários, ela conta no ranking quando termina; como não tem sala, o Lobby não muda nada.

### Mock ou serviço real: limpe o localStorage

Desde a fase 3, a tela fala com todos os serviços de verdade: `USAR_MOCK`, `USAR_MOCK_LOBBY` e `USAR_MOCK_RANKING`, em `frontend/js/api.js`, e `USAR_MOCK_GAME`, em `frontend/js/ws.js`, estão em `false`. O código dos mocks e as ferramentas de desenvolvimento continuam nos arquivos, desligados, e saem no fechamento do projeto (fase 6). Para voltar a simular um serviço no navegador (para mexer só na tela, por exemplo), troque a chave dele para `true`, sem fazer commit da troca.

**Sempre que trocar um mock pelo serviço real (ou o contrário), limpe o localStorage do navegador.** Uma sessão antiga, criada pelo mock, continua guardada: a tela de login pula direto para o lobby, o Lobby recusa o token falso com 401, e a tela volta para o login. Para limpar, aperte F12, vá ao Console, rode `localStorage.clear()` e recarregue a página.

### Limitações desta fase

- **Um processo só.** As conexões da mesa e as travas de cada partida ficam na memória do processo. Por isso o Game roda sem `--workers` e com um container só; com mais de um, jogadores da mesma partida deixariam de receber o estado uns dos outros. O estado das partidas fica no `game-redis` e sobrevive a um reinício do Game, e a mesa reconecta sozinha. Explicação completa em `services/game/app/partidas.py`.
- **Bots.** Um nível só, o `"padrao"`. O bot de uma partida que a pessoa abandonou fica conectado esperando, como a partida (ela é apagada depois de 7 dias parada, e aí o bot desiste). Os pedidos de bot da fase 3 também são atendidos quando o serviço sobe pela primeira vez: os bots entram nessas partidas antigas e esperam as pessoas voltarem. Detalhes no [guia da mesa](docs/guia-backend-mesa.md), seção 10.7.
- **Jogador que cai.** A partida espera ele voltar, sem prazo e sem bot no lugar (decisão do grupo).
- **Partidas paradas.** Uma partida sem nenhuma mudança por 7 dias é apagada do `game-redis`.
- **Lobby, Ranking e Bots também rodam com um processo só.** Cada um lê os eventos com um nome fixo no grupo dele (`lobby-1`, `ranking-1`, `bots-1`), para reler depois de um reinício o que tinha ficado sem confirmar. No Bots, é assim que os bots em jogo voltam para as partidas depois de um reinício.
- **Game lento ao iniciar.** Se o Game criar a partida e a resposta não chegar ao Lobby em 5 segundos, o dono vê "Não foi possível iniciar a partida agora" e a sala continua aguardando; pode tentar de novo. A partida que o Game chegou a criar fica sem ninguém e é apagada depois de 7 dias parada.
- **A sala depois da partida.** Quando a partida acaba, a sala passa a "encerrada" e sai da lista, mas continua sabendo qual foi a partida: quem estava nela e abrir o link antigo da sala vai para a mesa, que mostra o placar final.
- **Histórico do jogador.** A rota `GET /api/ranking/jogadores/{id}` já responde as estatísticas e as últimas partidas ([guia do lobby](docs/guia-backend-lobby.md), seção 11.5); a tela que a mostra fica para a fase 6.

## Divisão de tarefas

| Pessoa | Responsabilidade |
|---|---|
| A | Motor de regras (`game/engine`) com testes, depois o serviço de Bots |
| B | Auth, Lobby, Ranking, camada de serviço do Game, Docker Compose e Nginx |
| C | Frontend completo: login, lobby, mesa, animações e chat |

## Cronograma

| Dias | Entrega |
|---|---|
| 1 a 3 | Requisitos, contratos, repositório e Docker Compose subindo |
| 4 a 7 | Desenvolvimento em paralelo. **Meta: uma partida 1x1 completa entre dois navegadores** |
| 8 a 11 | 2x2, mão de onze e de ferro, bots, chat, ranking, acabamento visual |
| 12 a 14 | Correção de bugs, documentação e apresentação |

Se a meta do dia 7 atrasar, simplificamos primeiro o visual e depois as regras especiais.

## Fluxo de trabalho no Git

1. Nunca commitar direto na `main`.
2. Crie uma branch por tarefa: `feature/nome-da-tarefa`.
3. Abra um Pull Request para a `main`.
4. Outro membro revisa e aprova antes do merge.
