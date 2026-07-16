# OME-400 — Production ScreamingFace quickstart SDK implementation plan

**Spec:** `docs/spec/2026-07-15-OME-400-screamingface-quickstart-sdk-spec.md`

## Scope decision

Implement the production-capable OME-400 GPQA quickstart surface. Real mode uses AI Gateway by
default; explicit mock mode exists for deterministic tests and committed notebook output. DRACO
remains a follow-on.

OME-400 does not change `apps/aigateway`. Until the gateway publishes provider authentication
capabilities through its HTTP API, the SDK keeps a clearly marked compatibility map for the six
current gateway providers. It still discovers which providers are loaded from `/v1/models` and
will prefer server-reported `auth_methods` when a separate gateway change adds that contract.

## Phase 1 — Register and scaffold

1. Register a `screamingface` stack rooted at `packages/screamingface` with format, lint,
   Pyright, Pytest, and 95% coverage gates.
2. Add package skeleton, README, `pyproject.toml`, local URL4 dependency wiring, lockfile, and
   examples/data directories.
3. Add path-filtered CI, release-please, CODEOWNERS, and Dependabot entries using URL4's package
   conventions.
4. Preserve all pre-existing dirty URL4 files.

## Phase 2 — Public API, session, and gateway client via TDD

1. RED: test public imports, zero-argument live defaults, explicit mock mode, discovery order,
   and static-widget/execution-mode independence.
2. GREEN: implement typed settings, in-memory Session registry, setup representations, and
   errors.
3. RED: contract-test gateway health, login/me, model discovery, temporary auth-capability
   mapping, API-key
   connection create/replace/remove, profile mapping, and chat against `httpx.MockTransport`—no
   app internals imported.
4. GREEN: implement the narrow `AIGatewayClient`, explicit OAuth and API-key onboarding APIs, and
   a provider-card setup panel driven by loaded gateway providers plus the compatibility map.
5. Add leak tests for passwords, JWTs, provider keys, OAuth tokens, reprs, logs, and errors.

## Phase 3 — Catalog and Fusion via TDD

1. RED: test live gateway-model intersection, versioned pricing provenance, unknown-price
   handling, and `max_price` validation.
2. GREEN: implement immutable model metadata/catalog and `sf.models.list`.
3. RED: test Fusion validation, judge membership, active-catalog membership, credential-free
   recipes, URL4 parse/render/compile round trips.
4. GREEN: implement `Fusion` using URL4 builders and rendering.

## Phase 4 — URL4-backed evaluation via TDD

1. RED: test `CompletionPort`, deterministic mock adapter, and AI Gateway adapter request shape,
   JWT/profile headers, timeouts, and typed errors.
2. RED: add an execution spy proving every panel answer traverses URL4 exactly once and baseline
   reuses those answers.
3. RED: test GPQA answer extraction, invalid outputs, majority voting, judge tie-breaking,
   incomplete rows, score/baseline/gain arithmetic, and provenance.
4. GREEN: implement URL4 adapter, evaluation service, immutable Run, and provenance accounting.
6. Refactor into focused files below the repository's 450-line guidance while all tests stay
   green.

## Phase 5 — Dataset decision and notebook

1. Do not bundle or render GPQA examples. Implement authorized gated GPQA Diamond loading for
   live mode and a clearly labeled 20-question synthetic science fixture for mock/CI mode.
2. Add a reviewable notebook source/generator and
   `packages/screamingface/examples/00_quickstart.ipynb`.
3. Execute from a clean environment using `sf.setup(mode="mock", static_widgets=True)`.
4. Verify outputs show URL4, mode, provenance, score/baseline/gain, and simulated cost status,
   with no secret or absolute path.
5. Re-execute and compare semantic output for mock determinism.

## Phase 6 — Live contract verification

1. Add opt-in tests controlled by explicit environment markers for a running AI Gateway.
2. Verify login/session or supplied JWT, model listing, profile selection, and a minimal fusion
   across at least two connected providers.
3. Never run live/spending tests in default CI and never commit credentials or live output as a
   stable benchmark claim.

## Phase 7 — Quality and handoff

1. Run the new package's registered gate runner and the existing URL4 suite.
2. Perform security, provenance, public-contract, simplicity, and confidence reviews.
3. Fill the work ledger with exact files, tests, coverage, deviations, and live-test status.
4. Commit conventionally on `OME-400-ship-quickstart-sdk` with `Refs: OME-400`.
5. Hand off the Linear package-label registration, exact ticket metadata sync, and notebook
   visual verification. Do not close without the required Linear comment/state transition.

## Approval gate

Implementation begins only after owner approval of this revised spec and plan in plain words.
