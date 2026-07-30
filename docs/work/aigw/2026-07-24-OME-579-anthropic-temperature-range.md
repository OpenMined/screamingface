---
ticket: OME-579
stack: aigateway
status: done
started: 2026-07-24
finished: 2026-07-24
---

# OME-579 — Anthropic temperature must advertise and enforce its real 0–1 range

## Intent

The gateway binds one shared OpenAI-compatible `temperature` schema (`[0, 2]`) for every
provider, but the Anthropic Messages API only accepts `[0, 1]` and the installed LiteLLM
transform forwards the value with no clamp. So `/v1/model-parameters` overclaims `maximum: 2`
for Anthropic models, and the fail-closed classifier accepts `temperature=1.5`, forwarding a
value the provider rejects with HTTP 400. Give Anthropic its own provider-local temperature
schema (`maximum: 1`) without touching the shared schema the OpenAI-compatible providers
correctly use, and fold each rule's validation schema into the contract-identity digest so a
range change actually invalidates cached contracts.

## Planned changes

- `apps/aigateway/src/aigateway/plugins/anthropic_provider/parameters.py` — add a
  provider-local `ANTHROPIC_TEMPERATURE_SCHEMA` (`number`, `[0, 1]`) and bind it to the
  `temperature` rule (replacing the shared `[0, 2]` schema for Anthropic only).
- `apps/aigateway/src/aigateway/core/model_parameter_contract.py` — include a canonical
  serialization of each rule's `schema` in `_rules_revision`.
- Tests: `apps/aigateway/tests/unit/anthropic/…` (temperature range: accept 1.0, reject 1.5,
  before dispatch), `apps/aigateway/tests/unit/core/test_model_parameter_contract.py` (schema
  change moves `contract_id`), and a guard that the shared schema still admits `2.0`.

## Test plan

- RED: Anthropic `temperature=1.5` (api_key) → rejected at classification (above maximum),
  before credential access.
- RED: the Anthropic detail contract advertises `temperature` with `maximum: 1`.
- RED: building a document with a rule whose schema differs only in `maximum` yields a
  different `contract_id`.
- Guard (stays green): an OpenAI-compatible provider still accepts `temperature=2.0`.

## Acceptance

- Anthropic `temperature` enforces + advertises `[0, 1]`; shared schema unchanged at `[0, 2]`.
- Out-of-range Anthropic temperature rejected before any credential access.
- A rule schema change moves `contract_id`.
- Full `aigateway` gate suite green.

## Outcome

- **Actual files (matches planned):**
  - `apps/aigateway/src/aigateway/plugins/anthropic_provider/parameters.py` — added
    provider-local `ANTHROPIC_TEMPERATURE_SCHEMA` (`number`, `[0, 1]`), bound it to the
    `temperature` rule, and dropped the now-unused shared `TEMPERATURE_SCHEMA` import.
  - `apps/aigateway/src/aigateway/core/model_parameter_contract.py` — added `_schema_key`
    (canonical `to_json_schema` serialization) and folded it into `_rules_revision`, so a
    rule's validation-schema change moves `contract_id`/`context.revision`.
  - `apps/aigateway/tests/unit/anthropic/test_anthropic_parameter_projection.py` — +3 tests
    (advertises `maximum == 1`; `temperature=1.5` rejected `malformed` before dispatch;
    `temperature=1.0` still reaches the installed transform).
  - `apps/aigateway/tests/unit/core/test_model_parameter_contract.py` — +1 test (a
    schema-only change moves both digests).
- **Commits:** landed within the OME-479 base snapshot `b9c219ad`
  (`feat(aigateway): per-provider chat parameter contract (OME-479 base)`). Every affected file
  was introduced in that same base snapshot, so there is no earlier committed intermediate state;
  the refinement is inseparable from the base and was folded into it;
  fixes from here on land as their own follow-up commits.
- **Gates:** ALL GATES GREEN — `run_gates.py aigateway`: append-only test check (vs HEAD),
  ruff check, ruff format --check, pyright, check_no_enterprise, `pytest --cov` (fail-under 80).
  Blast-radius suites `tests/unit/anthropic` + `tests/unit/core`: 295 passed.
- **Deviations:** no standalone commit (see above). No schema/model touched → no migration (stack
  rule S1 N/A). Shared `TEMPERATURE_SCHEMA` deliberately left at `[0, 2]`; the detail-shape
  test still asserts a `maximum: 2` schema renders, confirming no cross-provider narrowing.
