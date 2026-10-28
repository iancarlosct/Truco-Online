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
| `gateway` | Nginx. Roteia `/api` para os serviços, `/ws` para o Game e serve o frontend | Pronto (`/api/auth/`, `/ws/` e frontend) |
| `auth` | Cadastro, login e emissão de JWT | Pronto, com o banco `auth-db` |
| `lobby` | Salas 1x1 e 2x2, assentos, adição de bots e início da partida | Simulado no navegador |
| `game` | Regras do truco, estado da partida, WebSocket e chat da mesa | Pronto, com o banco `game-redis`. A mesa continua no mock até o Lobby existir (seção [Mock ou serviço real](#mock-ou-serviço-real-limpe-o-localstorage)) |
| `bots` | Jogador automático que se conecta ao Game como um cliente comum | A fazer. O Game já aceita assentos de bot, mas ninguém joga por eles |
| `ranking` | Histórico e vitórias, a partir do evento `partida.finalizada` | Simulado no navegador |

Além dos serviços, há os containers de dados e de comunicação:

| Container | O que é | Quem acessa |
|---|---|---|
| `auth-db` | Postgres do Auth: os usuários | Só o `auth` |
| `game-redis` | Redis do Game: o estado das partidas | Só o `game` |
| `eventos` | Broker de eventos (Redis Streams): `partida.criada` e `partida.finalizada` | O `game` publica. Nas próximas fases, `lobby`, `ranking` e `bots` leem |

## Arquitetura

O sistema é dividido em microserviços. Cada serviço é um processo independente, num container próprio, com o seu diretório em `services/<nome>/`: código, `Dockerfile`, `requirements.txt` e testes. Nenhum serviço importa código de outro, e não há pacotes compartilhados entre eles.

```
navegador ──> gateway (Nginx, única porta aberta no computador)
                ├── /            arquivos de frontend/
                ├── /api/auth/   auth ──> auth-db (Postgres só do Auth)
                └── /ws/         game ──> game-redis (Redis só do Game: as partidas)
                                   └────> eventos (broker: partida.criada, partida.finalizada)
```

- **O navegador só fala com o gateway.** O Nginx é o único container com porta aberta no computador. Ele entrega o frontend, repassa cada `/api/...` ao serviço certo e o `/ws/` (WebSocket da mesa) ao Game, sempre com o caminho inteiro (`/api/auth/login` chega ao Auth como `/api/auth/login`).
- **Um banco por serviço.** Cada serviço que guarda dados tem o próprio banco, num container próprio, com volume e credenciais próprios: `auth-db` (Postgres) para o Auth, `game-redis` (Redis) para o Game e, nas próximas fases, `lobby-db` e `ranking-db`. Nenhum serviço conecta no banco de outro.
- **Dados e eventos ficam separados.** O `game-redis` guarda os dados do Game, e só o Game o acessa. O broker `eventos` é outro Redis, usado só para a comunicação entre os serviços: o Game publica nele `partida.criada` e `partida.finalizada` (um stream por evento), e o Lobby, o Ranking e os Bots vão ler de lá. O formato dos eventos está no [guia da mesa](docs/guia-backend-mesa.md), seção 10.4.
- **Redes separadas.** Cada banco fica numa rede só com o seu serviço (`rede-auth-db`, `rede-game-redis`). O broker fica na `rede-eventos`, só com quem publica ou lê eventos. O gateway e os serviços conversam na `rede-servicos`. O gateway não alcança nenhum banco nem o broker. O começo do `docker-compose.yml` explica essa organização, que se repete a cada serviço novo.
- **Comunicação só pelas interfaces públicas:** HTTP, WebSocket e eventos. Cada serviço confere o token (JWT) sozinho, com o mesmo `JWT_SEGREDO`, sem chamar o Auth. As rotas internas entre serviços, como o `POST /interno/partidas` do Game, ficam fora do gateway.
- Toda jogada é validada no Game. O frontend só envia a intenção ("jogar carta X").
- Nenhum jogador recebe as cartas dos outros.
- O Game roda num processo só: as conexões da mesa ficam na memória dele (detalhes em [Limitações do Game](#limitações-do-game-nesta-fase)).

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
    ├── game/
    │   ├── engine/     # motor de regras em Python puro, sem FastAPI, Redis nem I/O
    │   ├── app/        # FastAPI: WebSocket da mesa, rota interna, Redis e eventos
    │   ├── scripts/    # partida_de_teste.py: cria uma partida sem o Lobby
    │   └── tests/      # pytest: engine/ (motor) e app/ (serviço)
    ├── bots/
    └── ranking/
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

   O `.env` não vai para o repositório (está no `.gitignore`). Sem ele, o Docker Compose para com uma mensagem dizendo qual variável falta. Quem já tinha o `.env` da fase anterior precisa acrescentar `GAME_REDIS_SENHA` e `EVENTOS_SENHA` (copie as linhas do `.env.example` e troque os valores).

2. Suba tudo:

   ```bash
   docker compose up --build
   ```

3. Acesse `http://localhost` (ou `http://localhost:<GATEWAY_PORTA>`).

Comandos do dia a dia:

| Comando | O que faz |
|---|---|
| `docker compose up --build -d` | Sobe em segundo plano |
| `docker compose ps` | Mostra os containers; `auth`, `auth-db`, `game`, `game-redis` e `eventos` ficam `healthy` quando estão prontos |
| `docker compose logs -f game` | Acompanha o log de um serviço |
| `docker compose down` | Para e remove os containers. Os usuários, as partidas e os eventos continuam nos volumes |
| `docker compose down -v` | Para e **apaga também os volumes**: usuários, partidas e eventos |

- Mudanças em `frontend/` valem no próximo F5: o gateway lê os arquivos direto da pasta. Mudanças no `gateway/nginx.conf` pedem `docker compose restart gateway`, e mudanças no código de um serviço, `docker compose up --build -d`.
- O usuário e a senha do banco do Auth ficam gravados no volume na primeira vez que ele sobe. Se você trocar `AUTH_DB_*` depois disso, o Auth não consegue mais entrar no banco. Para recomeçar com os valores novos, rode `docker compose down -v` (apaga os usuários). As senhas dos dois Redis não ficam no volume: uma troca em `GAME_REDIS_SENHA` ou `EVENTOS_SENHA` vale no próximo `docker compose up -d`.
- A página de testes do Auth (o `/docs` do FastAPI) fica em `http://localhost/api/auth/docs`. A do Game fica em `/interno/docs`, fora do gateway.
- Para olhar dentro dos Redis: `docker compose exec game-redis redis-cli --scan --pattern 'partida:*'` lista as partidas, e `docker compose exec eventos redis-cli XRANGE partida.finalizada - +` mostra os eventos de fim de partida.

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

### Testar a mesa com o Game de verdade, sem o Lobby

Enquanto o Lobby é simulado, as partidas que ele "inicia" só existem no navegador: o Game não as conhece. Para jogar uma partida de verdade, use o script de desenvolvimento, que faz o papel do Lobby:

1. Em `frontend/js/ws.js`, troque `USAR_MOCK_GAME` para `false`. Vale no próximo F5.
2. Com o sistema no ar, crie a partida:

   ```bash
   docker compose exec game python scripts/partida_de_teste.py
   ```

   Se o gateway estiver em outra porta, passe a `GATEWAY_PORTA`: `docker compose exec game python scripts/partida_de_teste.py --porta 8080`.

   O script roda dentro do container do Game. Ele cadastra (ou só faz o login de) dois usuários de teste no Auth, pelo gateway: `ana.teste@truco.dev` e `beto.teste@truco.dev`, os dois com a senha `truco123`. Depois cria uma partida 1x1 pela rota interna `POST /interno/partidas`, a mesma que o Lobby vai chamar, e imprime o que abrir para cada jogador.

3. Siga o que o script imprimiu: entre como Ana em `http://localhost/` e abra a mesa dela; entre como Beto em `http://127.0.0.1/` e abra a mesa dele. Para o navegador, `localhost` e `127.0.0.1` são sites diferentes, cada um com a sua sessão, então os dois jogadores cabem no mesmo navegador, em abas separadas. Uma janela anônima também serve.
4. Ao terminar, **volte `USAR_MOCK_GAME` para `true` antes de fazer commit.** Com o Lobby ainda simulado, a sala "inicia" uma partida que não existe no Game, e a mesa mostraria "Esta partida não existe." e voltaria para o lobby. A chave vai ser ligada de vez na fase 3, junto com o Lobby de verdade.

### Mock ou serviço real: limpe o localStorage

O login já fala com o Auth de verdade (`USAR_MOCK = false` em `frontend/js/api.js`). O Lobby e o Ranking continuam simulados no navegador, pelas chaves `USAR_MOCK_LOBBY` e `USAR_MOCK_RANKING` (no mesmo arquivo). O Game já existe, mas a mesa continua falando com o servidor simulado (`USAR_MOCK_GAME = true` em `frontend/js/ws.js`) até o Lobby de verdade existir, porque só ele cria partidas no Game. Para testar a mesa com o Game antes disso, veja a seção anterior.

**Sempre que trocar um mock pelo serviço real (ou o contrário), limpe o localStorage do navegador.** Uma sessão antiga, criada pelo mock, continua guardada: a tela de login pula direto para o lobby, e você segue usando o usuário falso, sem passar pelo Auth. Para limpar, aperte F12, vá ao Console, rode `localStorage.clear()` e recarregue a página.

### Limitações do Game nesta fase

- **Um processo só.** As conexões da mesa e as travas de cada partida ficam na memória do processo. Por isso o Game roda sem `--workers` e com um container só; com mais de um, jogadores da mesma partida deixariam de receber o estado uns dos outros. O estado das partidas fica no `game-redis` e sobrevive a um reinício do Game, e a mesa reconecta sozinha. Explicação completa em `services/game/app/partidas.py`.
- **Bots.** A partida aceita assentos de bot, e o Game já confere o token que o serviço de Bots vai usar ([guia da mesa](docs/guia-backend-mesa.md), seção 10.5), mas ninguém joga por eles até a fase 4: numa partida com bot, a vez do bot fica parada.
- **Jogador que cai.** A partida espera ele voltar, sem prazo e sem bot no lugar (decisão do grupo).
- **Partidas paradas.** Uma partida sem nenhuma mudança por 7 dias é apagada do `game-redis`.

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
