# syntax=docker/dockerfile:1.7
# url4-cloud BACKEND image — the App: mints tokens, upgrades REST→WS, schedules Runner Jobs.
# (The Runner is its OWN image now — apps/url4-cloud/runner/Dockerfile — not a second entrypoint here.)
#
# INVARIANT: the build context is the REPO ROOT, not this dir:
#   docker build -f apps/url4-cloud/backend/Dockerfile -t url4-cloud:dev .
# WHY: backend/pyproject.toml path-depends on `url4` (../../../packages/url4), the shared
# libraries under ../shared/, and the runner under ../runner (local-dev mode drives the real
# Url4Executor in-process, so the backend depends on the runner package). All of those live
# outside backend/ — an app-scoped context cannot see them and `uv sync` fails. The repo
# layout is mirrored under /app so the editable installs' relative paths stay valid at runtime.
#
# The runtime shape matches the helm chart's securityContext (deploy/helm/values.yaml): non-root
# uid/gid 1000 owning the venv, `runAsNonRoot: true`-compatible, tini as PID 1 for clean SIGTERM.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# All path dependencies must exist before `uv sync` resolves the lockfile.
COPY packages/url4 ./packages/url4
COPY apps/url4-cloud/shared ./apps/url4-cloud/shared
COPY apps/url4-cloud/runner ./apps/url4-cloud/runner
COPY apps/url4-cloud/backend/pyproject.toml apps/url4-cloud/backend/uv.lock ./apps/url4-cloud/backend/
WORKDIR /app/apps/url4-cloud/backend
# Deps first (cache-friendly): busts only when pyproject/lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# Now the backend source (siblings above are already in place).
COPY apps/url4-cloud/backend/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="url4-cloud" \
      org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="url4-cloud backend — REST + WebSocket url4 execution control plane"
RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -d /app app
WORKDIR /app/apps/url4-cloud/backend
# INVARIANT: same absolute layout as the builder — editable installs resolve through these paths.
COPY --from=builder --chown=1000:1000 /app/packages/url4 /app/packages/url4
COPY --from=builder --chown=1000:1000 /app/apps/url4-cloud /app/apps/url4-cloud
ENV PATH="/app/apps/url4-cloud/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 1000
EXPOSE 9108
ENTRYPOINT ["tini", "--"]
# The App is the default; compose/k8s override `command` for the mock publisher.
# INVARIANT: AIGATEWAY_BASE_URL is NOT baked here — the App forwards it into each Runner Job from
# URL4_CLOUD_AIGATEWAY_BASE_URL, so the endpoint follows the deployment, not the artifact (§9).
CMD ["url4-cloud"]
