#!/bin/sh
# Local dev gateway for the OME-605 notebook flow: auth disabled (loopback only),
# OpenRouter enabled, seed models + claude-haiku-4-5 (the DRACO judge route).
set -eu
cd "$(dirname "$0")"

export AIGATEWAY_AUTH_ENABLED=0
export AIGW_OPENROUTER_ENABLED=true
export AIGW_OPENROUTER_DEFAULT_MODELS='["openrouter/anthropic/claude-haiku-4.5","openrouter/anthropic/claude-fable-5","openrouter/openai/gpt-5.5","openrouter/anthropic/claude-opus-4.8","openrouter/google/gemini-3.1-pro-preview","openrouter/google/gemini-3-flash-preview","openrouter/moonshotai/kimi-k2.6","openrouter/deepseek/deepseek-v4-pro","openrouter/qwen/qwen3.6-plus"]'

exec uv run aigateway
