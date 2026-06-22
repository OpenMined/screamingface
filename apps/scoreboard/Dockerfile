FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY apps/scoreboard/pyproject.toml apps/scoreboard/uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY apps/scoreboard/src /app/src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="ScreamingFace benchmark scoreboard" \
      org.opencontainers.image.licenses="MIT"

ENV SCOREBOARD_HOST=0.0.0.0 \
    SCOREBOARD_PORT=9106 \
    SCOREBOARD_PORTAL_DIR=/app/web/portal \
    SCOREBOARD_PORTAL_ARTIFACTS_DIR=/app/web/artifacts \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin scoreboard

COPY --from=builder --chown=scoreboard:scoreboard /app /app
COPY --chown=scoreboard:scoreboard web/portal /app/web/portal
COPY --chown=scoreboard:scoreboard output_artifacts/eval_results/livetruth-latest.jsonl /app/web/artifacts/livetruth-latest.jsonl
COPY --chown=scoreboard:scoreboard output_artifacts/eval_results/livetruth-masking.dataset.jsonl /app/web/artifacts/livetruth-masking.dataset.jsonl

USER scoreboard

EXPOSE 9106

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9106/healthz', timeout=3).read()" || exit 1

ENTRYPOINT ["scoreboard"]
