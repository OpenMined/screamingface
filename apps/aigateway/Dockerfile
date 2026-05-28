FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY apps/aigateway/pyproject.toml apps/aigateway/uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY apps/aigateway/src /app/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="ScreamingFace AI Gateway" \
      org.opencontainers.image.licenses="MIT"

ENV AIGW_HOST=0.0.0.0 \
    AIGW_PORT=9105 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --system --uid 1000 --create-home app

COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 9105

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9105/healthz', timeout=3).read()" || exit 1

ENTRYPOINT ["aigateway"]
