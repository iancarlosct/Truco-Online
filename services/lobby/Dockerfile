# Imagem do serviço Lobby.
FROM python:3.14-slim

# Sem arquivos .pyc e com os logs do Python aparecendo na hora no "docker compose logs".
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /servico

# As dependências vêm antes do código: enquanto o requirements.txt não muda, o Docker reaproveita
# essa etapa e o build fica rápido.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código e testes (os testes rodam neste mesmo container).
COPY . .

# O serviço roda com um usuário comum, sem os poderes do root.
RUN useradd --system --no-create-home lobby
USER lobby

# A porta 8000 só é alcançada dentro da rede do Docker Compose (pelo gateway). O host não a vê.
# --host 0.0.0.0: aceita conexões vindas de outros containers (o padrão, 127.0.0.1, não aceita).
# UM PROCESSO SÓ, sem --workers: o consumidor de eventos lê o broker com um nome fixo
# (app/eventos.py). As travas das salas ficam no Postgres e valeriam com vários processos.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
