FROM python:3.10-slim

# 1. Системные зависимости
RUN apt-get update \
 && apt-get install -y curl dnsutils gcc libffi-dev libssl-dev openssh-client openssl \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# 2. Рабочая директория
WORKDIR /app

# 3. Зависимости
# Делает установку устойчивее к сетевым таймаутам
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
COPY requirements.txt ansible-requirements.yml ./
RUN python -m pip install --upgrade pip setuptools wheel \
 && pip install --timeout=120 --retries 5 -r requirements.txt \
 && ansible-galaxy collection install -r ansible-requirements.yml

# 4. Кладём код (storage.py лежит здесь же)
COPY . .

# 5. Папка для БД
RUN mkdir -p data

ENV PYTHONUNBUFFERED=1
CMD ["python", "main.py"]
