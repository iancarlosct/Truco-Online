# Imagem do serviço de Bots.
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
RUN useradd --system --no-create-home bots
USER bots

# A porta 8000 só serve ao healthcheck (/saude), dentro do próprio container: o serviço não
# recebe pedidos de ninguém, nem do gateway. Quem trabalha são os bots, que conectam ao Game.
# --host 0.0.0.0: como nos outros serviços, aceita conexões da rede do Docker Compose.
# UM PROCESSO SÓ, sem --workers: os bots de todas as partidas rodam juntos neste processo
# (asyncio), e o consumidor de eventos lê o broker com um nome fixo (app/eventos.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
