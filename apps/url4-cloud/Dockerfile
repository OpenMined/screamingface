# syntax=docker/dockerfile:1.7
# url4-cloud image — ONE artifact, TWO modes (`url4_cloud.cli`):
#   url4-cloud serve   the control plane: mints tokens, upgrades REST→WS, schedules Runner Jobs
#   url4-cloud run     one url4 evaluation, streamed to NATS, then exit — what a Job runs
#
# This replaces the former pair of images. The run mode's dependencies were already a strict
# subset of the serving mode's, so a single image costs no new package — only the serving-side
# ones now sitting unused on a Job's disk. `.claude/scripts/check_layering.py` keeps the two
# halves' IMPORT graphs disjoint, which is what actually holds a Job's cold start down.
#
# INVARIANT: the build context is the REPO ROOT, not this dir:
#   docker build -f apps/url4-cloud/Dockerfile -t url4-cloud:dev .
# WHY: pyproject.toml path-depends on `url4` (../../packages/url4), which carries both the
# `url4.streaming` wire contract and the engine, and is outside this app's directory, so an
# app-scoped context cannot see it and `uv sync` fails. The repo layout is mirrored under /app so
# the editable install's relative paths stay valid at runtime.
#
# The runtime shape matches BOTH the helm chart's securityContext (deploy/helm/values.yaml) and
# what K8sJobRunner._manifest hardens each Job Pod with: non-root uid/gid 1000 owning the venv,
# `runAsNonRoot: true`-compatible, read-only rootfs, tini as PID 1 so activeDeadlineSeconds or a
# stop tears a run down promptly with a clean SIGTERM.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# All path dependencies must exist before `uv sync` resolves the lockfile.
COPY packages/url4 ./packages/url4
COPY apps/url4-cloud/pyproject.toml apps/url4-cloud/uv.lock ./apps/url4-cloud/
WORKDIR /app/apps/url4-cloud
# Deps first (cache-friendly): busts only when pyproject/lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
# Now the app source (siblings above are already in place).
COPY apps/url4-cloud/src ./src
COPY apps/url4-cloud/url4.toml ./url4.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="url4-cloud" \
      org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.description="url4-cloud — REST + WebSocket control plane and url4 run mode"
RUN apt-get update && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 1000 app && useradd -u 1000 -g 1000 -M -d /app app
WORKDIR /app/apps/url4-cloud
# INVARIANT: same absolute layout as the builder — editable installs resolve through these paths.
COPY --from=builder --chown=1000:1000 /app/packages/url4 /app/packages/url4
COPY --from=builder --chown=1000:1000 /app/apps/url4-cloud /app/apps/url4-cloud
# The DECLARED world the run mode evaluates against (`url4_cloud.runner.config`,
# DEFAULT_CONFIG_PATH). Endpoints are declared here, never discovered from the gateway catalog —
# the image decides what CAN exist. URL4_RUNNER_CONFIG overrides the path; a read-only rootfs is
# fine, it is read once at boot. Unused by the serving mode.
COPY --from=builder --chown=1000:1000 /app/apps/url4-cloud/url4.toml /etc/url4/url4.toml
ENV PATH="/app/apps/url4-cloud/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER 1000
EXPOSE 9108
ENTRYPOINT ["tini", "--"]
# Serving is the default mode, which is what keeps the chart's `command: [url4-cloud]` working.
# A Job overrides it with `["url4-cloud", "run"]` (adapters/k8s.py); compose/k8s likewise override
# it for the mock publisher.
# INVARIANT: AIGATEWAY_BASE_URL is NOT baked here — it reaches each Runner Job from the chart's
# runner-env ConfigMap, so the endpoint follows the deployment, not the artifact (§9).
CMD ["url4-cloud"]
