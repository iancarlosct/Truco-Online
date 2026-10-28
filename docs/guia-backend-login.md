# Guia do backend: o que a tela de login espera do serviço Auth

Este guia é para quem vai implementar o serviço Auth em Python com FastAPI e Postgres. Ele explica o que o serviço precisa receber e responder para a tela de login e cadastro (`frontend/index.html`) funcionar ligada a ele, no lugar das respostas falsas (mock) que ela usa hoje. Não é preciso conhecer FastAPI nem JWT: o guia explica o necessário e traz um exemplo pronto para rodar.

**De onde vêm as informações**

- **Código da tela**: `frontend/index.html`, `frontend/js/api.js`, `frontend/js/auth.js` e `frontend/js/paginas/login.js`, na branch `feature/frontend-login` em 13/10/2026. Tudo o que o guia afirma que a tela envia, lê ou mostra saiu desse código e foi conferido rodando a tela no navegador: com o mock e, com ele desligado, falando com o exemplo da seção 8. Atualizado em 14/10/2026, depois do lobby (branch `feature/frontend-lobby`): `lobby.html` passou a existir, o tratamento de 401 entrou em `api.js` e cada serviço ganhou a sua chave de mock.
- **Mock dentro de `api.js`**: enquanto o Auth não existe, é ele que responde ao cadastro e ao login. O comportamento dele é o contrato que a tela assume hoje.
- **Documento de requisitos e contratos** (link no [README](../README.md)): usado para o que o código não cobre, como a rota `GET /api/auth/me` e o uso do token pelos outros serviços.
- **Serviço Auth implementado** em `services/auth/`, na branch `feature/backend-infra-auth` em 28/10/2026, seguindo este guia rota por rota. Ele sobe com o Docker Compose, atrás do gateway (`gateway/nginx.conf`), com o banco próprio `auth-db`. Os pontos em que ele difere do guia estão logo abaixo, em "O que o serviço real faz diferente".

Quando essas fontes não batem, ou quando o código depende de algo que não está escrito em lugar nenhum, o texto traz um código como **P3**. Ele aponta para o item correspondente da seção 10, Pontos em aberto.

**Importante:** a tela já fala com o serviço. No topo de `frontend/js/api.js`, a constante `USAR_MOCK` está em `false`: o cadastro e o login vão ao Auth, pelo gateway. Com `true`, as mesmas funções voltam a ser simuladas dentro do navegador, sem nenhuma outra mudança no código da tela. O código do mock continua no arquivo, desligado (P1). O Lobby e o Ranking têm chaves próprias, `USAR_MOCK_LOBBY` e `USAR_MOCK_RANKING`, logo abaixo, que continuam em `true`: trocar o `USAR_MOCK` não mexe nelas ([guia do lobby](guia-backend-lobby.md)). Ao trocar o mock pelo serviço, limpe o `localStorage` do navegador (seção 9.3, passo 4).

**O que o serviço real faz diferente** do texto e dos exemplos deste guia:

| Ponto | O guia dizia | O serviço faz | Seção |
|---|---|---|---|
| Rota inexistente, método errado e exceção não tratada | Não é preciso converter o 404 e o 405 | Converte também esses erros, e o 500, para o formato `{"erro", "mensagem"}` | 4.2 e 4.4 |
| Mensagens de validação do cadastro | As do exemplo 8.1 ("O nome deve ter de 1 a 20 caracteres.") | As mesmas que a tela mostra ao lado de cada campo ("O nome pode ter no máximo 20 caracteres.") | 5 |
| `sub` do token | Busca o usuário pelo `sub` | Também recusa, com 401 `token_invalido`, um `sub` que não é UUID | 3.5 |
| Segredo do JWT | O exemplo tem um valor padrão no código | Sem valor padrão: o serviço não sobe sem `JWT_SEGREDO` ou com menos de 32 caracteres | 6.5 |
| `proxy_pass` no Nginx | `proxy_pass http://auth:8000;` | Um `upstream auth` com `resolve`, para o gateway acompanhar o Auth quando o container é recriado. O caminho continua chegando inteiro | 3.1 |
| Página `/docs` e testes manuais | `http://localhost:8002/docs` e `curl` na porta 8002 | `http://localhost/api/auth/docs` e `curl` em `http://localhost`, pelo gateway: o serviço não tem porta aberta no computador | 9 |
| Healthcheck | Não existia | `GET /saude`, fora do `/api/auth/`: o gateway não a repassa. O `docker-compose.yml` a usa para saber quando o Auth está pronto | — |
| Parâmetros do SQL | `$1`, `$2` | `:nome`, `:email` (SQLAlchemy com `text()`) | 7.3 |
| Mock do Auth | Apagado de `api.js` junto com o `USAR_MOCK = false` | Continua no arquivo, desligado | P1 |

## 1. Como a tela funciona

A tela tem duas abas no mesmo cartão: **Entrar** (e-mail e senha) e **Criar conta** (nome, e-mail, senha e confirmação de senha). Ela não guarda senha, não gera token e não decide quem pode entrar. Faz só três coisas:

1. **Confere o preenchimento** antes de enviar (seção 5). Se algo estiver errado, mostra o erro ao lado do campo e não envia nada.
2. **Envia os dados** ao Auth e espera a resposta. Enquanto espera, o botão fica desabilitado, com o texto "Entrando…" ou "Criando conta…".
3. **Guarda o que o login devolve** e abre a próxima página, ou **mostra a mensagem de erro** que o servidor mandou.

### 1.1 Os dois fluxos

```text
Entrar:       tela confere os campos -> POST /api/auth/login
              -> guarda token e usuário no navegador -> abre lobby.html

Criar conta:  tela confere os campos -> POST /api/auth/cadastro
              -> POST /api/auth/login (mesmo e-mail e senha, sem o usuário fazer nada)
              -> guarda token e usuário no navegador -> abre lobby.html
```

O que isso significa para o servidor:

- **O cadastro não faz login.** A tela não espera token na resposta do cadastro. Ela mesma chama o login logo em seguida. São sempre duas requisições.
- **A conta tem que valer na hora.** O login chega alguns milissegundos depois do cadastro. Não pode haver etapa de confirmação de e-mail nem demora para o usuário novo ser encontrado (P8).
- **A tela não lê o corpo da resposta do cadastro.** Para ela basta o status de sucesso. Mesmo assim, responda `id` e `nome`, que é o que o contrato pede (P4).
- **Do login, a tela exige o campo `token`.** Sem ele, trata a resposta como erro. O objeto `usuario` é guardado do jeito que vier.
- **Se o cadastro der certo e o login seguinte falhar**, a tela passa para a aba Entrar, preenche o e-mail e mostra um aviso próprio: "Sua conta foi criada, mas não foi possível entrar agora. Entre com seu e-mail e sua senha." Nesse caso a mensagem do servidor não aparece.
- Depois do login, a tela abre o lobby (`lobby.html`). O que ele espera dos serviços Lobby e Ranking está no [guia do lobby](guia-backend-lobby.md).

### 1.2 O que a tela guarda no navegador

Tudo fica no `localStorage`, que continua valendo depois de fechar o navegador. A tela não usa cookies.

| Chave | Conteúdo | De onde vem |
|---|---|---|
| `truco.token` | O texto do campo `token`, exatamente como veio | Resposta do login |
| `truco.usuario` | O objeto `usuario`, em JSON | Resposta do login |
| `truco.mock.usuarios` | Usuários de mentira criados pelo mock | Só existe com `USAR_MOCK = true` |

- **Para a tela, o token é só um texto.** Ela não abre o token, não confere a validade e não lê nada de dentro dele.
- **"Estar logado" é ter algo em `truco.token`.** Quem abre `index.html` com um token guardado nem vê a tela: o navegador vai direto para `lobby.html`. Isso acontece mesmo que o token já tenha vencido: com o Lobby de verdade, a primeira chamada de lá volta com 401, e a tela apaga a sessão e volta para o login (seção 1.3; P13).
- **Sair é apagar as duas chaves.** A função `sair()`, de `auth.js`, não chama o servidor, e o contrato não tem rota de logout (P3).

### 1.3 Como o token é enviado depois

Toda chamada à API passa pela função `requisitar`, de `api.js`. Quando existe um token guardado, ela acrescenta este cabeçalho:

```text
Authorization: Bearer <token>
```

É assim que o token chega às rotas do Lobby e do Ranking, usadas pelo lobby, e à rota `GET /api/auth/me`. No WebSocket da mesa o token vai na URL (`?token=<jwt>`), porque o navegador não permite cabeçalhos nesse tipo de conexão. O [guia da mesa](guia-backend-mesa.md) explica essa parte.

