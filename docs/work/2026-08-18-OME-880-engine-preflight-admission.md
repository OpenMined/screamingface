---
ticket: OME-880
stack: url4-cloud
status: in_progress
started: 2026-08-18
finished:
---

# OME-880 — url4-cloud: admission on the model-parameters miss, runtime world overlay

## Intent

Engine half of OME-878. Reality check vs the plan: the engine has NO run-submission
preflight — the "not available on this Engine" refusal is raised client-side by the SDK from
the engine's `/v1/models` projection, and the engine's real per-model pre-spend seam is
`GET /v1/model-parameters` (404 `ModelNotInstalled`). So admission triggers THERE: on a miss
for an OpenRouter-shaped id, ask the gateway `POST /v1/models/admit`; a grant joins an
in-memory overlay beside the frozen declared world (deployment lifetime), invalidates the
catalog cache (so `/v1/models` lists it with a fresh ETag), and the parameter fetch proceeds;
a refusal is returned as a gateway-shaped 404 body carrying the diagnostic code (riding the
existing caller-correctable pass-through wire the SDK already decodes). Admitted ids reach
run processes via a new `URL4_EXTRA_MODELS` job-env key merged additively into the runner's
world — the `JobRunner.schedule` port (packages/url4) stays untouched.

## Planned changes

- `src/url4_cloud/catalog/admission.py` (new) — `AdmittedModels` overlay,
  `is_dynamically_admissible` shape gate, `AdmissionAnswer`, `ModelAdmissionSource` protocol.
- `src/url4_cloud/catalog/aigateway.py` — `admit_model` POST (endpoint missing/unreachable →
  "unsupported", never a crash).
- `src/url4_cloud/catalog/executable.py` — overlay-aware membership in both the catalog
  projection and the parameter source; admission trigger on the miss.
- `src/url4_cloud/catalog/cache.py` — `CachedCatalog.invalidate()`.
- `src/url4_cloud/catalog/__init__.py` — wiring (overlay + admission source + invalidation).
- `src/url4_cloud/job_env.py` — `EXTRA_MODELS` + to/from-env helpers + `WRITTEN_BY_APP`.
- `src/url4_cloud/world_config.py` — additive `URL4_EXTRA_MODELS` merge after `_apply_env`.
- `src/url4_cloud/adapters/{inprocess,k8s}.py` — `extra_models` provider written into run env.
- `src/url4_cloud/app.py` (+ local wiring) — hand the overlay's ids to the job runner.
- Tests: new files only; no existing test modified.

## Test plan

- Shape gate: only `openrouter/<a>/<b>` (no `~`, no `:`) triggers an admit call.
- Admitted: overlay updated, invalidation callback fired, parameter fetch forwarded,
  catalog projection lists the id with a changed ETag.
- Refused: 404 response whose body is the gateway's `{"detail": {code, ...}}` verbatim shape.
- Unsupported/unreachable admit endpoint (404/timeout/garbage) → plain `ModelNotInstalled`
  (today's behavior, INVARIANT: graceful fallback).
- `CachedCatalog.invalidate()` forces the next fetch upstream.
- `URL4_EXTRA_MODELS`: appended to the world additively; never replaces a declared spec;
  malformed value → loud `WorldConfigError` (App-written, so a bug, never caller input).
- Adapters write the key from the provider; absent provider → key absent.

## Acceptance

- With a fake gateway granting admission, `GET /v1/model-parameters?model=<unlisted>` returns
  200 and `GET /v1/models` then lists the id; with a refusing gateway, the 404 body carries
  the gateway's code; with no admit endpoint, behavior is byte-identical to today.
- All url4-cloud gates green; `test_declared_models_match_aigateway.py` untouched and green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned (`catalog/{admission,aigateway,executable,cache,__init__}.py`,
  `job_env.py`, `world_config.py`, `adapters/{inprocess,k8s,factory}.py`, `app.py`,
  `local.py`) + tests `tests/unit/test_dynamic_model_admission.py` (22) and
  `tests/unit/test_adapters_extra_models.py` (5). No existing test modified.
- **Commits:** feat(url4-cloud): dynamic model admission on the model-parameters miss (this
  branch, `OME-878-dynamic-openrouter-admission`).
- **Gates:** `run_gates.py url4-cloud` — ALL GREEN (ruff check/format, pyright,
  check_layering, pytest cov≥80). `test_declared_models_match_aigateway.py` untouched.
- **Deviations:** the planned "preflight admission call on a routes_for miss" does not exist
  as a seam — the engine has no run-submission preflight (the refusal is SDK-side). Admission
  therefore triggers on the `GET /v1/model-parameters` miss, which is the engine's actual
  per-model pre-spend surface. Refusals are returned as gateway-shaped 404 pass-through
  bodies (no new REST mapping). Added beyond plan: `URL4_CLOUD_EXTRA_MODELS` run-env overlay
  (adapter-construction `extra_models` provider) so admitted models are routable by run
  processes — without it the admission promise would break mid-run. Making the SDK's
  availability check defer to model-parameters is a third unit (`OME-881`, py-screamingface).


## Review fixes (2026-08-19, PR #633)

Ultrareview findings 1-5 land here as a follow-up commit on the same branch (paths now
`apps/screamingface-engine` after the OME-876 rename on main):

- **F1** — the admitted overlay heals on a forwarded 404: a parameters miss for an
  overlay id evicts it and re-runs admission once (grant -> retry fetch; refusal ->
  relay). A gateway restart now self-heals on the next request. `AdmittedModels`
  gains `discard()`; the invariant becomes "the overlay never contradicts the
  gateway's latest answer", not "add-only".
- **F2** — `default_model` is validated against `section.models` AFTER
  `_apply_extra_models` merges the overlay ids, so an overlay-delivered default boots.
- **F3** — `parse_config` no longer reads `URL4_CLOUD_EXTRA_MODELS` ambiently; extras
  become an explicit opt-in of the runner-boot path only, so the App's own parse can
  neither 503 on a malformed ambient value nor absorb un-admitted ids.
- **F4** — the K8s adapter always writes the `URL4_CLOUD_EXTRA_MODELS` env entry
  (explicit env wins over `envFrom`), neutralizing stale ConfigMap values exactly like
  the inprocess pop.
- **F5** — `CachedCatalog.invalidate()` expires entries (ages `fetched_at` past TTL)
  instead of deleting them, preserving the stale-on-error fallback bodies.

### Prior-test amendments (owner-approved 2026-08-19)

The append-only gate flagged these; the owner approved all three in-session:

1. `apps/screamingface-engine/tests/unit/test_runner_job_env_isolation.py` — the exact-set
   env assertion gains `URL4_CLOUD_EXTRA_MODELS` (F4 always writes it), with a dated
   justification comment mirroring the STREAM_GRACE_S precedent.
2. `packages/screamingface/tests/test_client_run.py` — two fake-engine handlers now 404
   details for unlisted models (fixture fidelity for F10's defer-all); every assertion
   byte-identical.
3. This PR's own test files — probe-count / empty-overlay pins overturned by F10/F4.

Final gate runs used `--skip-append-only` on that approval; all other gates unweakened.
