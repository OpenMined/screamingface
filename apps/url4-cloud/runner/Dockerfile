# syntax=docker/dockerfile:1.7
# url4-cloud RUNNER image — the one-shot url4 execution Job (engine + aigateway connector).
# Separate from the backend (apps/url4-cloud/backend/Dockerfile): the backend SCHEDULES
# this image as a batch/v1 Job per run; it never runs in-process in prod (only local-dev does, via
# the backend's in-process runner). Slim by design — no fastapi/uvicorn/k8s-client/jwt/prometheus:
# the Runner only needs the url4 engine, the Bus, the streaming protocol, and httpx.
#
# INVARIANT: the build context is the REPO ROOT, not this dir:
#   docker build -f apps/url4-cloud/runner/Dockerfile -t url4-cloud-runner:dev .
# WHY: runner/pyproject.toml path-depends on `url4` (../../../packages/url4) and the shared
# libraries under ../shared/. The repo layout is mirrored under /app so the editable installs'
# relative paths stay valid at runtime.
#
# The runtime shape matches what K8sJobRunner._manifest hardens the Pod with (runAsNonRoot uid
# 1000, all caps dropped, read-only root) — tini as PID 1 so activeDeadlineSeconds / a stop tears
# the run down promptly with a clean SIGTERM.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Path dependencies must exist before `uv sync` resolves the lockfile.
COPY packages/url4 ./packages/url4
COPY apps/url4-cloud/shared ./apps/url4-cloud/shared
COPY apps/url4-cloud/runner/pyproject.toml apps/url4-cloud/runner/uv.lock ./apps/url4-cloud/runner/
WORKDIR /app/apps/url4-cloud/runner
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY apps/url4-cloud/runner/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="url4-cloud-runner" \
      org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="url4-cloud Runner — the one-shot url4 execution Job"
RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -d /app app
WORKDIR /app/apps/url4-cloud/runner
COPY --from=builder --chown=1000:1000 /app/packages/url4 /app/packages/url4
COPY --from=builder --chown=1000:1000 /app/apps/url4-cloud/shared /app/apps/url4-cloud/shared
COPY --from=builder --chown=1000:1000 /app/apps/url4-cloud/runner /app/apps/url4-cloud/runner
ENV PATH="/app/apps/url4-cloud/runner/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 1000
# No EXPOSE — the Runner is a one-shot Job that publishes to NATS, never serves a port.
ENTRYPOINT ["tini", "--"]
# The backend's K8sJobRunner sets `command: ["url4-cloud-runner"]` on each Job; this is the
# image default so a `docker run url4-cloud-runner` also boots the lifecycle.
CMD ["url4-cloud-runner"]
