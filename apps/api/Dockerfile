FROM python:3.14.6-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14.6-slim-bookworm
RUN useradd --create-home --uid 10001 hibi
WORKDIR /app
COPY --from=builder --chown=hibi:hibi /app/.venv .venv
USER hibi
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "hibi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
