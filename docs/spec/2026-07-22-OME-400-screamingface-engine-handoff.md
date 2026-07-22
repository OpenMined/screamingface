---
title: ScreamingFace engine reference handoff
ticket: OME-400
status: implemented-reference
date: 2026-07-22
---

# ScreamingFace engine reference handoff

This branch contains a working reference profile under
`packages/screamingface/apps/screamingface-engine`. It exists so the unreleased ScreamingFace SDK
could develop and verify its URL4 contract before the production engine and hosted runner had
owners. It is not a claim that the SDK owner should own or deploy the production engine.

## Proven end-to-end boundary

```text
ScreamingFace SDK
  -> compiles one complete URL4 benchmark expression
  -> sends only to a ScreamingFace URL4 execution surface

ScreamingFace node profile
  -> resolves model, reducer, benchmark, grader, aggregator, and tool routes
  -> sends model calls to AI Gateway
  -> sends eligible bare-model research-tool calls to Tavily
  -> returns plaintext JSON that the SDK validates
```

The reference app exposes a reusable `create_node(...) -> Url4Node` factory and a standalone HTTP
wrapper for local development. The node is created once for a worker/process and reused; it is not
a new server or node per URL4 request. `examples/05_draco_quickstart.ipynb` is the bounded live
acceptance surface: one ordered 7-solo/9-Fusion DRACO Lite study, one pinned real case, ten
criteria, and one judge pass.

## Ownership proposal

| Surface | Owner responsibility |
|---|---|
| ScreamingFace SDK | Public `Model`, `Fusion`, `Benchmark`, connection, URL4 compilation, manifest validation, report decoding, and notebooks |
| ScreamingFace node profile | Route registry, official benchmark cases/policies, graders, aggregators, AI Gateway/Tavily adapters, concurrency, and sanitized errors |
| `url4-cloud` | Jobs, tokens/session boundary, REST/WebSocket transport, CloudEvents, cancellation/resume, and the runner `Executor` adapter |
| AI Gateway | Provider credentials, model catalog, normalized model calls, usage, and provider admission control |
| `packages/url4` | Generic grammar, DAG evaluation, `Url4Node`, observation/stop hooks, and transport seams |

The engine owner can promote or reimplement the temporary app without changing the SDK contract.
The useful handoff is the tested route behavior and node factory, not the current directory.

## Hosted-runner integration

The local SDK currently uses the reference engine's direct `GET /v1?q=...` plus SSE progress
surface. The production hosted path should use the `url4-cloud` runner contract instead of copying
that private event shape:

1. `url4-cloud` owns the execution job and CloudEvents lifecycle.
2. Its real `Executor` adapter invokes a configured, reusable ScreamingFace `Url4Node` in-process,
   or an equivalently isolated worker-local node.
3. URL4 execution observations are translated by the executor/telemetry adapter into the official
   runner events.
4. The ScreamingFace SDK gains a hosted transport that submits the same URL4 and consumes those
   official events. Recipe and benchmark compilation do not change.

This keeps the node profile a capability plugin for the generic runner. It avoids an extra HTTP
hop between `url4-cloud` and a second ScreamingFace engine service while preserving the standalone
HTTP app as a local diagnostic/reference surface.

## Deliberate cleanup before ownership transfer

- Move the deployable profile to the root `apps/` tree only with its new owner and release lane.
- Remove the profile's imports of private `screamingface._...` modules by promoting the required
  contracts into an explicitly shared public/internal package boundary.
- Decide whether production DRACO receives the candidate-study route already proven by DRACO Lite.
- Replace the local in-memory Tavily credential policy with the hosted identity/secret boundary.
- Keep provider/model discovery sourced from AI Gateway rather than copying its catalog.
- Keep the SDK isolated from AI Gateway and Tavily in every deployment.

No generic URL4 or AI Gateway source changes are required by this handoff. The untracked
`apps/url4-cloud` work remains colleague-owned and is intentionally not modified by OME-400.