Quando uma rota responde 401, `requisitar` apaga a sessão (com a função `sair()`, de `auth.js`) e volta para a tela de login. Isso vale para todas as rotas, menos `/api/auth/cadastro` e `/api/auth/login`: nelas o 401 quer dizer e-mail ou senha incorretos, e a tela só mostra a mensagem (seção 4.3). A tela olha só o status, e não o código do erro.

Um detalhe: `requisitar` manda o cabeçalho em **qualquer** chamada, inclusive cadastro e login, se houver token guardado. Na prática isso é raro, porque quem tem token é levado para o lobby antes de ver a tela. Mesmo assim, o cadastro e o login devem ignorar esse cabeçalho, ainda que ele traga um token vencido.

## 2. Checklist do que o Auth precisa entregar

Na ordem recomendada. Cada etapa termina em algo que dá para ver funcionando.

Situação em 28/10/2026: tudo entregue em `services/auth/`, menos a remoção do código do mock do Auth em `api.js` (P1).

**Etapa 1: as duas rotas respondendo no formato certo**

- [x] Projeto FastAPI rodando com o Uvicorn (seção 8).
- [x] `POST /api/auth/cadastro` recebendo JSON e respondendo 201 com `id` e `nome` (seção 3.3).
- [x] `POST /api/auth/login` recebendo JSON e respondendo 200 com `token` e `usuario` (seção 3.4). Nesta etapa o token pode ser um texto fixo.
- [x] Erros no formato `{"erro": "...", "mensagem": "..."}`, inclusive os que o FastAPI gera sozinho (seção 4.4).

Os usuários podem ficar na memória, como no exemplo 8.1. Já dá para criar conta e entrar pela tela (seção 9.3).

**Etapa 2: regras e senha**

- [x] Validação no servidor das mesmas regras da tela (seção 5).
- [x] E-mail tratado sem diferenciar maiúsculas de minúsculas, no cadastro e no login (seção 7.2).
- [x] 409 para e-mail já cadastrado.
- [x] 401 igual para e-mail sem conta e para senha errada, sem regra de tamanho de senha no login.
- [x] Senha guardada só como hash (seção 6.1). Nem a senha nem o hash aparecem em respostas ou em logs.

**Etapa 3: token de verdade**

- [x] JWT assinado, com `sub`, `nome` e `exp` (seção 6.3).
- [x] Segredo lido de variável de ambiente (seção 6.5).
- [x] `GET /api/auth/me` validando o token (seções 3.5 e 8.2).
- [x] Segredo, algoritmo e campos do token combinados com Lobby, Game e Ranking (P12). Esses serviços ainda não existem; quando existirem, conferem o token como na seção 6.6.

**Etapa 4: Postgres, Docker e gateway**

- [x] Tabela de usuários no Postgres, com e-mail único (seção 7).
- [x] Erro de e-mail repetido vindo do banco convertido em 409 (seção 7.3).
- [x] Serviço no Docker Compose, com o Uvicorn em `--host 0.0.0.0`.
- [x] Rota `/api/auth` no Nginx (seção 3.1).
- [x] `USAR_MOCK = false` na tela.
- [ ] Mock do Auth apagado de `api.js` (P1).

## 3. Rotas

### 3.1 O prefixo `/api/auth` e o Nginx

O navegador sempre chama `/api/auth/...`, no mesmo endereço de onde a tela foi carregada. Quem recebe é o gateway (Nginx). Ele olha o começo do caminho e repassa a requisição ao serviço certo: `/api/auth` para o Auth, `/api/lobby` para o Lobby e assim por diante.

O caminho que chega ao FastAPI depende de como o Nginx for configurado. Há duas formas, e a diferença é uma barra no fim do `proxy_pass`:

| Dentro de `location /api/auth/ { ... }` | O navegador pede | O FastAPI recebe | Rotas declaradas no FastAPI |
|---|---|---|---|
| `proxy_pass http://auth:8000;` | `/api/auth/login` | `/api/auth/login` | `/api/auth/cadastro`, `/api/auth/login`, `/api/auth/me` |
| `proxy_pass http://auth:8000/;` | `/api/auth/login` | `/login` | `/cadastro`, `/login`, `/me` |

**Este guia assume a primeira forma**: o caminho chega inteiro e as rotas são declaradas com o prefixo completo. É o que o guia da mesa assume para o `/ws`. Assim a mesma URL funciona direto no serviço e pelo gateway, e dá para testar a tela sem o Nginx (seção 9.3). É o que o `gateway/nginx.conf` faz (P15, resolvido).

No código, o prefixo fica em um lugar só:

```python
rotas = APIRouter(prefix="/api/auth")

@rotas.post("/login")  # atende em /api/auth/login
def login(dados: DadosLogin):
    ...
```

Se o gateway for configurado para tirar o prefixo, basta trocar para `APIRouter()`, sem o `prefix`.

O trecho abaixo é a primeira forma, como está no `gateway/nginx.conf` (resumido; o arquivo explica cada linha):

```nginx
resolver 127.0.0.11 valid=10s ipv6=off;   # DNS interno do Docker

upstream auth {
    zone auth 64k;
    server auth:8000 resolve;   # nome e porta do serviço no docker-compose
}

server {
    location /api/auth/ {
        proxy_pass http://auth;   # sem barra no fim: o caminho chega inteiro
        proxy_set_header Host $host;
    }
}
```

A forma mais curta, `proxy_pass http://auth:8000;` direto no `location`, também repassa o caminho inteiro. A diferença é que, com ela, o Nginx descobre o endereço do container uma vez só, ao subir. Quando o Auth é recriado (num `docker compose up --build`, por exemplo) e ganha outro endereço, o gateway continua mandando para o antigo e responde 502 até ser reiniciado. O `resolve` faz o Nginx perguntar o endereço de novo a cada 10 segundos.

Mais dois pontos:

- Dentro do Docker, suba o Uvicorn com `--host 0.0.0.0`. O padrão é `127.0.0.1`, que só aceita conexões vindas de dentro do próprio contêiner.
- Não é preciso configurar CORS. A tela e a API saem do mesmo endereço (o do gateway), e a tela só chama caminhos relativos.

### 3.2 O que vem em toda requisição da tela

| Cabeçalho | Valor | Quando |
|---|---|---|
| `Content-Type` | `application/json` | Quando há corpo (cadastro e login) |
| `Accept` | `application/json` | Sempre |
| `Authorization` | `Bearer <token>` | Só quando há token guardado (seção 1.3) |

- O corpo é sempre um objeto JSON. A tela nunca envia formulário.
- A tela espera a resposta por até **10 segundos**. Depois disso desiste e mostra uma mensagem de falha de conexão (P10).

**Atenção para quem seguir o tutorial oficial do FastAPI sobre login:** ele usa outro formato. Lá o login recebe um formulário com os campos `username` e `password` e responde `access_token`. Não copie essa parte. A tela envia JSON com `email` e `senha` e lê `token` e `usuario`. Uma rota no formato do tutorial responde 422 ao JSON da tela, e a tela mostra "Não foi possível concluir a operação (erro 422)."

### 3.3 `POST /api/auth/cadastro`

Corpo enviado pela tela:

```json
{"nome": "Ana", "email": "Ana@Teste.com", "senha": "segredo1"}
```

| Campo | Tipo | Como a tela envia |
|---|---|---|
| `nome` | texto | Sem espaços no começo e no fim, com 1 a 20 caracteres. |
| `email` | texto | Sem espaços no começo e no fim, **com as maiúsculas que o usuário digitou**. |
| `senha` | texto | Exatamente como foi digitada, com 6 caracteres ou mais. Espaços contam. |

A confirmação de senha é conferida na tela e não é enviada.

Resposta de sucesso, com status **201**:

```json
{"id": "a712cd19-7914-4807-b5ee-a277fde52cee", "nome": "Ana"}
```

| Campo | Tipo | Obrigatório | Uso pela tela |
|---|---|---|---|
| `id` | texto | Sim, pelo contrato | A tela não lê. É um UUID em formato de texto (P11). |
| `nome` | texto | Sim, pelo contrato | A tela não lê. |

A tela aceita qualquer status de 200 a 299 como sucesso. O contrato não diz qual usar, e este guia adota o 201, que é o costume para "criado" (P4).

O que o servidor faz:

