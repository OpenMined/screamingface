FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /workspace/packages/screamingface/apps/sf-url4-engine

COPY packages/url4 /workspace/packages/url4
COPY packages/screamingface /workspace/packages/screamingface

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="Temporary ScreamingFace URL4 engine development profile" \
      org.opencontainers.image.licenses="MIT"

ENV URL4_HOST=0.0.0.0 \
    URL4_PORT=4404 \
    PATH="/workspace/packages/screamingface/apps/sf-url4-engine/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/packages/screamingface/apps/sf-url4-engine

RUN useradd --system --uid 1000 --create-home app

COPY --from=builder --chown=app:app /workspace /workspace

USER app

EXPOSE 4404

HEALTHCHECK --interval=30s --timeout=5s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4404/healthz', timeout=3).read()" || exit 1

ENTRYPOINT ["sf-url4-engine"]
