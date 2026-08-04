---
ticket: OME-735
stack: aigateway
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-735 — aigateway dependency upgrade + PyJWT pin bump

## Intent

Clear the remaining real security alerts on `apps/aigateway` — 7 on `uv.lock` and 5 on
`pyproject.toml` after `OME-734` — by taking the dependency upgrade Dependabot cannot land on
its own, and bumping the one pinned package it can never propose.

Dependabot's group PR for this app has been red since 2026-07-28 (now #476, previously #436).
It fails on `uv run pyright`, not pytest, and no bot can fix it: the fix is a source change in
a test file, which Dependabot will not author.

`PyJWT` is the mirror-image problem. It carries a high-severity alert needing ≥2.13.0, but is
hard-pinned `==2.12.1`, so Dependabot sees no in-range update and has **never opened a PR for
it**. It is the only alerted package in the repo in that state.

## Root cause of the red gate

litellm 1.87 → 1.95 changed the signature of `AnthropicConfig._map_reasoning_effort`:

```
1.87: (reasoning_effort, model, llm_provider: str = "anthropic")
1.95: (reasoning_effort, model, custom_llm_provider, llm_provider: str = "anthropic")
                                ^^^^^^^^^^^^^^^^^^^ new, required, no default
```

Note it **added** a required parameter rather than renaming the old one — `llm_provider` is
still there with its `"anthropic"` default. That is why passing `custom_llm_provider="anthropic"`
reproduces the previous call exactly.

`tests/unit/anthropic/test_anthropic_thinking_decision.py` calls it at lines 143 and 161, so
pyright reports `Argument missing for parameter "custom_llm_provider"` twice.

That file is **designed** to fail this way. Its own comment states the invariant: the budget
table is not a guess, it is what the installed litellm actually emits, so a litellm upgrade
that changes the mapping fails the test instead of silently drifting the gateway's idea of
when the thinking constraint applies. The red gate is the alarm working.

## Decision (owner-approved — sdlc-python rule 5)

Editing a prior test is a Confidence-Gate decision. Asked and approved: pass
`custom_llm_provider="anthropic"` explicitly at both call sites.

This is a faithful adaptation rather than a weakening — 1.87's default for that parameter was
already `"anthropic"`, so the call reproduces the previous behavior exactly. Every assertion
survives untouched, and the drift alarm keeps working.

**AIDEV-NOTE for the next agent:** the test binds to a litellm **private** method (leading
underscore). That is why a routine minor bump breaks the build. Re-anchoring it onto the public
`litellm.get_optional_params` — already used further down the same file — was considered and
deliberately deferred; it is the better long-term shape if this recurs.

## Planned changes

- `apps/aigateway/pyproject.toml` — `PyJWT==2.12.1` → `==2.13.0`
- `apps/aigateway/uv.lock` — regenerated via `uv lock --upgrade`, which also carries litellm to
  1.94.x and clears the `idna` (≥3.15) and `pydantic-settings` (≥2.14.2) alerts
- `apps/aigateway/tests/unit/anthropic/test_anthropic_thinking_decision.py` — the two call sites

(Three further files proved necessary once the upgrade ran — see Outcome.)

No schema or model change, so stack rule S1 (migrations ship with the schema) does not apply.
No Tortoise ORM surface is touched, so the mandatory `tortoise-dev` companion does not trigger.

## Test plan

The failing signal already exists and is reproducible before any edit:
`uv run pyright` reports 2 errors at lines 143 and 161. That is this unit's RED.

Tests are append-only otherwise: the whole existing suite must stay green and unmodified apart
from the two approved call sites. The assertions that matter are the ones already present —
that the derived budget table still equals `MANUAL_THINKING_BUDGETS`
(`minimal/low: 1024, medium: 2048, high: 4096`) and that `"none"` still emits no budget. If
litellm 1.94 changed the *mapping* as well as the signature, those assertions fail and the
upgrade needs a real product decision rather than a signature patch.

## Acceptance

- `uv run pyright` clean, no `# type: ignore` escapes.
- Full gate list from the card green: ruff check · ruff format --check · pyright ·
  check_no_enterprise · pytest with `--cov-fail-under=80`.
