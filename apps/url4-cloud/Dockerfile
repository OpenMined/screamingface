# url4-cloud — one image, two entrypoints (spec §1.1): the App (`url4-cloud`) and the Runner
# (`url4-cloud-runner`). The compose e2e (docker-compose.yml, spec §11) also runs the headless mock
# publisher `python -m url4_cloud.testing.mock_runner` from this same image. Owner-run — the headless
# test suite (`tests/integration/`) proves the flow without Docker/NATS (INFRA rule).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install deps first (cache-friendly), then the source.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# OCI image annotations (docs/protocol.md §9).
LABEL org.opencontainers.image.title="url4-cloud" \
      org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="url4-cloud — REST + WebSocket url4 execution runner"

EXPOSE 9108

# Default to the App; compose/k8s override `command` for the Runner or the mock publisher.
CMD ["url4-cloud"]
