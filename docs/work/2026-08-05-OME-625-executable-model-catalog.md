---
ticket: OME-625
stack: url4-cloud
status: done
started: 2026-08-05
finished: 2026-08-07
---

# OME-625 — make the Engine model catalog executable

## Intent

Correct the Engine catalog contract after a live quickstart exposed a model that AI Gateway
advertised but the Engine could not express or resolve as URL4. `GET /v1/models` must describe
the caller-visible subset of the Engine's declared model routes, not every model the downstream
Gateway can serve directly. The Gateway catalog remains unchanged and broad.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/catalog/` — project the caller-visible Gateway catalog onto
  the Engine's declared model ids and guard model-detail requests with the same set.
- `apps/url4-cloud/src/url4_cloud/local.py` and composition roots — inject the declared model
  set rather than letting discovery drift from the execution world.
- `apps/url4-cloud/src/url4_cloud/world_config.py` — share the complete declared-world parser
  across discovery and execution, rejecting ids that URL4 cannot render as expression paths.
- `apps/url4-cloud/tests/unit/` — add public HTTP/startup tests for the executable-catalog
  invariant, undeclared detail rejection, and invalid route configuration.
- `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md` — supersede the obsolete verbatim-proxy
  claim with the executable Engine catalog contract.

## Test plan

- RED: a Gateway-only, colon-qualified Hugging Face model is absent from Engine `/v1/models`.
- RED: Engine `/v1/model-parameters` rejects a model absent from the declared execution world
  without contacting AI Gateway.
- RED: runner configuration rejects an expression-path-incompatible declared model at startup.
- Preserve caller/profile catalog behavior for declared models and run the complete URL4 Cloud
  gate.

## Acceptance

- Every id returned by Engine `/v1/models` is a declared, URL4-executable model route.
- Gateway discovery remains unchanged; no alias, escaping fallback, or URL4 grammar change exists.
- Undeclared detail lookup fails before model spend with a clear Engine error.
- URL4 Cloud gates are green.

The separate Client candidate-authoring PR owns translating a manually supplied invalid Model id
into a typed planning error. Keeping that SDK behavior out of this Engine PR preserves the app
seam and does not weaken normal discovery: an invalid id is never advertised by the Engine.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** Engine catalog projection and error port, shared declared-route reader,
  production/local composition, Runner route-id validation, focused tests, and the existing model
  catalog specification.
- **Commits:** one local commit rebased directly onto `main`; it is not a stacked change.
- **Gates:** 47 focused executable-catalog/world-config tests; complete URL4 Cloud suite
  (879 passed, 5 skipped, 97.18% coverage); Ruff; format; Pyright; and the Engine/Runner layering
  check all pass. The full gate used its documented append-only override because moving and
  renaming the shared configuration types necessarily updates imports and type names in existing
  tests; their behavioral assertions are unchanged.
- **Deviations:** The SDK planning-error portion is intentionally assigned to the later Client
  candidate-authoring PR. No Gateway, URL4 package, Benchmark, authentication, deployment, or
  Client code is included here.
