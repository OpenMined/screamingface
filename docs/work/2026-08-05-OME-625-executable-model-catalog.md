---
ticket: OME-625
stack: url4-cloud
status: in_progress
started: 2026-08-05
finished:
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
- `apps/url4-cloud/src/url4_cloud/runner/config.py` — reject declared ids that URL4 cannot render
  as expression paths.
- `apps/url4-cloud/tests/unit/` — add public HTTP/startup tests for the executable-catalog
  invariant, undeclared detail rejection, and invalid route configuration.
- `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md` — supersede the obsolete verbatim-proxy
  claim with the executable Engine catalog contract.
- `packages/screamingface/` — turn a manually supplied invalid Engine route into a typed planning
  failure at Candidate compilation, with a focused planning test.

## Test plan

- RED: a Gateway-only, colon-qualified Hugging Face model is absent from Engine `/v1/models`.
- RED: Engine `/v1/model-parameters` rejects a model absent from the declared execution world
  without contacting AI Gateway.
- RED: runner configuration rejects an expression-path-incompatible declared model at startup.
- RED: compiling a manually supplied colon-qualified SDK Model raises a stable PlanningError
  rather than leaking URL4's RenderError.
- Preserve caller/profile catalog behavior for declared models and run both complete stack gates.

## Acceptance

- Every id returned by Engine `/v1/models` is a declared, URL4-executable model route.
- Gateway discovery remains unchanged; no alias, escaping fallback, or URL4 grammar change exists.
- Undeclared detail lookup and manual invalid SDK routes fail before model spend with clear errors.
- url4-cloud and screamingface gates are green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:** not committed; the user is reviewing the stacked work before any commit action.
- **Gates:**
- **Deviations:**
