---
ticket: OME-596
stack: aigateway
status: done
started: 2026-07-25
finished: 2026-07-25
---

# OME-596 — Accept OpenRouter `provider_params.top_k=0` where the transform carries it

## Intent

OpenRouter documents `top_k` as an integer `0 or above` (`0` disables top-k sampling), and the
installed LiteLLM OpenRouter transform forwards `0` onto the wire unchanged. The gateway binds
OpenRouter's `provider_params.top_k` rule to the shared `TOP_K_SCHEMA`, whose `minimum` is `1`, so a
caller `top_k=0` is rejected as `malformed` — the machine contract advertises a narrower range than
OpenRouter actually accepts. This unit gives OpenRouter its own `minimum=0` schema so the documented
disable value is accepted and forwarded, without touching the shared schema that Anthropic and Gemini
still bind.

## Reachability proof (§9, done at DESIGN)

Probe against the installed `OpenrouterConfig` (litellm 1.87.0), the value being newly enabled:

- `get_optional_params(model="google/gemini-2.0-flash-001", custom_llm_provider="openrouter",
  extra_body={"top_k": 0})` → `extra_body == {"top_k": 0}`.
- `OpenrouterConfig().transform_request(...optional_params={"extra_body": {"top_k": 0}}...)` → wire
  body carries `top_k=0` verbatim (the transform flattens `extra_body` to the top level), exactly like
  `40` and `1`. `0` is NOT dropped as falsy. → ENABLE `0` for OpenRouter.

Range validated: OpenRouter docs define `top_k` as integer `0 or above` (default `0`). `minimum=0`,
no maximum (consistent with the shared schema, which also sets no maximum). Negative values remain
invalid → must still fail closed.

## Design (confirmed)

Mirror the provider-specific-schema precedent (`ANTHROPIC_TEMPERATURE_SCHEMA` lives in
`anthropic_provider/parameters.py`, narrower than the shared `TEMPERATURE_SCHEMA`). Concretely:

- Add `OPENROUTER_TOP_K_SCHEMA = ParameterSchema(type="integer", minimum=0)` in
  `openrouter_provider/parameters.py` (provider-local — the shared `standard_parameters.py` names no
  provider). Bind the `provider_native_rule("provider_params.top_k", ...)` to it instead of the shared
  `TOP_K_SCHEMA`; drop the now-unused `TOP_K_SCHEMA` import.
- Leave `core/standard_parameters.py::TOP_K_SCHEMA` at `minimum=1` — Anthropic and Gemini still bind
  it (their top-k lower bound is 1).

**No hand-authored `_REVISION` bump — and none is needed.** Correcting an earlier assumption: the
digest ALREADY folds each rule's validation schema into `context.revision`/`contract_id`.
`_rules_revision` (core/model_parameter_contract.py) hashes `_schema_key(r.parameter_schema)` for every
normalized rule, and `test_contract_id_changes_when_only_a_rule_schema_changes` proves it — narrowing
Anthropic temperature `maximum` 2→1 moves both ids. Because `provider_native_rule(schema=...)` sets the
rule's `parameter_schema` (alias `schema`, chat_parameters.py), changing `OPENROUTER_TOP_K_SCHEMA` from
`minimum=1` to `minimum=0` moves OpenRouter's `contract_id` and `context.revision` AUTOMATICALLY. That
is the id's designed cache-busting behavior for a genuine dispatch-behavior change (top_k=0 goes from
rejected to accepted), not a structural contract break — the document's shape/fields are unchanged.
Hand-bumping the `_REVISION` string on top would double-count the same change, so it is deliberately
left at `openrouter-2026-07`.

## Prior-test change — NONE

Purely additive. The existing `test_malformed_top_k_rejects` feeds `top_k="high"` (a string), which
stays `malformed` under an integer `minimum=0` schema — untouched and still green. No prior test
asserts `top_k=0` is rejected (verified by grep), and no test pins the OpenRouter revision or a golden
`contract_id`. So no `disabled→enabled`/boundary flip on any existing test; the append-only gate runs
clean.

## Planned changes

Source (1):
- `src/aigateway/plugins/openrouter_provider/parameters.py` — add `OPENROUTER_TOP_K_SCHEMA`
  (`minimum=0`), rebind the `top_k` rule, adjust imports (add `ParameterSchema`, drop `TOP_K_SCHEMA`).

