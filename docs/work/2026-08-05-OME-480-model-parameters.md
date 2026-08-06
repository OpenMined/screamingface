---
ticket: OME-480
stack: url4-cloud
status: in_progress
started: 2026-08-05
finished:
---

# OME-480 — expose AI Gateway model details through the Engine

## Intent

Expose AI Gateway's authoritative, profile-bound model-parameter contract through URL4 Cloud so
the Client can discover and preflight model parameters without bypassing the Engine or creating
a second parameter language.

## Planned changes

- `catalog/port.py` — model-detail response and source port.
- `catalog/aigateway.py` — identity-aware, uncached upstream request and envelope validation.
- `catalog/cache.py` — retain the uncached detail source in the existing client lifecycle.
- `app.py` — injectable model-parameter source.
- `rest/catalog.py` — public endpoint and private/no-store policy.
- `tests/unit/test_model_parameters_proxy.py` — new behavioral tests only.
- OME-480 task/spec/plan/work artifacts.

No schema/model migration applies.

## Test plan

- Verbatim successful v1 document, unknown fields, model query, identity/profile forwarding.
- Anonymous local request and no invented bearer token.
- Caller-correctable `4xx` pass-through.
- Mismatched/malformed success, `5xx`, timeout, transport, and non-JSON failures.
- ASGI success/error cache policy, RFC 9457 `502`/`503`/`504`, and OpenAPI visibility.
- Existing `/v1/models` tests remain unchanged and green.

## Acceptance

- All spec acceptance points hold.
- Existing tests are not edited.
- Full `url4-cloud` gates are green.

## Outcome

- **Actual files:** six URL4 Cloud modules, one new focused test module, and this task's
  task/spec/plan/work artifacts. No runner, connector, Benchmark, AI Gateway, URL4, SDK, Helm, or
  dependency file changed.
- **Behavior:** URL4 Cloud exposes uncached `GET /v1/model-parameters`, forwards the existing
  verified identity/profile, preserves valid v1 documents and caller-correctable JSON `4xx`, and
  fails closed for malformed or unavailable upstream responses.
- **Tests:** 29 focused detail tests; the complete URL4 Cloud suite passes with **522 passed, 5
  skipped**, and **96.70%** coverage.
- **Gates:** `python3 .claude/scripts/run_gates.py url4-cloud` — append-only, Ruff, formatting,
  Pyright, layering, and pytest/coverage all green.
- **Commits:** pending explicit handoff approval.
- **Deviations:** `CachedCatalog` retains a reference to the detail source for composition rather
  than implementing `ModelParameterSource`; this keeps the cache boundary honest while preserving
  one owned HTTP client and shutdown hook. Linear remains unchanged until the full stack is ready
  for review, as requested.
