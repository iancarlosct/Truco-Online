# Truco Online

Jogo de truco paulista online, com partidas 1x1 e 2x2 contra pessoas ou bots. Trabalho da disciplina Engenharia de Software (UFAL).

Requisitos completos, contratos das APIs e formato das mensagens: [documento de requisitos e contratos](https://claude.ai/code/artifact/37cda24d-3d94-4e3d-93b8-99790ba8252e).

## Stack

- Backend: Python com FastAPI
- Frontend: HTML, CSS e JavaScript puro
- Banco: Postgres, uma instância por serviço (`auth-db`, `lobby-db`, `ranking-db`)
- Estado das partidas e eventos: Redis
- Gateway: Nginx
- Tudo roda com Docker Compose

## Serviços

| Serviço | O que faz | Situação |
|---|---|---|
| `gateway` | Nginx. Roteia `/api` para os serviços, `/ws` para o Game e serve o frontend | Pronto (`/api/auth/` e frontend) |
| `auth` | Cadastro, login e emissão de JWT | Pronto, com o banco `auth-db` |
| `lobby` | Salas 1x1 e 2x2, assentos, adição de bots e início da partida | Simulado no navegador |
| `game` | Regras do truco, estado da partida, WebSocket e chat da mesa | Simulado no navegador |
| `bots` | Jogador automático que se conecta ao Game como um cliente comum | A fazer |
| `ranking` | Histórico e vitórias, a partir do evento `partida.finalizada` | Simulado no navegador |

## Arquitetura

O sistema é dividido em microserviços. Cada serviço é um processo independente, num container próprio, com o seu diretório em `services/<nome>/`: código, `Dockerfile`, `requirements.txt` e testes. Nenhum serviço importa código de outro, e não há pacotes compartilhados entre eles.

```
navegador ──> gateway (Nginx, única porta aberta no computador)
                ├── /            arquivos de frontend/
                └── /api/auth/   auth ──> auth-db (Postgres só do Auth)
```

- **O navegador só fala com o gateway.** O Nginx é o único container com porta aberta no computador. Ele entrega o frontend e repassa cada `/api/...` ao serviço certo, com o caminho inteiro (`/api/auth/login` chega ao Auth como `/api/auth/login`).
- **Um banco por serviço.** Cada serviço que guarda dados tem o próprio Postgres, num container próprio, com volume e credenciais próprios: `auth-db` para o Auth e, nas próximas fases, `lobby-db` e `ranking-db`. Nenhum serviço conecta no banco de outro.
- **Redes separadas.** Cada banco fica numa rede só com o seu serviço (`rede-auth-db`: `auth` e `auth-db`). O gateway e os serviços conversam numa rede comum (`rede-servicos`). O gateway não alcança nenhum banco. O começo do `docker-compose.yml` explica essa organização, que se repete a cada serviço novo.
- **Comunicação só pelas interfaces públicas:** HTTP, WebSocket e eventos. Cada serviço confere o token (JWT) sozinho, com o mesmo `JWT_SEGREDO`, sem chamar o Auth.
- Toda jogada é validada no Game. O frontend só envia a intenção ("jogar carta X").
- Nenhum jogador recebe as cartas dos outros.
- Game e Bots não usam Postgres: o estado das partidas fica no Redis.

## Estrutura do repositório

```
truco-online/
├── docker-compose.yml
├── .env.example      # modelo do .env (configuração e segredos)
├── gateway/          # nginx.conf
├── frontend/         # html, css, js
├── docs/             # guias do que o frontend espera de cada serviço
└── services/
    ├── auth/
    │   ├── app/      # FastAPI: rotas, banco, senha e JWT
    │   └── tests/    # pytest
    ├── lobby/
    ├── game/
    │   ├── engine/   # regras em Python puro + testes
    │   └── app/      # FastAPI, WebSocket, Redis
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

   O `.env` não vai para o repositório (está no `.gitignore`). Sem ele, o Docker Compose para com uma mensagem dizendo qual variável falta.

2. Suba tudo:

   ```bash
   docker compose up --build
   ```

3. Acesse `http://localhost` (ou `http://localhost:<GATEWAY_PORTA>`).

Comandos do dia a dia:

| Comando | O que faz |
|---|---|
| `docker compose up --build -d` | Sobe em segundo plano |
| `docker compose ps` | Mostra os containers; `auth` e `auth-db` ficam `healthy` quando estão prontos |
| `docker compose logs -f auth` | Acompanha o log de um serviço |
| `docker compose down` | Para e remove os containers. Os usuários cadastrados continuam no volume do banco |
| `docker compose down -v` | Para e **apaga também os bancos**, com todos os usuários |

- Mudanças em `frontend/` valem no próximo F5: o gateway lê os arquivos direto da pasta. Mudanças no `gateway/nginx.conf` pedem `docker compose restart gateway`, e mudanças no código de um serviço, `docker compose up --build -d`.
- O usuário e a senha do banco ficam gravados no volume na primeira vez que ele sobe. Se você trocar `AUTH_DB_*` depois disso, o Auth não consegue mais entrar no banco. Para recomeçar com os valores novos, rode `docker compose down -v` (apaga os usuários).
- A página de testes do Auth (o `/docs` do FastAPI) fica em `http://localhost/api/auth/docs`.

### Testes

Os testes do Auth rodam dentro do container, com o Postgres de verdade. Eles usam um banco separado no `auth-db` (`auth_teste`, criado sozinho) e não mexem nos usuários cadastrados:

```bash
docker compose run --rm --build auth pytest
```

O `--build` reconstrói a imagem antes, para os testes rodarem com o código atual.

Testes do motor de regras, quando o Game existir:

```bash
docker compose run --rm game pytest
```

### Mock ou serviço real: limpe o localStorage

O login já fala com o Auth de verdade (`USAR_MOCK = false` em `frontend/js/api.js`). O Lobby, o Ranking e o Game continuam simulados no navegador, pelas chaves `USAR_MOCK_LOBBY` e `USAR_MOCK_RANKING` (no mesmo arquivo) e `USAR_MOCK_GAME` (em `frontend/js/ws.js`).

**Sempre que trocar um mock pelo serviço real (ou o contrário), limpe o localStorage do navegador.** Uma sessão antiga, criada pelo mock, continua guardada: a tela de login pula direto para o lobby, e você segue usando o usuário falso, sem passar pelo Auth. Para limpar, aperte F12, vá ao Console, rode `localStorage.clear()` e recarregue a página.

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