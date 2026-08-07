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

## Post-review corrections (2026-08-07)

Rebased onto `main` after the Benchmark foundation landed in the same composition roots, then
reviewed. Three corrections, all inside the r4 contract:

1. **An unusable declared world degrades discovery instead of stopping the Engine.**
   `build_executable_catalog_service` catches `WorldConfigError`, logs it at ERROR, and returns
   `None` — so both catalog routes answer the existing 503 while runs, streaming, connections and
   health keep serving. Raising in the App's composition root would have turned a
   discovery-scoped misconfiguration into a total control-plane outage, for a file whose only
   reader before r4 was the Runner. Reachable in practice: `url4.toml` instructs operators that
   ids must match AI Gateway's EXACTLY, and the Hugging Face provider seeds colon-qualified slugs
   that r4 now rejects. Fail-fast is kept where it decides correctness — the Runner, at Job start.
   Recorded in the spec §0.1; the two tests that pinned the raise now pin the degrade, plus a new
   HTTP-level test that `/v1/models` is 503 while `/healthz` is 200.
2. **One malformed Gateway model entry no longer fails the whole catalog.** Membership in the
   declared set is the entire filter: an entry that cannot state a declared id cannot be one, so
   it is omitted. Raising there let a single odd upstream document 502 every caller — and with
   stale-on-error, a persistent one would have become an outage after `stale_max_s`. The
   `data`-is-not-a-list check still raises: that shape cannot be projected at all.
3. **Documentation truthfulness at the seams this work moved.** The app README, the Helm
   ConfigMap operator comment, the `/v1/model-parameters` OpenAPI description and its 404/503
   texts, `rest/catalog.py`'s module docstring, `runner/__init__.py`'s layering statement (three
   shared leaves → four, with the reason), `check_layering.py`'s own module list, `job_env.py`'s
   error-name note, `url4.toml`'s header, and `world_config.py`'s format-mirror claim all still
   described the pre-r4 verbatim-proxy world.

The `assert source is not None` flagged in review was verified unreachable (`build_catalog_service`
guards on the same base URL) — replaced with expressed narrowing rather than an assertion, so a
future drift between the two guards degrades like an unconfigured deployment instead of raising.

- **Gates after corrections:** complete URL4 Cloud suite (977 passed, 5 skipped, 95.21% coverage);
  Ruff; format; Pyright; and the Engine/Runner layering check all pass.
