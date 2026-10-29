FROM ghcr.io/astral-sh/uv:0.9.26 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
ENV PATH="/app/backend/.venv/bin:$PATH"
USER 10001:10001
CMD ["python", "-m", "app.workers.main"]
