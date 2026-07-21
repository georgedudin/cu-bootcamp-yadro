# Build context is the REPO ROOT (docker cannot COPY ../contracts from a
# per-service context) — see infra/docker-compose.yml.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /usr/local/bin/

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Layer caching: resolve deps from manifests only, then copy source
COPY pyproject.toml uv.lock ./
COPY contracts/pyproject.toml contracts/
COPY core/pyproject.toml core/
COPY backend/pyproject.toml backend/
COPY ml/pyproject.toml ml/
RUN uv sync --frozen --package backend --no-dev --no-install-workspace

COPY contracts/ contracts/
COPY core/ core/
COPY backend/ backend/
RUN uv sync --frozen --package backend --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Single migration writer: the backend migrates at startup; workers never do
CMD ["sh", "-c", "alembic -c core/alembic.ini upgrade head && uvicorn backend.main:app --host 0.0.0.0 --port 8000"]
