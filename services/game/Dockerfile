# Imagem do serviço Game.
FROM python:3.14-slim

# Sem arquivos .pyc e com os logs do Python aparecendo na hora no "docker compose logs".
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /servico

# As dependências vêm antes do código: enquanto o requirements.txt não muda, o Docker reaproveita
# essa etapa e o build fica rápido.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código (engine/ e app/), testes e o script de partida de teste.
COPY . .

# O serviço roda com um usuário comum, sem os poderes do root.
RUN useradd --system --no-create-home game
USER game

# A porta 8000 só é alcançada dentro da rede do Docker Compose (pelo gateway e pelos serviços).
# --host 0.0.0.0: aceita conexões vindas de outros containers (o padrão, 127.0.0.1, não aceita).
# UM PROCESSO SÓ, sem --workers: as conexões da mesa ficam na memória do processo (P21 do guia
# da mesa; explicação em app/partidas.py).
# --ws-max-size: as mensagens da mesa são pequenas (o chat tem até 200 caracteres); uma maior
# que 64 KB derruba a conexão em vez de ocupar o servidor. O padrão seria 16 MB.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--ws-max-size", "65536"]
