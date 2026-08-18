---
ticket: OME-881
stack: screamingface
status: in_progress
started: 2026-08-18
finished:
---

# OME-881 — SDK: let the per-model details probe decide OpenRouter availability

## Intent

Third unit of OME-878, discovered during implementation: the SDK refuses missing models from
the `/v1/models` listing BEFORE the per-model `GET /v1/model-parameters` call — the exact
call that now triggers engine-side dynamic admission (OME-880). So for OpenRouter-shaped
missing ids the listing stops being the availability authority: the SDK probes the details
endpoint instead (already free and pre-spend), which either admits the model (run proceeds)
or answers 404 with the gateway's diagnostic code (decoded into a clear `PlanningError`).
Everything else keeps today's immediate refusal.

## Planned changes

- `src/screamingface/_evaluation/runner.py` — `_validate_required_models` returns the
  OpenRouter-shaped missing ids instead of refusing them; both workflows probe
  `load_model_details` for each before the parameter preflight.
- `src/screamingface/_engine/catalog.py` — `_raise_model_details_error` decodes the
  admission refusal codes into `PlanningError` (gateway message verbatim), and decodes the
  engine's plain RFC 9457 "not installed" 404 into today's `model_unavailable` wording.
- Tests: `tests/test_dynamic_admission_preflight.py` (new only).

## Test plan

- Missing OpenRouter model + engine grants → probe fires, run reaches the transport.
- Engine refuses with a code → `PlanningError` carrying that code + gateway message,
  transport never called ($0).
- Engine without admission (plain 404) → today's `model_unavailable` wording, pre-spend.
- Non-OpenRouter missing id and `~`/`:`-shaped ids → immediate refusal, no probe.
- Async path covered.

## Acceptance

- `sf.evaluate(sf.Model("openrouter/<real-but-unlisted>"), ...)` against an engine+gateway
  pair with OME-879/880 proceeds with only an OpenRouter key; typos refuse pre-spend with
  the catalog verdict. All screamingface gates green; no existing test modified.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `_evaluation/runner.py` (`_defers_to_details_probe`,
  `_validate_required_models` now returns the deferred tuple, both workflows probe),
  `_engine/catalog.py` (`_ADMISSION_REFUSAL_CODES` decode + `_raise_model_not_installed`),
  `tests/test_dynamic_admission_preflight.py` (8 tests). No existing test modified.
- **Commits:** feat(screamingface): defer OpenRouter availability to the details probe
  (this branch, `OME-878-dynamic-openrouter-admission`).
- **Gates:** `run_gates.py screamingface` — ALL GREEN (ruff check/format, pyright, pytest
  cov≥95, notebooks check, uv build, distribution check).
- **Deviations:** also decodes the Engine's plain RFC 9457 not-installed 404 into today's
  `model_unavailable` wording (previously that shape fell through to a generic
  `engine_contract_error`) — needed so an Engine without admission support answers the probe
  with the same message users see today.