1. Lê o JSON e confere que os três campos vieram e são texto.
2. Tira os espaços das pontas do nome e do e-mail e passa o e-mail para minúsculas (seção 7.2).
3. Valida as regras da seção 5. Se alguma falhar, responde 422 `dados_invalidos`.
4. Se já existe usuário com esse e-mail, responde 409 `email_ja_cadastrado`.
5. Calcula o hash da senha (seção 6.1) e grava o usuário (seção 7).
6. Responde 201 com `id` e `nome`. A senha e o hash nunca voltam na resposta.

### 3.4 `POST /api/auth/login`

Corpo enviado pela tela:

```json
{"email": "Ana@Teste.com", "senha": "segredo1"}
```

| Campo | Tipo | Como a tela envia |
|---|---|---|
| `email` | texto | Sem espaços no começo e no fim, com as maiúsculas que o usuário digitou. |
| `senha` | texto | Exatamente como foi digitada. Só precisa estar preenchida: pode ter menos de 6 caracteres (seção 5). |

Resposta de sucesso, com status **200**:

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNzEyY2QxOS03OTE0LTQ4MDctYjVlZS1hMjc3ZmRlNTJjZWUiLCJub21lIjoiQW5hIiwiZXhwIjoxNzkxOTg0NzM2fQ.OX-i1eGalT26SbbOFBp33uS8ZjNSJMRJDkzd7Xa-oCE",
  "usuario": {
    "id": "a712cd19-7914-4807-b5ee-a277fde52cee",
    "nome": "Ana",
    "email": "ana@teste.com"
  }
}
```

| Campo | Tipo | Obrigatório | Uso pela tela |
|---|---|---|---|
| `token` | texto | **Sim** | Guardado em `truco.token` e enviado nas chamadas seguintes. Se faltar, vier vazio ou vier com outro nome, a tela não entra e mostra "Algo deu errado. Tente de novo." |
| `usuario` | objeto | Sim, pelo contrato | Guardado inteiro em `truco.usuario`. A tela de login não lê os campos; o lobby usa o `id` e o `nome`. |
| `usuario.id` | texto | Sim, pelo contrato | O mesmo valor que vai no `sub` do token (seção 6.3). |
| `usuario.nome` | texto | Sim, pelo contrato | O nome cadastrado. |
| `usuario.email` | texto | Sim, pelo contrato | O mock devolve em minúsculas, mesmo que o usuário tenha digitado com maiúsculas (P7). |

O que o servidor faz:

1. Lê o JSON e confere que os dois campos vieram e são texto.
2. Trata o e-mail do mesmo jeito que no cadastro (sem espaços nas pontas, em minúsculas) e busca o usuário.
3. Se não achou o usuário, ou se a senha não confere com o hash guardado, responde 401 `credenciais_invalidas`. A resposta é a mesma nos dois casos.
4. Emite o token (seção 6) e responde 200 com `token` e `usuario`.

### 3.5 `GET /api/auth/me`

Está no documento de contratos, mas a tela ainda não chama essa rota (P2). Ela serve para conferir um token e é o modelo de como as outras rotas protegidas descobrem quem é o usuário.

A requisição não tem corpo. O token vem no cabeçalho:

```text
GET /api/auth/me
Authorization: Bearer <token>
```

Resposta de sucesso, com status **200**:

```json
{"id": "a712cd19-7914-4807-b5ee-a277fde52cee", "nome": "Ana", "email": "ana@teste.com"}
```

O que o servidor faz:

1. Lê o token do cabeçalho `Authorization`. Se não veio, responde 401 `token_invalido`.
2. Confere a assinatura e a validade do token (seção 6.6). Se não servir, responde 401.
3. Busca o usuário pelo id que está no `sub` do token. Se ele não existe, responde 401 `token_invalido`. No serviço, um `sub` que não é UUID recebe a mesma resposta antes de chegar ao banco: o Postgres recusaria a consulta, e a resposta seria um erro 500.
4. Responde 200 com `id`, `nome` e `email`.

## 4. Erros

### 4.1 Formato

Todo erro é uma resposta com status HTTP de erro e este corpo:

```json
{"erro": "credenciais_invalidas", "mensagem": "E-mail ou senha incorretos."}
```

- **`erro`** é um código fixo, para programas. A tela de login não lê esse campo hoje.
- **`mensagem`** é o texto que a tela mostra ao usuário, **exatamente como veio**, numa caixa dentro do cartão.

Por isso a `mensagem` tem que ser escrita para o usuário final: em português, curta, dizendo o que ele pode fazer. Nada de nome de exceção, de tabela ou de campo interno. A tela mostra a mensagem como texto puro, sem interpretar HTML.

### 4.2 Códigos e status

O documento de contratos define só o formato. Os códigos e os status abaixo são os que o mock da tela usa, mais os que este guia propõe para os casos que o mock não cobre (P5).

| Situação | Status | `erro` | `mensagem` | De onde vem |
|---|---|---|---|---|
| Cadastro com e-mail que já tem conta | 409 | `email_ja_cadastrado` | "Este e-mail já está cadastrado." | Mock de `api.js` |
| Login com e-mail sem conta ou com senha errada | 401 | `credenciais_invalidas` | "E-mail ou senha incorretos." | Mock de `api.js` |
| Dados inválidos no cadastro ou no login | 422 | `dados_invalidos` | Diz qual é o problema | Proposta deste guia (P6) |
| Token ausente ou inválido em rota protegida | 401 | `token_invalido` | "Sessão inválida. Entre de novo." | Proposta deste guia |
| Token vencido em rota protegida | 401 | `token_expirado` | "Sua sessão expirou. Entre de novo." | Proposta deste guia |
| Rota inexistente | 404 | `nao_encontrado` | "Endereço não encontrado." | Serviço (seção 4.4) |
| Método errado (por exemplo, `GET` no login) | 405 | `metodo_nao_permitido` | "Operação não permitida neste endereço." | Serviço (seção 4.4) |
| Exceção não tratada (um bug, ou o banco fora do ar) | 500 | `erro_interno` | "Ocorreu um erro no servidor. Tente de novo em instantes." | Serviço (seção 4.4) |

A lista está fechada e é a que o serviço usa (P5). A tela continua não lendo o campo `erro`.

No login, não diferencie "e-mail não existe" de "senha errada". O mock responde igual nos dois casos, para ninguém descobrir quais e-mails têm conta.

### 4.3 O que a tela faz com cada resposta

| O que chega | O que a tela faz |
|---|---|
| Erro com `mensagem` no corpo, qualquer status | Mostra a `mensagem`, libera o botão e continua na mesma aba. Ela não trata 401, 409 e 422 de formas diferentes. |
| Erro sem `mensagem` (outro formato, ou corpo que não é JSON), status de 400 a 499 | Mostra "Não foi possível concluir a operação (erro 422).", com o número do status. |
| Erro sem `mensagem`, status de 500 a 599 | Mostra "O servidor está indisponível no momento. Tente de novo em instantes." |
| Nenhuma resposta: serviço parado ou mais de 10 segundos de espera | Mostra "Não foi possível conectar ao servidor. Verifique sua conexão e tente de novo em instantes." |
| Sucesso no login, mas sem o campo `token` | Mostra "Algo deu errado. Tente de novo." e escreve "Resposta do login sem token." no console do navegador. |
| Qualquer erro no login feito logo depois de um cadastro | Vai para a aba Entrar e mostra o aviso próprio da seção 1.1. |

### 4.4 O formato padrão do FastAPI é outro

Sem nenhum ajuste, o FastAPI responde erros assim:

| Situação | Resposta padrão do FastAPI |
|---|---|
| `raise HTTPException(status_code=401, detail="...")` | `{"detail": "..."}` |
| Corpo fora do esperado: campo faltando, tipo errado, JSON quebrado | 422 com `{"detail": [{"type": "missing", "loc": ["body", "email"], "msg": "Field required", ...}]}` |
| Erro no código da rota (exceção não tratada) | 500 com o texto `Internal Server Error` |

Nenhuma dessas respostas tem `mensagem`, então a tela cai nas frases genéricas da seção 4.3. Para seguir o contrato:

- Nos erros de regra (e-mail repetido, senha errada), monte a resposta já no formato do contrato, em vez de usar `HTTPException`. O exemplo 8.1 tem a função `erro` para isso.
- Para os erros de corpo, registre um tratador de `RequestValidationError` que devolva o formato do contrato. No exemplo 8.1 é a função `corpo_invalido`.

Rota inexistente (404, `{"detail": "Not Found"}`) e método errado (405, `{"detail": "Method Not Allowed"}`) só acontecem se a tela chamar o endereço errado. Mesmo assim, o serviço converte os dois, com um tratador de `HTTPException` do Starlette, e também o 500, com um tratador de `Exception`: assim todo erro sai no formato do contrato (seção 4.2). O 405 mantém o cabeçalho `Allow`, e no 500 a exceção completa continua indo para o log do container (`docker compose logs auth`). Os três tratadores estão em `services/auth/app/erros.py`.

## 5. Validação no servidor

A tela confere os campos antes de enviar, mas o servidor precisa conferir tudo de novo. A conferência da tela é só comodidade para o usuário. Qualquer pessoa pode chamar a rota direto, com o `curl` da seção 9.1 ou pelas ferramentas do navegador, sem passar pela tela.

**Cadastro**

| Campo | Regra na tela | No servidor |
|---|---|---|
| `nome` | Obrigatório, com no máximo 20 caracteres, depois de tirar os espaços das pontas | Tirar os espaços das pontas e aplicar a mesma regra |
| `email` | Obrigatório, no formato `algo@algo.algo`, sem espaços | Tirar os espaços das pontas, passar para minúsculas e aplicar a mesma regra |
| `senha` | Obrigatória, com no mínimo 6 caracteres | A mesma regra, sem alterar a senha |
| confirmação de senha | Igual à senha | Não chega ao servidor |

**Login**

| Campo | Regra na tela | No servidor |
|---|---|---|
| `email` | Obrigatório, no mesmo formato do cadastro | Tirar os espaços das pontas, passar para minúsculas e buscar |
| `senha` | Só precisa estar preenchida | **Nenhuma regra de tamanho** |

Detalhes que evitam diferença entre a tela e o servidor:

- **Login sem regra de tamanho.** A tela envia qualquer senha preenchida, mesmo com 1 caractere. Senha curta é só mais uma senha errada: responda 401 `credenciais_invalidas`, e não um erro de validação.
- **Contagem de caracteres.** A tela conta caracteres de verdade: uma letra acentuada ou um emoji vale 1. O `len()` do Python conta do mesmo jeito.
- **Formato do e-mail.** A regra da tela é a expressão `^[^\s@]+@[^\s@]+\.[^\s@]+$`: algo, arroba, algo, ponto, algo, sem espaços. O exemplo 8.1 usa a mesma. Se o servidor usar uma regra mais rígida, alguns e-mails que passaram na tela serão recusados, e o usuário só vai entender se a `mensagem` explicar o motivo.
- **Senha intocada.** Não tire espaços nem mude maiúsculas da senha. O hash tem que ser calculado sobre o texto exato que chegou, no cadastro e no login.
- **Sem limite máximo para e-mail e senha.** A tela não limita o tamanho desses dois campos (P9).

Quando uma regra falhar, responda 422 `dados_invalidos` com uma `mensagem` que diga qual é o campo e o que está errado. A tela mostra esse texto na caixa de mensagem do cartão, e não ao lado do campo.

No serviço, a `mensagem` é a mesma que a tela mostra ao lado do campo quando a regra falha nela, e vale o primeiro problema encontrado, nesta ordem:

| Problema | `mensagem` |
|---|---|
| Nome vazio (ou só espaços) | "Informe seu nome." |
| Nome com mais de 20 caracteres | "O nome pode ter no máximo 20 caracteres." |
| E-mail vazio | "Informe seu e-mail." |
| E-mail fora do formato | "Informe um e-mail válido, como nome@exemplo.com." |
| Senha com menos de 6 caracteres | "A senha precisa ter no mínimo 6 caracteres." |
| Corpo fora do formato: JSON quebrado, campo faltando, número no lugar de texto | "Dados inválidos. Confira os campos e tente de novo." |

## 6. Senhas e JWT

### 6.1 Senha: guardar só o hash

Um hash de senha é o resultado de uma conta de mão única. A partir da senha se chega ao hash, mas a partir do hash não se volta à senha. O banco guarda só o hash. No login, o serviço confere se a senha digitada produz aquele hash. Assim, nem quem tem acesso ao banco descobre as senhas.

Os requisitos pedem bcrypt ou argon2 (RNF05). Os dois são lentos de propósito, para dificultar que alguém teste milhões de senhas. O exemplo 8.1 usa o argon2, pelo pacote `argon2-cffi`:

```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