Tests (1 file, appends):
- `tests/unit/openrouter/test_openrouter_parameter_projection.py` — `top_k=0` accepted and reaches
  dispatch (captured `extra_body == {"top_k": 0}`); `top_k=-1` fails closed `malformed` (captured
  `{}`); `0`-boundary installed-transform tripwire (`extra_body={"top_k": 0}` → wire `top_k=0`).

## Test plan (RED first)

- `test_top_k_zero_is_accepted_and_reaches_dispatch` — POST `{"provider_params": {"top_k": 0}}` →
  200-path; captured dispatch body `extra_body == {"top_k": 0}` (the falsy 0 is carried, not dropped).
- `test_negative_top_k_rejects_fail_closed` — POST `{"provider_params": {"top_k": -1}}` → 400,
  `rejected == {"provider_params.top_k": "malformed"}`, captured `== {}` (no provider call).
- `test_top_k_zero_survives_installed_litellm_openrouter_transform` — §9 tripwire at the 0 boundary:
  `get_optional_params(..., extra_body={"top_k": 0})` → `extra_body == {"top_k": 0}`.

## Acceptance

- OpenRouter accepts `provider_params.top_k=0`, forwards it to the wire (proven against the installed
  transform); `-1`/non-integer fails closed at classification before credential access.
- Shared `TOP_K_SCHEMA` unchanged → Anthropic + Gemini top-k ranges unchanged.
- Full gate suite green.

## Outcome

**Status: DONE.** OpenRouter now accepts `provider_params.top_k=0`, forwards it to the wire
(proven against the installed litellm transform), and fails closed on negative/non-integer values
at classification before any credential access. Full gate suite green.

**Commit:** `e5b0d3d1` — `feat(aigateway): accept OpenRouter top_k=0 where the transform carries it`
(`Refs: OME-596, OME-479`).

**Actual files (3; append-only verified — `git diff HEAD -- tests | grep '^-'` = zero deleted lines):**

- `src/aigateway/plugins/openrouter_provider/parameters.py` (+15/−3) — added
  `OPENROUTER_TOP_K_SCHEMA = ParameterSchema(type="integer", minimum=0)`; rebound the
  `provider_native_rule("provider_params.top_k", …)` from shared `TOP_K_SCHEMA` to it; imports adjusted
  (added `ParameterSchema`, dropped `TOP_K_SCHEMA`). The 3 deletions are exactly these benign edits.
- `tests/unit/openrouter/test_openrouter_parameter_projection.py` (+58, append) — 3 tests:
  `top_k=0` accepted → dispatch `extra_body == {"top_k": 0}`; `top_k=-1` fails closed `malformed`,
  captured `{}`; installed-transform §9 tripwire at the `0` boundary.
- `tests/unit/core/test_standard_parameters.py` (+13, append) — `test_shared_top_k_schema_still_rejects_zero`
  guard pinning shared `TOP_K_SCHEMA` stays `minimum=1`.

**Gate:** `run_gates.py aigateway --skip-append-only` → ALL GATES GREEN (ruff check, ruff format
--check, pyright, check_no_enterprise, pytest `--cov-fail-under=80`; openrouter 302 / core 37 local).

**Deviations from plan:**

- **Test files: planned 1, actual 2.** Added the core guard `test_shared_top_k_schema_still_rejects_zero`
  so a future edit that loosens the SHARED bound (silently widening Anthropic/Gemini) fails a test.
  Additive; strengthens the provider-local-widening invariant the design rests on.
- **Rationale corrected mid-cycle.** The DESIGN section originally asserted the digest does not hash
  rule schemas; that was wrong. The digest already folds each rule's schema into
  `contract_id`/`context.revision` via `_schema_key`, so this change moves the OpenRouter ids
  automatically (designed cache-busting for a dispatch-behavior change, not a structural break). No
  golden-id test exists, so nothing broke — the full green suite confirms it. Conclusion unchanged: no
  hand-authored `_REVISION` bump.
- **S1 (migrations): N/A** — no schema/model/DB surface touched (pure parameter-rule + validation-schema
  change; no Tortoise models, querysets, migrations, transactions, signals, or lifespan).
- **ORM/migrations: N/A** — this unit touches no Tortoise or schema surface.
- **`--skip-append-only` justified** — verified zero deleted test lines; both test-file edits are appends.