- Alerts on `apps/aigateway/pyproject.toml` and `apps/aigateway/uv.lock` reduced to zero for
  `pyjwt`, `idna` and `pydantic-settings`.
- #476 closed as superseded.

## Outcome

- **Actual files — three more than planned.** The upgrade surfaced two failures the plan did
  not predict, one of them a real security gap:

  | File | Planned? | Why |
  |---|---|---|
  | `pyproject.toml` | yes | `PyJWT==2.12.1` → `==2.13.0` |
  | `uv.lock` | yes | `uv lock --upgrade` |
  | `tests/…/test_anthropic_thinking_decision.py` | yes | the `custom_llm_provider` call sites |
  | `src/…/core/request_hardening.py` | **no** | 4 new Datadog callback fields to strip |
  | `tests/unit/core/test_request_hardening.py` | **no** | the exact-set pin mirroring them |
  | `tests/unit/test_main.py` | **no** | FastAPI 0.141 route-introspection change |

- **Versions landed:** litellm 1.87 → **1.95.0**, fastapi 0.136.1 → **0.141.1**,
  pyjwt 2.12.1 → **2.13.0**, idna → **3.18**, pydantic-settings → **2.14.2**,
  cryptography 50.0.0, pydantic → 2.13.4, uvicorn → 0.52.1, ruff → 0.16.1.

- **Gates:** `run_gates.py aigateway` — **ALL GATES GREEN**. ruff check ✓ · ruff format --check ✓
  · pyright ✓ (no `# type: ignore` added) · check_no_enterprise ✓ · pytest ✓.
  **2645 passed, 40 skipped**, coverage **92.36%** against the 80% floor. Re-run on
  **Python 3.12** as well (CI matrix is 3.12/3.13): 2645 passed, 40 skipped.

### Deviation 1 — a real security gap, found by an existing test

`test_litellm_dynamic_callback_parameter_set_is_covered` asserts litellm's
`_supported_callback_params` is a subset of `DISPATCH_CONTROL_FIELDS`. litellm 1.95 added four
Datadog params — `dd_api_key`, `dd_agent_host`, `dd_agent_port`, `dd_site` — that the gateway
was **not** stripping.

That is caller-injectable: `dd_api_key` is a credential, and the host/port/site fields redirect
where prompt and response telemetry is shipped. Same exfiltration category as the
langfuse/arize/braintrust host+key fields already in the list. Fixed in production code
(`_CALLBACK_DYNAMIC_FIELDS`), which is the correct direction — the test was right and the code
was behind.

This is the strongest argument in this whole epic for keeping dependency bumps flowing: the gap
existed the moment litellm shipped 1.95, and only the upgrade revealed it.

### Deviation 2 — FastAPI 0.141 changed route introspection

`test_create_app_mounts_provider_auth_router` scanned `app.routes` for a matching `.path`.
FastAPI 0.141 no longer flattens included routers into `app.routes`; it stores lazy
`_IncludedRouter` wrappers, so the scan finds nothing.

**Product behavior is unchanged** — verified directly: `app.openapi()["paths"]` still lists
`/v1/auth/dummy/ping`, and a real request returns **200**. Blast radius checked: no production
code introspects `app.routes` (`_describe_admin_security` wraps `app.openapi`, which uses
FastAPI's own machinery). The test now asserts through a real `TestClient` request, which is
strictly stronger than the scan it replaced.

### Deviation 3 — three owner approvals under sdlc rule 5

Every prior-test change was stopped on and approved before being made:

1. `test_anthropic_thinking_decision.py` — pass `custom_llm_provider="anthropic"`. Faithful:
   1.87's `llm_provider` default was already `"anthropic"`, and 1.94 **added** the new
   parameter rather than renaming the old one, so the call is behaviourally identical.
2. `test_request_hardening.py` — extend the exact-set pin with the 4 `dd_*` names.
3. `test_main.py` — re-assert via a real request.

The repo's own `run_gates.py` append-only check fired on the first of these and blocked the
run, which is exactly what it is for. Re-run with the script's documented
`--skip-append-only` flag **after** approval — the flag is the sanctioned path for an approved
Confidence-Gate change, not a weakening of the gate.

### Not applicable

No schema or model change, so stack rule S1 does not apply. No Tortoise ORM surface touched,
so the mandatory `tortoise-dev` companion did not trigger.
