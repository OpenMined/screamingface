---
ticket: OME-879
stack: aigateway
status: in_progress
started: 2026-08-18
finished:
---

# OME-879 — aigateway: POST /v1/models/admit — validate against OpenRouter catalog, register dynamically

## Intent

When a run asks for an OpenRouter model outside the seeded list, the engine will ask the
gateway whether the model really exists on OpenRouter. This unit gives the gateway that
answer surface: a `POST /v1/models/admit` endpoint that checks the dynamic-admission flag,
the id shape, provider enablement, credentials, and OpenRouter's public catalog (OME-479
discovery transport, TTL-cached) — then either registers the model live (in-memory, for the
deployment's lifetime) or refuses pre-spend with a diagnostic code naming which knob to
turn. Plan: `.dk/plans/2026-08-18-openrouter-dynamic-model-admission.md` (approved by Khoa
2026-08-18).

## Planned changes

- `apps/aigateway/src/aigateway/plugins/openrouter_provider/settings.py` — add
  `dynamic` flag (`AIGW_OPENROUTER_DYNAMIC`, default true).
- `apps/aigateway/src/aigateway/plugins/openrouter_provider/` — admission logic module
  (catalog lookup via existing discovery transport + TTL cache + refusal codes).
- Core route wiring for `POST /v1/models/admit` (exact placement per existing v1 route
  layout — resolved during DESIGN).
- Dynamic registration into the live model registry + admitted set.

## Test plan

- Flag off → refused (`dynamic_admission_disabled`).
- Provider disabled → `provider_disabled`; no credential → `provider_not_credentialed`.
- Catalog hit → admitted, ModelEntry registered, second admit idempotent.
- Catalog miss → `model_not_on_openrouter`, nothing registered.
- `~variant` id and non-OpenRouter-shaped id → refused (shape gate).
- Catalog fetch failure → distinct outage refusal, nothing registered.
- INVARIANT protected: seeded registrations and `AIGW_OPENROUTER_DEFAULT_MODELS`
  semantics unchanged; admission never persists anything.

## Acceptance

- `POST /v1/models/admit {"model_id": "openrouter/<org>/<slug>"}` admits a real catalog
  model so a subsequent completion for that id resolves (no 404), and refuses
  typos/disabled/uncredentialed cases with the distinct codes — all pre-spend.
- All aigateway gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus: `core/plugin_base/_ports.py` (`ModelAdmission` value
  type), `core/plugin_base/_provider.py` (default `admit_model` port, refuses),
  `core/plugin_base/__init__.py` (export), `core/discovery_runtime.py` (`client` property),
  `routes/model_admission.py` (the endpoint), `routes/models.py` + `routes/model_parameters.py`
  (admitted ids join listing/contract), `main.py` (state init + router),
  `plugins/openrouter_provider/{settings,discovery,plugin,admission}.py`,
  `tests/unit/openrouter/test_model_admission_route.py` (16 tests).
- **Commits:** feat(aigateway): dynamic OpenRouter model admission endpoint (this branch,
  `OME-878-dynamic-openrouter-admission`).
- **Gates:** `run_gates.py aigateway` — ALL GREEN (ruff check, format, pyright,
  check_no_enterprise, pytest cov≥80).
- **Deviations:** admission state lives on `app.state.admitted_models` (per-process dict)
  rather than "register into the live registry" — the gateway has no central mutable model
  table (the registry maps providers, `register_models()` is computed per call), and the
  chat path never gated on membership anyway, so app-state is the smallest true seam.
  Credential check is account-scoped via the chat path's own resolution (admission and
  dispatch cannot disagree). Extra refusal codes beyond the plan: `invalid_model_id`,
  `unknown_provider`, `dynamic_admission_unsupported`, `openrouter_catalog_unavailable`.


## Review fixes (2026-08-19, PR #633)

Ultrareview findings 6, 7, 9 land here as a follow-up commit on the same branch:

- **F6** — `_is_credentialed` no longer flattens reauth/pending profile states into
  "no key": the admission answer relays the chat path's own `auth_required` /
  `profile_pending_auth` code + message so the user is told to reconnect, not re-add.
- **F7** — the admitted set gets a named cap (`_MAX_ADMITTED_MODELS`); at capacity the
  route refuses with `admission_capacity_reached` instead of growing unboundedly.
  Real eviction/teardown is a follow-up design ticket, not invented here.
- **F9** — the shared `app.state.admission_catalog_cache` is namespaced per provider
  (`cache.setdefault(provider, {})`) so a second `admit_model` plugin cannot collide
  with OpenRouter's `ids`/`expires_at` keys.
