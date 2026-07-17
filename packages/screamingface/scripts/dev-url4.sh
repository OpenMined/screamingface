#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCREAMINGFACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
URL4_DIR="$(cd "${SCREAMINGFACE_DIR}/../url4" && pwd)"
URL4_CONFIG="${URL4_CONFIG:-${SCREAMINGFACE_DIR}/url4.dev.toml}"
URL4_HOST="${URL4_HOST:-127.0.0.1}"
URL4_PORT="${URL4_PORT:-4404}"

echo "Starting the optional deterministic URL4 HTTP engine at http://${URL4_HOST}:${URL4_PORT}"
echo "The SDK uses the equivalent in-process node by default; this server is for HTTP testing."

cd "${URL4_DIR}"
exec uv run --extra server url4 serve \
    --config "${URL4_CONFIG}" \
    --host "${URL4_HOST}" \
    --port "${URL4_PORT}"
