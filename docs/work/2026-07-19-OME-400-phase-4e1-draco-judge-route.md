---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 4E1 DRACO judge route

## Intent

Add the ordinary `gemini/3.1-pro-preview` model route required by the installed DRACO rubric
grader, assuming the AI Gateway owner registers the corresponding
`gemini-cli/gemini-3.1-pro-preview` model. Reuse the generic engine model adapter, preserve
plaintext URL4 results and existing error behavior, and make no URL4 or AI Gateway changes.

## Planned changes

- Add the public-to-Gateway model identity mapping to the ScreamingFace engine catalog with no
  tool capability.
- Advertise the route through the existing strict ScreamingFace registry.
- Add route-level tests for the exact judge request mapping, plaintext response, independent
  repeated calls, missing Gateway model, unavailable Gateway, invalid Gateway response, and
  unchanged URL4 error envelopes.
- Update the approved prior exact registry assertions, package/engine documentation, public
  contract, architecture plan, task mirror, and this ledger.

## Test plan

- First add a failing Phase 4E1 engine test module that expects the judge catalog identity and
  exercises the route through the real `Url4Node` ASGI surface with a controlled Gateway
  transport.
- Prove three identical judge requests produce three independent Gateway calls and return each
  assistant plaintext response without an engine envelope or cache.
- Prove Gateway HTTP rejection, connection failure, timeout, and malformed success responses are
  safe transient `502 resolution_failed` URL4 errors; retain the existing whole-evaluation
  `504 timeout` test.
- Run the complete SDK and engine suites, coverage, Ruff, Pyright, fixture/notebook drift, build,
  Compose validation, and stack gates.

## Acceptance

- `/.well-known/screamingface` advertises `gemini/3.1-pro-preview` with no tools.
- The route sends `gemini-cli/gemini-3.1-pro-preview`, system/user messages, temperature,
  max-tokens, and reasoning effort through the unchanged AI Gateway contract.
- Judge responses remain plaintext and repeated passes remain independent.
- Upstream failures are safe typed URL4 HTTP errors and trigger no automatic retry.
- No file under `packages/url4` or `apps/aigateway` changes.

## Outcome

- **Actual files:** added the one model mapping in the engine catalog and a Phase 4E1 route test
  module; updated the two owner-approved exact registry snapshots; regenerated the Phase 1
  notebook from its updated builder; and aligned the package/engine READMEs, public contract,
  architecture plan, task mirror, and this ledger.
- **Commits:** not committed; the owner will choose the commit point.
- **Gates:** 81 engine tests at 96.54% coverage and 367 package tests at 97.08% coverage; Ruff
  check/format, Pyright, fixture construction, notebook regeneration, wheel/sdist build, Compose
  validation, and `git diff --check` all green. The stack runner reported `ALL GATES GREEN` with
  `--skip-append-only`, recording the owner's explicit approval to update the two prior exact
  registry snapshots. No test was deleted, weakened, or runtime-skipped.
- **Behavior:** three identical `/v1` judge evaluations produced three independent AI Gateway
  calls with the exact mapped model, system/user messages, temperature, max-tokens, and reasoning
  effort, and returned three plaintext judge JSON bodies. Gateway 404, connection failure,
  timeout, and malformed success each produced one safe `502 resolution_failed` response with no
  retry.
- **Deviations:** provider-backed live success was not attempted because the Gateway model
  registration is an explicit external assumption. No file under `packages/url4` or
  `apps/aigateway` changed.
