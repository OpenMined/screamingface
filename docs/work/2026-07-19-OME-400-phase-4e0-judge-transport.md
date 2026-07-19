---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 4E0 safe judge transport

## Intent

Make arbitrary model and DRACO judge context safe to carry through native URL4 bindings, and make
the configured engine's transactional GET size an explicit preflighted capability. Preserve URL4's
expression-as-address contract, plaintext responses, and the single engine-only SDK boundary.

## Planned changes

- Change the ScreamingFace model-expression compiler to bind literal context as quoted URL4 data
  before referencing it from the model route.
- Extend the strict ScreamingFace engine registry with a required encoded request-target byte
  limit and expose it through the immutable SDK profile.
- Measure complete encoded `/v1?q=...` targets before any selected Fusion or rubric-judge spend,
  raising a typed SDK error when the configured engine cannot carry them.
- Enforce the same 60 KiB request-target boundary in the engine ASGI wrapper with HTTP 414, and
  configure Uvicorn/h11 with 128 KiB of parsing headroom.
- Update the public contract, architecture plan, task mirror, package and engine READMEs, and this
  work record. Do not modify `packages/url4` or `apps/aigateway`.

## Test plan

- First add failing compiler tests proving unmatched parentheses, quotes, backslashes, dollar
  literals, multiline content, and the pinned judge prompt round-trip through a real `Url4Node`
  while returning only model plaintext.
- Add failing strict-registry tests for the required positive integer byte limit and unknown or
  malformed limit fields.
- Add failing SDK execution and grading tests proving exact encoded-size preflight happens before
  any model/judge request and reports actual versus allowed bytes through a typed error.
- Add failing engine settings/ASGI/CLI tests for the 60 KiB default, configurable validation,
  exact boundary behavior, HTTP 414 JSON, registry advertisement, and 128 KiB h11 headroom.
- Run the complete SDK and engine suites, coverage, Ruff, Pyright, fixture/notebook drift, build,
  lock, Compose, stack gates, and a real local HTTP request above the old 16 KiB h11 default.

## Acceptance

- `compile_model_expression()` accepts arbitrary context without ambiguous URL4 structure and the
  addressed model receives byte-equivalent logical context and intent.
- Engine registry and SDK agree on `max_request_target_bytes=61440` for the local profile.
- Oversize Fusion and judge work fails before paid calls; the engine independently rejects direct
  oversize callers with HTTP 414 and `request_target_too_large`.
- A valid judge-shaped request larger than 16 KiB crosses real local Uvicorn HTTP successfully.
- Existing public workflows, plaintext result contracts, and tool-free/tool-enabled behavior stay
  green without compatibility fallbacks.

## Outcome

- **Actual files:** updated the SDK compiler, engine HTTP helpers, strict profile decoder,
  execution/grading preflight, public error exports, engine settings/catalog/app/ASGI/CLI and
  Compose profile; added Phase 4E0 SDK and engine tests; updated the approved prior exact-contract
  fixtures; regenerated the Phase 1 notebook; and aligned the package/engine READMEs, public spec,
  architecture plan, task mirror, and this ledger.
- **Commits:** not committed; the owner requested implementation and will choose the commit point.
- **Gates:** 361 SDK tests at 97.08% coverage; 75 engine tests at 96.54% coverage; Ruff check and
  format, Pyright, fixture construction, notebook regeneration, wheel/sdist build, Compose config,
  and `git diff --check` all green. The full stack runner reported `ALL GATES GREEN` with
  `--skip-append-only`, which records the owner's explicit Confidence-Gate approval to update four
  prior exact registry fixtures. No test was deleted, weakened, or runtime-skipped.
- **Live HTTP:** a real Uvicorn process accepted and evaluated a 40129-byte encoded URL4 GET with
  HTTP 200. A 62018-byte encoded GET reached the ASGI boundary and returned HTTP 414 with
  `request_target_too_large` and the advertised 61440-byte limit.
- **Deviations:** the reviewed draft used a 128 KiB application limit and 256 KiB h11 allowance.
  Live verification exposed `httpx`'s 65536-byte absolute-URL ceiling. With owner approval, the
  final contract uses a 60 KiB application limit (4096 bytes of origin headroom) and 128 KiB h11
  allowance. No `packages/url4` or `apps/aigateway` file changed.
