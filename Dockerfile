FROM python:3.13-slim

RUN apt-get update && apt-get install -y pipx curl && rm -rf /var/lib/apt/lists/*
RUN pipx ensurepath
RUN pipx install poetry

ARG ENGINE_VERSION=v1.0.0

WORKDIR /app

RUN ARCH=$(arch | sed s/aarch64/arm64/ | sed s/x86_64/amd64/) && \
    curl -o engine -L https://github.com/CSSE6400/ageoverflow-engine/releases/download/${ENGINE_VERSION}/engine-${ENGINE_VERSION}-linux-${ARCH} && \
    chmod +x engine

COPY pyproject.toml poetry.lock* ./
RUN pipx run poetry install --no-root

COPY application application

EXPOSE 8080

CMD ["pipx", "run", "poetry", "run", "flask", "--app", "application", "run", "--host", "0.0.0.0", "--port", "8080"]