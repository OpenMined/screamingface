---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Phase 4D SearXNG web research

## Intent

Make the existing benchmark-level `tools=("web_search",)` contract executable through the
temporary `screamingface-engine` profile. The engine will own a bounded model/tool loop, use a
locally hosted SearXNG service for search, safely fetch selected public pages, and continue to
send every model turn through AI Gateway. The SDK, URL4 package, and AI Gateway remain unchanged.

## Planned changes

- Add a private web-research adapter and bounded model executor under
  `packages/screamingface/apps/screamingface-engine/src/screamingface_engine/`.
- Extend the private Gateway client to preserve standard assistant tool calls and accept
  follow-up tool-result messages without changing its public HTTP boundary.
- Extend engine settings, lifecycle wiring, model parameter validation, and registry claims so
  only configured and compatible routes advertise `web_search`.
- Add a pinned internal SearXNG service and JSON-search configuration to the engine Compose stack.
- Add append-only engine tests for search normalization, safe fetching, tool execution loops,
  capability discovery, limits, failures, lifecycle cleanup, and unchanged tool-free behavior.
- Update the benchmark architecture plan, public contract, engine README, task mirror, and this
  work record with the Phase 4D boundary and verification evidence.

## Test plan

- First add failing unit tests for SearXNG result normalization, empty/malformed responses,
  URL-prefix contamination filtering, safe HTTP(S)-only fetching, private-address rejection,
  redirects, size limits, and upstream errors.
- Add failing tests for structured AI Gateway assistant turns, standard tool declarations,
  tool-result continuation, multiple calls, maximum-call enforcement, malformed calls, and final
  plaintext extraction.
- Add failing registry/application tests proving Claude and Gemini advertise `web_search` only
  when configured, Codex remains tool-free, unsupported tools fail before Gateway traffic, and
  tool-free requests remain byte-compatible.
- Run the complete ScreamingFace SDK and engine suites, Ruff format/lint, Pyright, coverage,
  fixture/notebook drift checks, package builds, lock checks, and Compose validation.

## Acceptance

- A URL4 model request carrying `tools=web_search` can complete a controlled search/fetch/model
  loop and returns only the final assistant plaintext.
- Every model turn uses the existing AI Gateway `/v1/chat/completions` endpoint; no AI Gateway or
  URL4 source file changes.
- SearXNG is internal to the local engine stack and requires no researcher API key.
- Tool execution is bounded, blocked DRACO material is never returned, and unsafe fetch targets
  fail closed.
- Registry claims remain honest: Claude and Gemini advertise the configured capability while
  Codex does not.
- All pre-existing tests remain unchanged and green, with the configured coverage threshold met.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added the engine-owned `executor.py` and `web_research.py`; extended the
  Gateway adapter, settings, catalog, composition root, and ASGI lifecycle; added the pinned
  SearXNG Compose service and configuration; added four append-only Phase 4D engine test modules;
  and updated the package/engine READMEs, architecture plan, public contract, and task mirror.
- **Commits:** pending the owner's commit after review.
- **Gates:** 72 engine tests passed at 96.72% coverage; 351 SDK tests passed at 97.09% coverage;
  Ruff lint/format, Pyright, the stack-specific gate runner, append-only test check, fixture
  construction, generated-notebook drift, both lock checks, package build, Compose validation,
  and `git diff --check` passed. The rebuilt live stack was healthy on isolated host ports;
  SearXNG returned JSON search results and the engine registry advertised `web_search` exactly on
  Gemini and Claude. The isolated verification stack was removed afterward.
- **Deviations:** one public `web_search` capability intentionally expands to the engine's private
  standard `web_search` and `web_fetch` function pair. Transient failure to read one public page
  is returned to the model as structured tool output; malformed or unsafe targets still fail
  closed. Full DRACO remains deferred to the reviewed judge route and long-expression transport
  slices; no SDK, URL4, or AI Gateway behavior was changed.
