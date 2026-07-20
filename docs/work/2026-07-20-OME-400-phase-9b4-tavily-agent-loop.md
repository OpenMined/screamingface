---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 9B.4 Tavily agent loop

## Intent

Replace the temporary SearXNG research path with the approved engine-owned Tavily service and a
bounded multi-turn agent loop for explicitly verified Hugging Face model/provider routes. Keep the
ScreamingFace SDK isolated from AI Gateway and Tavily, keep generic URL4 unchanged, and continue
returning only final plaintext model answers through URL4.

## Planned changes

- Add strict engine-side parsing for typed benchmark tool policy serialized as scalar URL4
  parameters, separating model parameters, loop controls, and Tavily request policy.
- Replace the connection-only Tavily adapter with one process-local service that owns credential
  validation, bounded search/extract HTTP calls, retries, response normalization, and safe errors.
- Replace the SearXNG executor with a bounded Hugging Face agent loop that preserves assistant tool
  calls, appends normalized tool messages, and stops on final plaintext or explicit budget failure.
- Advertise `web_search` and `web_fetch` only on the two approved DeepInfra-pinned Hugging Face
  routes when AI Gateway discovers them, and include Tavily in SDK connection preflight.
- Remove all SearXNG code, Compose services, settings, tests, documentation, and fallback behavior;
  raise the configurable local whole-evaluation timeout to the approved 15-minute default.
- Update the approved contract, task/plan records, engine README, and deterministic fixtures where
  the implemented boundary is documented.

## Test plan

- RED: engine policy parsing covers exact valid search/extract policies, unknown or malformed
  fields, contiguous domain indices, missing declarations, unsupported routes, and missing Tavily.
- RED: Tavily service covers validation, search/extract body mapping, bounded normalized responses,
  retries, authentication invalidation, rate limits, transport failures, malformed successes, and
  secret-safe error behavior using injected HTTP transports.
- RED: the agent loop covers tool-free execution, one/multiple tool rounds, sequential tool calls,
  preserved call IDs, invalid model arguments returned as tool results, per-turn/total/round limits,
  final plaintext, and explicit exhaustion/failure behavior.
- RED: registry, SDK preflight, settings, Compose, and documentation tests prove exact-route tool
  claims, Tavily connection requirements, the 15-minute timeout, and total SearXNG removal.
- GREEN: run focused tests, full SDK and engine suites, deterministic fixtures/notebooks, typing,
  lint/format, coverage, and the authoritative ScreamingFace gate.

## Acceptance

- A typed tool-enabled benchmark request can execute URL4 -> verified HF model through AI Gateway
  -> Tavily search/extract -> the same HF model -> final plaintext without SDK service access.
- Tool-free requests remain one AI Gateway call; reducers and graders remain tool-free.
- Unsupported or malformed policy fails before model spend; missing Tavily fails before Gateway
  spend; secrets and raw upstream bodies never enter URL4, model messages, responses, or logs.
- No SearXNG implementation, configuration, documentation, service, or compatibility fallback
  remains in the current product tree.
- All ScreamingFace quality gates pass at or above their existing coverage thresholds.

## Outcome

- **Actual files:** added strict engine policy parsing, the process-local Tavily execution service,
  bounded agent-loop execution, application-owned safe error translation, exact HF capability
  overlays, SDK tool-service preflight, and deterministic Phase 9B.4 tests. Removed the superseded
  SearXNG service/settings, direct-page adapter, connection-only Tavily module, and their legacy
  tests. Updated Compose, active contracts, task/plan records, skills, README files, and the
  generated architecture and DRACO Preview notebooks.
- **Commits:** not created in this work slice.
- **Gates:** authoritative `screamingface` gate green: Ruff lint/format, Pyright, SDK tests at the
  existing 95% coverage threshold, 203 engine tests at 95.10% coverage, deterministic fixtures,
  generated-notebook freshness, and wheel/sdist build. Focused Phase 9B.4 and notebook contracts
  also pass.
- **Deviations:** the append-only test check was intentionally skipped because the approved clean
  break deletes the obsolete SearXNG tests rather than retaining legacy coverage. Live HF/Tavily
  credential acceptance and canonical DRACO execution remain the separately approved Phase 9B.5;
  no user credential or paid request was made here.
