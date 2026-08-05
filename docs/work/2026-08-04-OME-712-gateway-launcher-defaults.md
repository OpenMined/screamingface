---
ticket: OME-712
stack: aigateway
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-712 — Keep local Gateway model discovery canonical

## Intent

Make the local notebook launcher enable OpenRouter without replacing the provider plugin's
canonical model seeds. This keeps newly registered models available locally without requiring a
second hand-maintained list in shell tooling.

## Planned changes

- Add an AI Gateway-owned executable contract test for `run-dev-gateway.sh`.
- Remove the launcher's `AIGW_OPENROUTER_DEFAULT_MODELS` override.
- Remove the URL4 Cloud test that parsed another app's private launcher.

## Test plan

- Execute the launcher with a fake `uv` command and assert that it migrates before serving, auth
  is disabled, OpenRouter is enabled, and the canonical-model override remains unset.
- Run the focused AI Gateway test and the applicable AI Gateway gates.

## Acceptance

- The local launcher inherits `OpenRouterPluginSettings.default_models`.
- The local launcher applies migrations before serving.
- Future canonical seed additions need no launcher edit.
- URL4 Cloud no longer parses AI Gateway's shell implementation.

## Outcome

- **Actual files:** `apps/aigateway/run-dev-gateway.sh` migrates before serving and does not export
  a copied model list; `apps/aigateway/tests/unit/openrouter/test_run_dev_gateway.py` executes the
  launcher against a fake `uv` and pins both command order and environment. The cross-app URL4
  Cloud launcher-parsing test was restored to HEAD and has no remaining diff.
- **Commits:** included in the migration/local-tooling review group.
- **Gates:** RED proved both the copied model override and missing migration step. Focused results
  are recorded in the parent Gateway ledger; the authoritative Linux gate remains pending there.
- **Deviations:** no new cleanup issue was created, per explicit user direction. The first full
  suite run exhausted macOS's 256-file soft limit and cascaded into SQLite fixture errors; an
  unchanged rerun with `ulimit -n 4096` was fully green.
