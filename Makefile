# ScreamingFace dev commands. Run `make help` for the full list.
#
# Each subproject under apps/ has its own uv environment; the targets
# below dispatch into the right directory so you don't have to remember
# where each project lives.

.PHONY: help \
        sync sync-server sync-aigateway \
        run-server run-aigateway \
        test test-server test-aigateway test-aigateway-live test-e2e \
        lint lint-server lint-aigateway \
        fmt fmt-server fmt-aigateway \
        typecheck typecheck-server typecheck-aigateway \
        check-no-enterprise \
        clean

SERVER_DIR := apps/server
AIGW_DIR   := apps/aigateway

# --- Default ---------------------------------------------------------------

help:  ## Show this help.
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Sync ------------------------------------------------------------------

sync: sync-server sync-aigateway  ## Sync deps for every subproject.

sync-server:  ## uv sync apps/server.
	cd $(SERVER_DIR) && uv sync

sync-aigateway:  ## uv sync apps/aigateway.
	cd $(AIGW_DIR) && uv sync

# --- Run -------------------------------------------------------------------

run-server:  ## Start screamingface server (reads sf.json).
	cd $(SERVER_DIR) && uv run sf run

run-aigateway:  ## Start aigateway on :9105 with live reload.
	cd $(AIGW_DIR) && uv run uvicorn aigateway.main:app --port 9105 --reload

# --- Test ------------------------------------------------------------------

test: test-server test-aigateway  ## Run the full unit-test suite (no live).

test-server:  ## apps/server unit tests.
	cd $(SERVER_DIR) && uv run pytest

test-aigateway:  ## apps/aigateway unit tests (skips live).
	cd $(AIGW_DIR) && uv run pytest -m "not live"

test-aigateway-live:  ## apps/aigateway live e2e (requires real OAuth creds in keychain).
	cd $(AIGW_DIR) && AIGW_LIVE=1 uv run pytest tests/live/ -v

test-e2e:  ## apps/server parallel CLI e2e (claude/codex/gemini/multi).
	cd $(SERVER_DIR) && bash scripts/run_e2e_parallel.sh

# --- Lint / format / typecheck --------------------------------------------

lint: lint-server lint-aigateway  ## Ruff lint every subproject.

lint-server:
	cd $(SERVER_DIR) && uv run ruff check .

lint-aigateway:
	cd $(AIGW_DIR) && uv run ruff check .

fmt: fmt-server fmt-aigateway  ## Ruff format every subproject.

fmt-server:
	cd $(SERVER_DIR) && uv run ruff format .

fmt-aigateway:
	cd $(AIGW_DIR) && uv run ruff format .

typecheck: typecheck-server typecheck-aigateway  ## Pyright every subproject.

typecheck-server:
	cd $(SERVER_DIR) && uv run pyright

typecheck-aigateway:
	cd $(AIGW_DIR) && uv run pyright

# --- LiteLLM licensing guard ----------------------------------------------

check-no-enterprise:  ## Fail if any aigateway code imports LiteLLM Enterprise.
	cd $(AIGW_DIR) && uv run python scripts/check_no_enterprise.py

# --- Cleanup ---------------------------------------------------------------

clean:  ## Remove caches and build artefacts.
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
