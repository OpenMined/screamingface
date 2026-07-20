---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 9B.2 engine-owned Tavily connection

## Intent

Add the researcher-owned local ScreamingFace engine's Tavily BYOK connection without routing the
credential through AI Gateway or claiming search/extract execution before it exists. The existing
generic SDK connection API and widget must discover Tavily from engine metadata, validate a key
through Tavily, expose only sanitized state, and require reconnection after an engine restart.

## Planned changes

- Record the approved local-only connection and hosted-deployment boundary in the Phase 9 contract,
  architecture plan, and temporary engine README.
- Add append-only tests for provider discovery, SDK/widget discovery, successful key validation,
  sanitized state, zero Gateway traffic, atomic replacement, disconnect/restart behavior,
  unsupported OAuth, and stable validation failures.
- Add an engine-owned Tavily connection backend with an injected asynchronous HTTP transport and
  process-memory credential lifecycle.
- Compose Gateway model-provider connections and the Tavily tool-service connection through one
  public connection manager without adding Tavily to AI Gateway.
- Add semantic comments that prevent future code from forwarding Tavily credentials to Gateway or
  mistaking the local store for a shared hosted credential system.
- Do not add search/extract execution, URL4 tool parameters, HF tool loops, credential persistence,
  a generic URL4 change, or any AI Gateway change in this unit.

## Test plan

- RED: registry and the generic SDK connection surface include API-key-only `tavily`, while model
  discovery remains unchanged.
- RED: `PUT /v1/connections/tavily/api-key` validates through `GET https://api.tavily.com/usage`,
  reports only sanitized connected state, and never contacts AI Gateway.
- RED: failed replacement retains the prior validated key; disconnect clears it; a fresh backend
  starts disconnected; OAuth fails locally.
- RED: 401/403, 429, network/5xx, and malformed success responses map to stable safe errors without
  leaking the candidate key or upstream response body.
- GREEN: run focused tests, all prior engine/SDK tests, deterministic notebook checks, and the
  authoritative ScreamingFace gate.

## Acceptance

- `sf.connect("tavily", api_key=...)`, `sf.connections.get("tavily")`, and
  `sf.disconnect("tavily")` work against the configured local engine with no SDK special case.
- A public `connected` status means the submitted key passed Tavily validation at connection time.
- The credential exists only inside the running engine process and is absent after restart.
- Tavily causes no AI Gateway traffic and no secret reaches URL4, model messages, responses, or
  logs.
- No HF model advertises Tavily tools in Phase 9B.2.
- Documentation explicitly says this local store is not suitable for unauthenticated shared
  deployment; hosted use requires HTTPS, identity, and encrypted per-user storage.

## Outcome

- **Actual files:** added the engine-owned Tavily validator and composed connection manager;
  extracted neutral connection-control errors/JSON decoding from the Gateway adapter; added
  Tavily to public provider metadata; wired lifecycle cleanup; added generic
  `sf.connections.get()`; updated the SDK/engine READMEs, Phase 9 plan/spec, task record, and
  generated service-connections notebook; and added focused SDK/engine contract tests.
- **Commits:** `feat(screamingface): add engine-owned Tavily connections` (this commit).
- **Gates:** 12 focused Tavily engine tests, one focused generic SDK/panel test, 45 complete
  connection regressions, 575 SDK tests, and 180 engine tests passed. The authoritative
  `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` gate passed Ruff
  lint/format, Pyright, both coverage suites, fixture checks, deterministic notebooks, and wheel
  build.
- **Deviations:** the append-only precheck was skipped under the owner's approved Phase 9B.2
  contract because three prior strict provider-list assertions had to gain the new Tavily record;
  their existing assertions were preserved and extended, not weakened. All notebooks were
  regenerated with owner approval after an active Jupyter session had changed kernel metadata.
  No search/extract execution, HF tool claim, Gateway change, credential persistence, or generic
  URL4 change was added.
