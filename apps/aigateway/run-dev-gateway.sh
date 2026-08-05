#!/bin/sh
# Local dev gateway for the OME-605 notebook flow: auth disabled (loopback only),
# OpenRouter enabled. The plugin owns its canonical model seeds; callers may still override them.
set -eu
cd "$(dirname "$0")"

export AIGATEWAY_AUTH_ENABLED=0
export AIGW_OPENROUTER_ENABLED=true

uv run aigateway migrate
exec uv run aigateway