hasher = PasswordHasher()

senha_hash = hasher.hash("segredo1")   # no cadastro: é isto que vai para o banco
hasher.verify(senha_hash, "segredo1")  # no login: devolve True
hasher.verify(senha_hash, "errada")    # levanta VerifyMismatchError
```

O hash é um texto de 97 caracteres parecido com este, que já traz junto os parâmetros da conta:

```text
$argon2id$v=19$m=65536,t=3,p=4$3GjWz4OrsYnncWZV45f9qQ$joVNdcBh8xewCWN9JuWEdVyq+Ewj3x8UKnGPJIDvIL8
```

O que saber antes de usar:

- **A mesma senha gera um hash diferente a cada vez.** Por isso não dá para comparar hashes com `==` nem buscar o usuário pelo hash. Busque pelo e-mail e use `verify`.
- **Cada cálculo levou cerca de 0,15 segundo** na máquina de teste e usa 64 MB de memória. Declare as rotas com `def` comum, sem `async`. Num teste com a rota de login em `async def`, uma requisição leve feita ao mesmo tempo que quatro logins esperou mais de meio segundo. Com `def` comum, levou menos de 15 milissegundos.
- **O bcrypt também serve, mas tem um limite.** O pacote `bcrypt` 5.0 recusa senhas com mais de 72 bytes, com um erro `ValueError`, tanto no cadastro quanto no login. Quarenta letras acentuadas já passam disso. Quem escolher o bcrypt precisa limitar o tamanho da senha na validação (P17).
- **Nunca** guarde a senha em texto, nunca devolva a senha ou o hash numa resposta e nunca escreva a senha em log. Um `print(dados)` na rota de login já escreve a senha no terminal.

### 6.2 O que é um JWT

O token é um texto que o Auth entrega no login. Nas requisições seguintes, é ele que prova quem é o usuário. O formato usado no projeto é o JWT, que tem três partes separadas por ponto:

```text
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhNzEyY2QxOS03OTE0LTQ4MDctYjVlZS1hMjc3ZmRlNTJjZWUiLCJub21lIjoiQW5hIiwiZXhwIjoxNzkxOTg0NzM2fQ.OX-i1eGalT26SbbOFBp33uS8ZjNSJMRJDkzd7Xa-oCE
```

| Parte | O que é | No exemplo acima |
|---|---|---|
| 1. Cabeçalho | JSON codificado, com o tipo do token e o algoritmo da assinatura | `{"alg": "HS256", "typ": "JWT"}` |
| 2. Conteúdo | JSON codificado, com os dados do usuário | `{"sub": "a712cd19-7914-4807-b5ee-a277fde52cee", "nome": "Ana", "exp": 1791984736}` |
| 3. Assinatura | Conta feita com as duas primeiras partes e um segredo | Só confere com o segredo certo |

Três consequências:

- **O conteúdo não é secreto.** Ele está só codificado, não cifrado: qualquer pessoa com o token lê o que há dentro. Nunca ponha senha, hash ou outro dado sensível no token.
- **O conteúdo não pode ser alterado.** Quem mudar uma letra do conteúdo invalida a assinatura, e não consegue refazê-la sem o segredo.
- **Quem tem o segredo confere o token sozinho.** Não é preciso perguntar ao Auth nem consultar o banco. É isso que permite a Lobby, Game e Ranking validar o token sem chamar o Auth (RNF06).

### 6.3 O que vai dentro do token

| Campo | Valor | Para quê |
|---|---|---|
| `sub` | O id do usuário, **em texto** | Dizer quem é o usuário. O Lobby usa para saber quem está na sala, e o Game, para descobrir em que assento o jogador está. |
| `nome` | O nome do usuário | Os outros serviços mostrarem o nome sem consultar o Auth. |
| `exp` | O momento em que o token vence | Depois disso o token é recusado (seção 6.4). |

O `sub` tem que ser texto. Com o id vindo do Postgres como UUID, converta com `str(...)`:

- Passar o objeto UUID direto dá erro ao emitir o token: `TypeError: Object of type UUID is not JSON serializable`.
- Passar um número é pior. O token é emitido, mas o PyJWT o recusa na hora de validar, com "Subject must be a string".

O documento de contratos não diz o que vai dentro do token. Os nomes `sub` e `nome` e o algoritmo HS256 eram a proposta deste guia e foram adotados pelo serviço; Lobby, Game e Ranking seguem o mesmo formato (P12, resolvido).

### 6.4 Expiração

O campo `exp` guarda o momento em que o token deixa de valer, em segundos contados desde 1970. No token de exemplo, `1791984736` é 14/10/2026 às 13h32 UTC, 24 horas depois do login. O PyJWT confere o `exp` sozinho na validação.

O token vale 24 horas, como no exemplo (P13, resolvido). O que pesou na escolha:

- A tela não renova o token e não percebe quando ele vence (seção 1.2). Com um prazo curto, o usuário é mandado de volta para o login no meio do uso: a primeira chamada depois do vencimento volta com 401 (seção 1.3).
- Com um prazo longo demais, um token que vazar continua valendo por muito tempo, e não há como cancelá-lo antes (P3).

Hoje, com um token vencido guardado, a tela de login continua mandando o usuário direto para o lobby. Lá, a primeira chamada a um serviço de verdade volta com 401, e a tela apaga a sessão e volta para o login.

### 6.5 O segredo

- O segredo fica numa variável de ambiente, por exemplo `JWT_SEGREDO`, com **o mesmo valor em todos os serviços**.
- Para gerar um bom valor: `python -c "import secrets; print(secrets.token_hex(32))"`. O resultado tem 64 caracteres.
- Use pelo menos 32 caracteres. Com menos, o PyJWT emite o aviso `InsecureKeyLengthWarning`.
- O segredo não vai para o repositório. Quem tem o segredo consegue fabricar um token de qualquer usuário.
- No projeto, o valor fica no arquivo `.env` da raiz (modelo no `.env.example`, versionado), e o `docker-compose.yml` o entrega a cada serviço. O Auth não tem valor padrão no código: sem `JWT_SEGREDO`, ou com menos de 32 caracteres, ele nem sobe e explica no log o que falta.

### 6.6 Como os outros serviços validam o token

Todos usam a mesma função, que está no exemplo 8.2:

```python
conteudo = conteudo_do_token(token)  # levanta jwt.InvalidTokenError se o token não servir
usuario_id = conteudo["sub"]
nome = conteudo["nome"]
```

- No Lobby e no Ranking o token chega no cabeçalho `Authorization`, como em `GET /api/auth/me`. No Game ele chega na URL do WebSocket (`?token=`).
- `jwt.InvalidTokenError` cobre todos os casos: assinatura errada, texto que não é um token e token vencido. Para tratar o vencido à parte, capture antes `jwt.ExpiredSignatureError`.
- Passe sempre `algorithms=["HS256"]`. Sem esse argumento o PyJWT se recusa a validar.
- Nenhum serviço chama o Auth nem o banco do Auth para validar um token.
- Os bots também entram no Game com um token, o "token de serviço" do contrato. Quem emite esse token ainda não foi definido (P14).

## 7. Banco

### 7.1 A tabela de usuários

```sql
CREATE TABLE usuarios (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome       VARCHAR(20) NOT NULL,
    email      TEXT        NOT NULL UNIQUE,
    senha_hash TEXT        NOT NULL,
    criado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

| Campo | Tipo | Regra | Observação |
|---|---|---|---|
| `id` | `UUID` | Chave primária, gerada pelo banco | Vai nas respostas e no `sub` do token, sempre como texto (P11). |
| `nome` | `VARCHAR(20)` | Obrigatório | O limite conta caracteres, como na tela. |
| `email` | `TEXT` | Obrigatório e único | Sempre gravado em minúsculas (seção 7.2). |
| `senha_hash` | `TEXT` | Obrigatório | O texto devolvido por `hasher.hash`. Nunca a senha. |
| `criado_em` | `TIMESTAMPTZ` | Preenchido pelo banco | A tela não usa. |

- `gen_random_uuid()` já vem no Postgres a partir da versão 13. O projeto usa o Postgres 17.
- O próprio serviço cria a tabela ao subir, com `CREATE TABLE IF NOT EXISTS usuarios (...)`, o mesmo SQL acima (`services/auth/app/banco.py`). Na primeira vez a tabela é criada; nas outras, o comando não faz nada e não mexe nos dados. Ele também não altera uma tabela que já existe: se a estrutura mudar, é preciso um `ALTER TABLE` à mão ou recriar o banco (`docker compose down -v`, que apaga os usuários).
- Vale um banco por serviço, como diz o README: o Auth tem o próprio Postgres, no container `auth-db`, e só ele conecta nesse banco (P16, resolvido).

### 7.2 E-mail sem diferenciar maiúsculas de minúsculas

Para a tela, `Ana@Teste.com` e `ana@teste.com` são a mesma conta. É o que o mock faz, embora não esteja no contrato (P7). A tela envia o e-mail como o usuário digitou, então quem resolve isso é o servidor.

O jeito mais simples:

1. Ter **uma função só** que limpa o e-mail: tira os espaços das pontas e passa para minúsculas (`email.strip().lower()`).
2. Usar essa função no cadastro, antes de validar e de gravar, e no login, antes de buscar.
3. Gravar no banco o e-mail já limpo. A restrição `UNIQUE` da tabela passa a impedir a conta duplicada.

Com isso, `usuario.email` volta sempre em minúsculas, igual ao mock.

O erro a evitar é limpar o e-mail em uma rota e esquecer na outra. Se o cadastro grava `Ana@Teste.com` e o login busca `ana@teste.com`, a conta é criada e o login automático falha. O usuário vê "Sua conta foi criada, mas não foi possível entrar agora…".

### 7.3 Consultas e cuidados

As três consultas que o serviço precisa:

```sql
-- Cadastro: grava e devolve o que vai na resposta
INSERT INTO usuarios (nome, email, senha_hash) VALUES ($1, $2, $3) RETURNING id, nome;

-- Login: busca pelo e-mail já em minúsculas
SELECT id, nome, email, senha_hash FROM usuarios WHERE email = $1;

-- GET /me: busca pelo id que veio no token
SELECT id, nome, email FROM usuarios WHERE id = $1;
```

- **Nunca monte o SQL juntando textos** com os dados do usuário. Use sempre os parâmetros da biblioteca. A forma de escrever o parâmetro (`$1`, `%s`, `:email`) muda de uma biblioteca para outra. O serviço usa o SQLAlchemy 2 com o driver psycopg 3 e escreve o SQL à mão, com `text()`: lá os parâmetros são `:nome`, `:email` e `:id` (`services/auth/app/banco.py`).
- **E-mail repetido também pode chegar pelo banco.** Se dois cadastros com o mesmo e-mail chegarem juntos, os dois passam pela checagem "já existe?" e o segundo `INSERT` falha na restrição `UNIQUE` (código de erro `23505` do Postgres). Capture esse erro e responda 409 `email_ja_cadastrado`. Sem isso o usuário recebe um erro 500.
- **Confirme a gravação antes de responder.** O login chega logo depois do cadastro (seção 1.1). Se a transação ainda não foi confirmada (commit), o login não acha o usuário.
- **O `id` volta do banco como um objeto UUID.** Nas respostas o FastAPI converte sozinho para texto. No token, não: use `str(id)` (seção 6.3).

## 8. Exemplo mínimo em FastAPI

O serviço real, em `services/auth/`, segue a mesma estrutura deste exemplo, dividida em arquivos: `rotas.py` (as três rotas e as regras), `seguranca.py` (argon2 e JWT), `banco.py` (Postgres), `erros.py` (formato dos erros), `config.py` (variáveis de ambiente) e `main.py` (o app, que junta tudo). O exemplo continua aqui por ser o jeito mais curto de entender cada parte.

Os dois trechos abaixo foram testados com Python 3.14, FastAPI 0.143, Uvicorn 0.54, PyJWT 2.15 e argon2-cffi 25.1. A tela real, com `USAR_MOCK = false`, criou conta e entrou usando este exemplo.

Para rodar, salve o código como `main.py` numa pasta de testes, fora do repositório, e execute dentro dela:

```bash
pip install fastapi "uvicorn[standard]" pyjwt argon2-cffi
uvicorn main:app --reload --port 8002
```

- O pacote do JWT se chama `pyjwt`, mas no código o import é `import jwt`. Não instale o pacote de nome `jwt`, que é outra biblioteca. Do mesmo jeito, o pacote `argon2-cffi` é importado como `argon2`.
- `main:app` quer dizer: arquivo `main.py`, variável `app`. Se o comando `uvicorn` não for encontrado, use `python -m uvicorn main:app --reload --port 8002`.
- `--reload` reinicia o servidor a cada vez que o arquivo é salvo. Use só durante o desenvolvimento. No exemplo os usuários ficam na memória, então somem a cada reinício.
- A porta 8002 evita conflito com o frontend, que costuma ser servido na 8000, e com o exemplo do guia da mesa, que usa a 8001.

### 8.1 Esqueleto: cadastro e login, com hash de senha e JWT

```python
# main.py: esqueleto mínimo do serviço Auth. Faz o cadastro e o login, com hash de senha
# e emissão de JWT. Os usuários ficam na memória e somem quando o servidor reinicia;
# no serviço real eles ficam no Postgres (seção 7).
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt  # pacote PyJWT
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Segredo que assina os tokens. Os outros serviços usam o mesmo valor para validar.
# No serviço real ele vem de uma variável de ambiente e não vai para o repositório.
JWT_SEGREDO = os.environ.get("JWT_SEGREDO", "segredo-de-teste-troque-por-um-valor-aleatorio")
JWT_VALIDADE = timedelta(hours=24)

# As mesmas regras que a tela confere antes de enviar (seção 5).
NOME_MAX = 20
SENHA_MIN = 6
FORMATO_EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")

app = FastAPI()
rotas = APIRouter(prefix="/api/auth")  # todas as rotas abaixo começam com /api/auth
hasher = PasswordHasher()  # argon2id, com os parâmetros padrão da biblioteca

# "Banco de dados" de mentira: e-mail em minúsculas -> usuário.
USUARIOS: dict[str, dict] = {}


# Corpo esperado em cada rota. O FastAPI lê o JSON e confere se os campos vieram e são texto.
class DadosCadastro(BaseModel):
    nome: str
    email: str
    senha: str


class DadosLogin(BaseModel):
    email: str
    senha: str


def erro(status: int, codigo: str, mensagem: str) -> JSONResponse:
    """Resposta de erro no formato do contrato: {"erro": ..., "mensagem": ...}."""
    return JSONResponse(status_code=status, content={"erro": codigo, "mensagem": mensagem})


# Quando o corpo não é o esperado (JSON quebrado, campo faltando, número no lugar de texto),
# o FastAPI responde sozinho com 422 e {"detail": [...]}. Aqui essa resposta é trocada
# pelo formato do contrato, para a tela ter uma mensagem para mostrar.
@app.exception_handler(RequestValidationError)
def corpo_invalido(request, exc):
    return erro(422, "dados_invalidos", "Dados inválidos. Confira os campos e tente de novo.")


def senha_confere(senha_hash: str, senha: str) -> bool:
    """Compara a senha digitada com o hash guardado."""
    try:
        return hasher.verify(senha_hash, senha)
    except VerifyMismatchError:
        return False


def criar_token(usuario: dict) -> str:
    """Emite o JWT: quem é o usuário (sub), o nome dele e até quando o token vale (exp)."""
    conteudo = {
        "sub": usuario["id"],  # tem que ser texto
        "nome": usuario["nome"],
        "exp": datetime.now(timezone.utc) + JWT_VALIDADE,
    }
    return jwt.encode(conteudo, JWT_SEGREDO, algorithm="HS256")


# As rotas usam "def" comum, sem "async": o cálculo do hash é lento de propósito e, numa
# rota "async def", seguraria todas as outras requisições enquanto roda.
@rotas.post("/cadastro", status_code=201)
def cadastro(dados: DadosCadastro):
    # 1. Limpa o nome e o e-mail. A senha fica exatamente como chegou.
    nome = dados.nome.strip()
    email = dados.email.strip().lower()

    # 2. Confere de novo as regras da tela.
    if not nome or len(nome) > NOME_MAX:
        return erro(422, "dados_invalidos", f"O nome deve ter de 1 a {NOME_MAX} caracteres.")
    if not FORMATO_EMAIL.fullmatch(email):
        return erro(422, "dados_invalidos", "Informe um e-mail válido.")
    if len(dados.senha) < SENHA_MIN:
        return erro(422, "dados_invalidos", f"A senha precisa ter no mínimo {SENHA_MIN} caracteres.")

    # 3. Recusa e-mail que já tem conta.
    if email in USUARIOS:
        return erro(409, "email_ja_cadastrado", "Este e-mail já está cadastrado.")

    # 4. Guarda o usuário com o hash da senha. A senha em si não é guardada em lugar nenhum.
    usuario = {
        "id": str(uuid.uuid4()),
        "nome": nome,
        "email": email,
        "senha_hash": hasher.hash(dados.senha),
    }
    USUARIOS[email] = usuario

    # 5. Responde 201 com id e nome. O login é uma segunda requisição, feita pela tela.
    return {"id": usuario["id"], "nome": usuario["nome"]}


@rotas.post("/login")
def login(dados: DadosLogin):
    usuario = USUARIOS.get(dados.email.strip().lower())

    # E-mail desconhecido e senha errada recebem a mesma resposta,
    # para não revelar quais e-mails têm conta.
    if usuario is None or not senha_confere(usuario["senha_hash"], dados.senha):
        return erro(401, "credenciais_invalidas", "E-mail ou senha incorretos.")

    return {
        "token": criar_token(usuario),
        "usuario": {"id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"]},
    }


app.include_router(rotas)
```

Para quem nunca usou FastAPI, o essencial deste código:

- `@rotas.post("/cadastro")` liga um endereço a uma função. Quando chega um `POST /api/auth/cadastro`, o FastAPI chama a função `cadastro`.
- O parâmetro `dados: DadosCadastro` manda o FastAPI ler o corpo como JSON e conferir os campos da classe. Se o corpo não servir, a função nem é chamada: quem responde é o tratador `corpo_invalido`.
- O que a função devolve vira a resposta. Um dicionário vira JSON, com status 200 ou com o `status_code` indicado na rota. Nos erros, a função `erro` devolve a resposta já pronta, com o status que ela recebeu.

O que este esqueleto ainda não faz:

- Não usa banco. Os usuários ficam num dicionário e somem ao reiniciar. Falta trocar o `USUARIOS` pelas consultas da seção 7.3.
- Não impede dois cadastros simultâneos com o mesmo e-mail. No Postgres, quem garante isso é a restrição `UNIQUE` (seção 7.3).
- Não valida token nenhum. Isso é o próximo passo.
- Usa um segredo padrão escrito no código quando a variável `JWT_SEGREDO` não existe. Serve só para teste.

### 8.2 Próximo passo: validar o token em `GET /api/auth/me`

Acrescente este trecho ao `main.py` do passo anterior, logo antes da última linha (`app.include_router(rotas)`). Ele mostra a validação que todos os serviços vão repetir.

```python
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Lê o cabeçalho "Authorization: Bearer <token>". Com auto_error=False, quando o cabeçalho
# falta o FastAPI não responde por conta própria (seria no formato dele): quem decide é a rota.
bearer = HTTPBearer(auto_error=False)


def conteudo_do_token(token: str) -> dict:
    """Confere a assinatura e a validade do token e devolve o que há dentro dele.
    Levanta jwt.InvalidTokenError quando o token não serve.
    Qualquer serviço pode usar esta mesma função: basta ter o segredo."""
    return jwt.decode(
        token,
        JWT_SEGREDO,
        algorithms=["HS256"],
        options={"require": ["sub", "exp"]},  # recusa token sem dono ou sem validade
    )


@rotas.get("/me")
def me(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credenciais is None:
        return erro(401, "token_invalido", "Sessão inválida. Entre de novo.")
    try:
        conteudo = conteudo_do_token(credenciais.credentials)
    except jwt.ExpiredSignatureError:
        return erro(401, "token_expirado", "Sua sessão expirou. Entre de novo.")
    except jwt.InvalidTokenError:
        return erro(401, "token_invalido", "Sessão inválida. Entre de novo.")

    # "sub" traz o id do usuário. Os dados são buscados de novo, para devolver os atuais.
    usuario = next((u for u in USUARIOS.values() if u["id"] == conteudo["sub"]), None)
    if usuario is None:
        return erro(401, "token_invalido", "Sessão inválida. Entre de novo.")
    return {"id": usuario["id"], "nome": usuario["nome"], "email": usuario["email"]}
```

Observações:

- O `HTTPBearer` também faz aparecer o botão **Authorize** na página `/docs` (seção 9.2). Ler o cabeçalho com um parâmetro `Header` comum funciona pelo `curl`, mas não pelo `/docs`: a página mostra o campo e não envia o cabeçalho.
- Para ver um token vencer, troque `JWT_VALIDADE` para `timedelta(seconds=10)`, faça login e chame o `/me` depois de 10 segundos. A resposta passa a ser 401 `token_expirado`.
- No Lobby e no Ranking, toda rota protegida começa igual: recebe `credenciais`, chama `conteudo_do_token` e usa `conteudo["sub"]` como id do usuário.

## 9. Como testar sem a tela

Suba o exemplo da seção 8 na porta 8002 antes de começar.

**Com o serviço real**, suba tudo com `docker compose up --build` e troque `http://localhost:8002` por `http://localhost` em todos os comandos abaixo: as requisições passam pelo gateway, porque o serviço não tem porta aberta no computador. A página da seção 9.2 fica em `http://localhost/api/auth/docs`. Os testes automáticos, que cobrem todos os casos das tabelas abaixo, rodam com `docker compose run --rm --build auth pytest` (README).

### 9.1 Pelo terminal, com curl

Os comandos abaixo são para bash: Linux, macOS, WSL ou Git Bash. No PowerShell que vem com o Windows (testado na versão 5.1) eles não funcionam como estão. Lá `curl` é outro comando e, mesmo com `curl.exe`, as aspas do JSON se perdem e o serviço responde `dados_invalidos`. No Windows, use o Git Bash, o WSL ou a página `/docs` (seção 9.2).

**Cadastro**

```bash
curl -i -X POST http://localhost:8002/api/auth/cadastro \
  -H "Content-Type: application/json" \
  -d '{"nome": "Ana", "email": "ana@teste.com", "senha": "segredo1"}'
```

A opção `-i` mostra o status e os cabeçalhos antes do corpo. O que interessa é a primeira linha e a última:

```text
HTTP/1.1 201 Created
...
{"id":"a712cd19-7914-4807-b5ee-a277fde52cee","nome":"Ana"}
```

O `id` muda a cada cadastro.

Para os casos de erro, repita o comando trocando só o corpo (`-d`):

| Caso | Corpo | Resposta esperada |
|---|---|---|
| E-mail repetido | O mesmo comando de novo, ou com `"email": "ANA@Teste.com"` | 409 `email_ja_cadastrado` |
| Nome com 21 caracteres | `'{"nome": "123456789012345678901", "email": "bia@teste.com", "senha": "segredo1"}'` | 422 `dados_invalidos` |
| E-mail fora do formato | `'{"nome": "Bia", "email": "bia-sem-arroba", "senha": "segredo1"}'` | 422 `dados_invalidos` |
| Senha com 5 caracteres | `'{"nome": "Bia", "email": "bia@teste.com", "senha": "12345"}'` | 422 `dados_invalidos` |
| Campo faltando | `'{"nome": "Bia", "email": "bia@teste.com"}'` | 422 `dados_invalidos` |
| Corpo que não é JSON | `'isto não é json'` | 422 `dados_invalidos` |

Em todos eles o corpo da resposta tem que ter `erro` e `mensagem`. Por exemplo:

```json
{"erro": "email_ja_cadastrado", "mensagem": "Este e-mail já está cadastrado."}
```

**Login**

```bash
curl -i -X POST http://localhost:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "ana@teste.com", "senha": "segredo1"}'
```

A resposta é 200, com `token` e `usuario` (o exemplo completo está na seção 3.4).

| Caso | Corpo | Resposta esperada |
|---|---|---|
| E-mail com maiúsculas | `'{"email": "ANA@TESTE.COM", "senha": "segredo1"}'` | 200, com `"email": "ana@teste.com"` |
| Senha errada | `'{"email": "ana@teste.com", "senha": "errada"}'` | 401 `credenciais_invalidas` |
| Senha curta | `'{"email": "ana@teste.com", "senha": "1"}'` | 401 `credenciais_invalidas`, e não 422 |
| E-mail sem conta | `'{"email": "ninguem@teste.com", "senha": "segredo1"}'` | 401 `credenciais_invalidas`, com a mesma mensagem da senha errada |

**Token e `GET /api/auth/me`** (com o trecho da seção 8.2)

Copie o valor de `token` da resposta do login e guarde numa variável:

```bash
TOKEN="cole aqui o token"

curl -i http://localhost:8002/api/auth/me -H "Authorization: Bearer $TOKEN"
```

| Caso | Comando | Resposta esperada |
|---|---|---|
| Token certo | O comando acima | 200, com `id`, `nome` e `email` |
| Sem cabeçalho | `curl -i http://localhost:8002/api/auth/me` | 401 `token_invalido` |
| Token adulterado | Acrescente uma letra: `"Authorization: Bearer ${TOKEN}x"` | 401 `token_invalido` |
| Token vencido | Veja a segunda observação da seção 8.2 | 401 `token_expirado` |

Para ver o que há dentro de um token, sem conferir a assinatura:

```bash
python -c "import jwt, sys; print(jwt.decode(sys.argv[1], options={'verify_signature': False}))" "$TOKEN"
```

```text
{'sub': 'a712cd19-7914-4807-b5ee-a277fde52cee', 'nome': 'Ana', 'exp': 1791984736}
```

### 9.2 Pela página `/docs`

O FastAPI monta sozinho uma página de testes, que funciona em qualquer sistema. Abra `http://localhost:8002/docs`. Ela lista as três rotas.

1. Clique na rota e depois em **Try it out**.
2. Edite o JSON do corpo e clique em **Execute**. A resposta aparece logo abaixo, com o status.
3. Para o `GET /api/auth/me`, clique antes em **Authorize**, no alto da página, e cole o token, só o token, sem a palavra `Bearer`.

### 9.3 Com a tela de verdade

A tela e a API precisam estar no mesmo endereço, porque a tela chama `/api/auth/...` no endereço de onde ela mesma foi carregada. Com o gateway, basta subir tudo com o Docker Compose e abrir `http://localhost`: o `USAR_MOCK` já está em `false`. Siga então os passos 4 a 7 abaixo, trocando `http://localhost:8002/` por `http://localhost/`.

Para testar o exemplo da seção 8 sem o Docker, o próprio serviço de teste pode entregar os arquivos da tela:

1. Em `frontend/js/api.js`, confira que a linha 13 está como `const USAR_MOCK = false;`. É a única chave que importa aqui: as do Lobby e do Ranking, nas linhas 21 e 22, continuam em `true`.
2. Acrescente este trecho no **fim** do `main.py` de teste, depois de `app.include_router(rotas)`, trocando o caminho pelo da pasta `frontend` do repositório:

```python
# SÓ PARA TESTE LOCAL, enquanto não há Nginx: o próprio serviço entrega os arquivos da tela,
# para a tela e a API ficarem no mesmo endereço.
from fastapi.staticfiles import StaticFiles

app.mount("/", StaticFiles(directory="caminho/para/frontend", html=True))
```

3. Abra `http://localhost:8002/` e recarregue com Ctrl+Shift+R, para o navegador não usar uma cópia antiga do `api.js`.
4. Limpe o que o mock ou um teste anterior deixou guardado: aperte F12, vá ao Console e rode `localStorage.clear()`. Se sobrar um token antigo, a tela pula direto para `lobby.html`; nesse caso rode o comando ali mesmo e abra o endereço de novo.
5. Crie uma conta. O navegador vai para o lobby, que continua com as salas e o ranking falsos, porque as chaves dele seguem em `true`.
6. Confira o que ficou guardado: F12, aba Application (ou Armazenamento), Local Storage. `truco.token` tem que ser um JWT, com três partes separadas por ponto, e `truco.usuario` tem que ter `id`, `nome` e `email`.
7. Para voltar à tela de login, rode `localStorage.clear()` no Console e abra `http://localhost:8002/` de novo. Teste então o e-mail repetido e a senha errada: a `mensagem` do servidor tem que aparecer na caixa do cartão.

Abrir a tela por `python -m http.server`, como no desenvolvimento do frontend, não serve para este teste. Esse servidor não tem a API e responde 501 a qualquer envio.

### 9.4 Problemas comuns

| Sintoma | Causa provável |
|---|---|
| A tela mostra "Não foi possível concluir a operação (erro 422)." | O corpo do erro não está no formato do contrato. Falta o tratador de `RequestValidationError`, ou a rota espera formulário em vez de JSON (seção 3.2). |
| A tela mostra "Não foi possível concluir a operação (erro 401)." ou "(erro 409)." | O erro foi gerado com `HTTPException`, e o corpo saiu como `{"detail": ...}` (seção 4.4). |
| A tela mostra "O servidor está indisponível no momento…" | Erro no código do serviço: o terminal do Uvicorn mostra a exceção. Ou a tela foi aberta por um servidor que não tem a API (seção 9.3). |
| A tela mostra "Não foi possível conectar ao servidor…" | O serviço está parado ou levou mais de 10 segundos para responder. |
| A tela mostra "Algo deu errado. Tente de novo." | O login respondeu sucesso sem o campo `token`, por exemplo com `access_token`. O console do navegador mostra "Resposta do login sem token." |
| O cadastro funciona, mas a tela cai na aba Entrar com "Sua conta foi criada, mas não foi possível entrar agora…" | O login feito logo depois do cadastro falhou. Causas comuns: e-mail gravado de um jeito e buscado de outro (seção 7.2), senha alterada antes do hash, ou gravação ainda não confirmada no banco (seção 7.3). |
| A tela abre e pula direto para `lobby.html` | Sobrou um token no `localStorage`, do mock ou de um teste anterior. Rode `localStorage.clear()` no Console. |
| O `curl` recebe `dados_invalidos` com um JSON que parece certo | O comando foi rodado no PowerShell, que perde as aspas do JSON (seção 9.1). |
| No `/docs`, o `GET /api/auth/me` devolve 401 mesmo com token | Faltou clicar em **Authorize**, ou a palavra `Bearer` foi colada junto com o token. |
| `TypeError: Object of type UUID is not JSON serializable` ao fazer login | O `sub` recebeu o id como objeto UUID. Use `str(id)` (seção 6.3). |
| Todo token é recusado, e o erro do PyJWT é "Subject must be a string" | O `sub` foi emitido como número. Use `str(id)`. |
| O terminal mostra `InsecureKeyLengthWarning` | O segredo tem menos de 32 caracteres (seção 6.5). |

## 10. Pontos em aberto

### Diferenças entre a tela e o documento de contratos

- **P1. A tela ainda usa o mock. Em parte resolvido.** `USAR_MOCK` está em `false` em `frontend/js/api.js`, e o cadastro e o login vão ao Auth pelo gateway. Falta apagar o código do mock do Auth do arquivo, o que fica para o fechamento do projeto. O Lobby e o Ranking têm chaves e mocks próprios, que saem quando esses serviços estiverem no ar.
- **P2. `GET /api/auth/me` não é usado.** A rota está no contrato, mas nenhuma tela a chama. Decidir se o frontend passa a usá-la, por exemplo para conferir o token ao abrir o lobby, ou se ela fica só para testes.
- **P3. Logout sem rota.** O requisito RF02 pede login e logout, mas o contrato não tem rota de logout. Hoje sair é apagar o token do navegador, e o token continua valendo até vencer. Decidir se isso basta.
- **P4. Resposta do cadastro.** O contrato pede `id` e `nome`, mas não diz o status. A tela não lê o corpo e aceita qualquer status de sucesso. Este guia usa 201. **Resolvido:** o serviço responde 201.

### O que o código da tela assume sem estar escrito

- **P5. Códigos e status de erro.** O contrato define só o formato `{"erro", "mensagem"}`. `email_ja_cadastrado` (409) e `credenciais_invalidas` (401) foram escolhidos no mock da tela. `token_invalido` e `token_expirado` (401) são proposta deste guia. A tela de login não depende dos códigos, e o lobby também não: ele só olha o status ([guia do lobby](guia-backend-lobby.md), seção 5.3). **Resolvido:** a lista fechada, com os códigos do 404, do 405 e do 500, está na seção 4.2.
- **P6. Dados inválidos.** Nem a tela nem o mock têm código ou status para dados inválidos, porque a tela valida antes de enviar. A proposta é 422 `dados_invalidos`, já que 422 é o status que o FastAPI usa nesse caso. Confirmar, e decidir se a `mensagem` é única ou uma por regra. **Resolvido:** 422 `dados_invalidos`, com uma `mensagem` por regra, a mesma que a tela mostra, e uma geral para corpo fora do formato (seção 5).
- **P7. E-mail sem diferenciar maiúsculas de minúsculas.** O mock trata `Ana@Teste.com` e `ana@teste.com` como a mesma conta e devolve o e-mail em minúsculas. Isso não está no contrato. **Resolvido:** o serviço faz o mesmo (seção 7.2).
- **P8. Conta ativa na hora.** A tela faz o login automaticamente logo depois do cadastro. Isso exclui confirmação de e-mail ou qualquer etapa entre criar a conta e poder entrar. Confirmar que é o comportamento desejado. **Resolvido:** a conta vale na hora, e o cadastro só responde depois do commit.
- **P9. Regras e limites de validação.** Nome com até 20 caracteres, senha com no mínimo 6 e o formato do e-mail estão só no código da tela, não no documento de contratos. A tela não limita o tamanho máximo do e-mail nem da senha, não restringe os caracteres do nome e não exige nome único. O P14 do guia da mesa mostra que nomes repetidos se confundem no chat. Decidir os limites do servidor e avisar o frontend, para a tela validar igual. **Em parte resolvido:** o servidor aplica as mesmas regras da tela (seção 5), sem limite máximo para e-mail e senha. Continua em aberto se o nome deve ser único.
- **P10. Tempo de resposta.** A tela desiste de qualquer requisição depois de 10 segundos. Se um cadastro demorar mais que isso, a conta pode ser criada e a tela mostrar falha de conexão; na nova tentativa, o usuário recebe "e-mail já cadastrado". O valor não foi combinado com ninguém.
- **P11. Tipo do `id`.** O exemplo de estado do documento de contratos mostra `"usuario_id": "uuid"`. O mock devolve textos como `"mock-1"`, e a tela não interpreta o valor. Este guia assume UUID em formato de texto. **Resolvido:** o `id` é um UUID gerado pelo Postgres e vai como texto nas respostas e no `sub` do token.

### Token

- **P12. Conteúdo do token.** O contrato diz que cada serviço valida o JWT sozinho, mas não diz o algoritmo, os campos nem como o segredo é compartilhado. Este guia propõe HS256, `sub` com o id, `nome` e `exp`, e a variável de ambiente `JWT_SEGREDO`. Combinar com quem faz Lobby, Game e Ranking. O P17 do guia da mesa é a mesma pergunta, vista pelo Game. **Resolvido:** HS256, com `sub`, `nome` e `exp`, assinado com `JWT_SEGREDO`, o mesmo valor em todos os serviços (vem do `.env`). Lobby, Game e Ranking conferem o token sozinhos, como na seção 6.6, sem chamar o Auth.
- **P13. Expiração. Resolvido: 24 horas.** A tela não renova o token e não percebe quando ele vence: considera o usuário logado enquanto houver algo em `truco.token`. Quando uma rota que exige login responde 401, a tela apaga a sessão e volta para o login (seção 1.3). Como ela olha só o status, isso funciona com qualquer código de erro de token.
- **P14. Token de serviço dos bots.** O contrato diz que o bot se conecta ao Game com "um token de serviço", sem dizer quem emite esse token nem o que vai dentro dele. Se for um JWT assinado com o mesmo segredo, alguém precisa emiti-lo: o Auth ou o próprio serviço de Bots. Decidir.

### Decisões do backend

- **P15. Prefixo no Nginx.** Decidir se o gateway repassa o caminho inteiro (`/api/auth/login`), como este guia assume, ou se tira o prefixo (seção 3.1). A decisão muda uma linha no serviço e precisa ser a mesma para Auth, Lobby e Ranking. **Resolvido:** o gateway repassa o caminho inteiro, e as rotas são declaradas com o prefixo completo.
- **P16. Banco.** O README fala em um banco por serviço (`auth-db`), e o documento de contratos, em um schema por serviço (`auth`). Decidir qual vale. Falta também escolher a biblioteca de acesso ao Postgres e como a tabela é criada quando o banco sobe. **Resolvido:** um banco por serviço, cada um no seu container Postgres (`auth-db` para o Auth), acessado com o SQLAlchemy 2 e o psycopg 3. A tabela é criada pelo serviço ao subir, com `CREATE TABLE IF NOT EXISTS` (seção 7.1).
- **P17. Algoritmo de hash.** O exemplo usa argon2. Os requisitos também aceitam bcrypt, que exige limitar a senha a 72 bytes (seção 6.1). Decidir antes de existirem usuários de verdade: trocar depois obriga a conviver com os dois formatos. **Resolvido:** argon2 (argon2id, pacote `argon2-cffi`).
