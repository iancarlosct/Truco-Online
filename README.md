# Truco Online

Jogo de truco paulista online, com partidas 1x1 e 2x2 contra pessoas ou bots. Trabalho da disciplina Engenharia de Software (UFAL).

Requisitos completos, contratos das APIs e formato das mensagens: [documento de requisitos e contratos](https://claude.ai/code/artifact/37cda24d-3d94-4e3d-93b8-99790ba8252e).

## Stack

- Backend: Python com FastAPI
- Frontend: HTML, CSS e JavaScript puro
- Banco: Postgres (um schema por serviço)
- Estado das partidas e eventos: Redis
- Gateway: Nginx
- Tudo roda com Docker Compose

## Serviços

| Serviço | O que faz |
|---|---|
| `gateway` | Nginx. Roteia `/api` para os serviços, `/ws` para o Game e serve o frontend |
| `auth` | Cadastro, login e emissão de JWT |
| `lobby` | Salas 1x1 e 2x2, assentos, adição de bots e início da partida |
| `game` | Regras do truco, estado da partida, WebSocket e chat da mesa |
| `bots` | Jogador automático que se conecta ao Game como um cliente comum |
| `ranking` | Histórico e vitórias, a partir do evento `partida.finalizada` |

Regras importantes:

- Toda jogada é validada no Game. O frontend só envia a intenção ("jogar carta X").
- Nenhum jogador recebe as cartas dos outros.
- Um serviço nunca acessa o banco de outro.

## Estrutura do repositório

```
truco-online/
├── docker-compose.yml
├── gateway/          # nginx.conf
├── frontend/         # html, css, js
└── services/
    ├── auth/
    ├── lobby/
    ├── game/
    │   ├── engine/   # regras em Python puro + testes
    │   └── app/      # FastAPI, WebSocket, Redis
    ├── bots/
    └── ranking/
```

## Como rodar

```bash
docker compose up --build
```

Depois, acesse `http://localhost`.

Testes do motor de regras:

```bash
docker compose run --rm game pytest
```

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