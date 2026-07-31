---
title: SF Engine requirements for the ScreamingFace Python Client v1
ticket: OME-605
status: approved
date: 2026-07-26
approved: 2026-07-26
---

# SF Engine requirements for the ScreamingFace Python Client v1

## Purpose

This document is the deterministic boundary between the `screamingface` Python Client and the SF
Engine. It prevents the Client from filling unresolved Engine contracts with fixtures, legacy
behavior, or guessed routes.

Each requirement has one of three states:

- **confirmed** — published by the current `url4-cloud` OpenAPI, AsyncAPI, and protocol;
- **provisional** — enough is published for isolated Client work, but a production detail remains;
- **blocked** — the Engine owner must publish a contract before the production adapter ships.

Pure Client domain values may exercise blocked future shapes, but blocked adapters, compilers, and
decoders are not implemented from fixtures or presented as working production behavior.

## Ordered capability requirements

These are the Engine or URL4 contracts that must be resolved before the Client's target
`plan → run` workflow can operate in production. We review and close them in this order.

### Capability Requirement 1 — Benchmark manifest resolution

**Status:** blocked

Given a stable public Benchmark name such as `draco`, the Client needs an authoritative,
versioned Engine response that identifies the immutable Benchmark revision and everything required
to compile its Evaluation:

- case source and stable case count;
- prompts and permitted Tools;
- grading protocol and judge configuration;
- aggregation route and primary metric;
- execution policy relevant to compilation, including scientific-repetition and
  protocol-repair semantics; and
- the information needed to construct a complete Candidate → grade → aggregate URL4.

The missing decision is the Engine route and versioned schema for this response, including whether
it provides a descriptive manifest, a URL4 graph template, or both, and what immutability guarantee
pins an identity such as `draco@1`.

The Client must not hardcode a second DRACO definition or compile from a stale local fixture.
Until this contract is published, `plan(candidates, benchmark="draco")` fails with a typed
`PlanningError` before paid work.

Recipe authoring describes graph structure. Generic Fusion member settlement and degraded
reduction are Recipe execution semantics and do not belong in a Benchmark Manifest. The manifest
owns only Benchmark-specific scientific repetitions, protocol repair, grading, and aggregation.

**Owner question:** What versioned Engine contract resolves a Benchmark name into its immutable
cases, grading, Tools, aggregation, scientific-repetition, protocol-repair, and URL4 compilation
information?

The Client-side proposal for review is
[`2026-07-26-OME-605-benchmark-manifest-proposal.md`](2026-07-26-OME-605-benchmark-manifest-proposal.md).
It remains non-normative until the Engine owner confirms the route, schema, compilation ABI, and
canonical DRACO revision.

### Capability Requirement 2 — Engine capability profile

**Status:** blocked

A Plan may be inspected, shared, and executed through a different Client or Engine
after it is created. Before opening any paid Candidate Runs, the Client needs to verify that the
destination Engine supports the Plan's pinned contracts:

- URL4 and ScreamingFace protocol versions;
- Benchmark revision and referenced routes;
- model controls and required Tool capabilities;
- grader, Reducer, and Aggregator routes;
- generic Fusion member-outcome semantics; and
- the Candidate-result schema.

The recommended shape is a read-only, versioned Engine profile, for example
`GET /.well-known/screamingface`, with an immutable compatibility identifier. Planning pins the
profile against which it compiled; `run(plan)` checks the destination profile and fails before paid
work when incompatible. The Client must not wait for model execution to discover this mismatch.

**Owner question:** What endpoint and versioned schema advertises an Engine's URL4, Benchmark,
route, model-control, Tool, and result-contract compatibility?

### Capability Requirement 3 — Candidate-result schema

**Status:** blocked

Each `Candidate.url4` produces one root result. The Client needs a strict, versioned JSON
schema from which it can assemble one `CandidateResult`.

Field ownership is:

- the result body supplies pinned Benchmark provenance, selected/succeeded/failed Case counts,
  metrics, direct-member Failure summaries, and typed domain Failures;
- the Candidate Run's lifecycle Events supply `run_id`, authoritative timestamps, termination, and
  observed root usage;
- the inspected `Candidate` supplies the exact URL4, name, kind, model routes, and immutable
  Operation projection after verification against the root `Started` Event; and
- the Client validates and combines these sources but never calculates scores, grading, or
  aggregation.

A model, grading, or aggregation failure should normally still return a valid Candidate Result
with typed Failure evidence. V1 may publish aggregate metrics only when all selected Cases have
successful Case Grades. After the responsible operational layer exhausts its bounded attempt
policy, any failed Case leaves that Candidate unscored while independently scheduled Candidates
continue. A malformed, missing, or contradictory root result is a Client exception rather than a
fabricated Candidate Result.

A legitimate incorrect, refused, empty, or unparsable Candidate output may still receive a
zero-valued Case Grade when the pinned Benchmark grading protocol says so. Provider, Tool,
Synthesis, Judge, and sandbox-infrastructure failures are operational Failures and must never be
silently converted into benchmark zeroes. A degraded Fusion may still succeed when its generic
member-settlement invariant produces a valid synthesized answer; the direct-member Failure
remains observable.

The result does not duplicate the Manifest's primary metric as a generic `score` field. The
Client's `CandidateResult.score` property reads the pinned primary metric from `metrics`; this is a
convenience view, not Client-side grading or aggregation.

Proposed minimum shape:

```json
{
  "schema": "screamingface.candidate-result.v1",
  "benchmark": {
    "id": "draco@1"
  },
  "case_counts": {
    "selected": 5,
    "succeeded": 5,
    "failed": 0
  },
  "metrics": {
    "normalized_score": 0.66,
    "coverage": 1.0
  },
  "members": [
    {
      "operation_id": "op_01K_opus",
      "failures": []
    },
    {
      "operation_id": "op_01K_gpt",
      "failures": []
    }
  ],
  "failures": []
}
```

`members` is empty for a Model and contains every direct Fusion member exactly once in declared
order. Its opaque stable `operation_id` joins the result body to the inspected Candidate and
runtime Events. The Client copies the complete validated Operation projection from that Candidate
into the final portable `CandidateResult`; the Engine result body does not duplicate it.

**Owner question:** What versioned JSON schema does one completed Candidate URL4 return, and which
fields come from its result body versus lifecycle Events?

### Capability Requirement 4 — Candidate scheduling and cache reuse

**Status:** blocked

A Plan contains separate Candidate URL4s. The product backlog confirms the desired
outcome that rerunning an identical Recipe on the same Benchmark slice can be served from cache at
zero provider cost, and that cache hits and savings appear in persisted run accounting:

- [OME-305](https://linear.app/openmined/issue/OME-305/ome-305-propose-caching-model-and-double-check-with-the)
  assigns the still-unresolved fingerprinted caching model to the URL4 Engine;
- [OME-304](https://linear.app/openmined/issue/OME-304/ome-304-cumulative-cost-surfaced-to-the-user-includes-the-cache-hits)
  and
  [OME-306](https://linear.app/openmined/issue/OME-306/ome-306-cache-hit-accounting-in-run-cost-saved-with-the-run)
  require cache-hit and saved-cost accounting;
- [OME-344](https://linear.app/openmined/issue/OME-344/ome-344-local-completion-caching-current-component)
  records the existing AI Gateway completion cache as a separate, incomplete component; and
- [OME-311](https://linear.app/openmined/issue/OME-311/ome-311-broadcast-cached-sessions-from-openmined-gateway-to-local)
  leaves Gateway cache propagation as future work.

Current implementation evidence establishes only the following:

- URL4 bindings and DAG-node memoization are local to one compiled expression Run. Separate flat
  Candidate expressions do not share logical node identity.
- AI Gateway has an opt-in persistent response cache, disabled by default. Its current key is
  account/profile/provider/model plus canonical prompt content; it has no Evaluation, Candidate,
  Recipe, or URL4-node identity.
- The current Gateway cache bypasses streaming and requests with output-affecting controls, and it
  does not coalesce simultaneous cache misses.

The following are therefore **open contract decisions**, not confirmed Client requirements:

- whether separate Candidate Runs share an explicit Evaluation/cache scope;
- whether reuse is identified by Client logical-work identity, a complete request fingerprint,
  URL4-level metadata, or another mechanism;
- how deliberately independent equal-looking operations opt out of reuse;
- whether scheduling waves, Engine coordination, Gateway single-flight, or a combination prevents
  duplicate provider calls;
- whether failures are cached;
- which layer physically stores cached responses;
- how cache provenance is represented in Events and Candidate results; and
- how the Client discovers that the required behavior is supported before paid work.

The current recommendation is layered, but remains unconfirmed: URL4 core stays neutral; the SF
Engine owns Evaluation semantics, scheduling, independence, and provenance; AI Gateway may own
encrypted completion persistence and provider-dispatch single-flight. The Client must not call AI
Gateway directly or invent a production encoding before these owners publish the contract.

See
[`docs/research/2026-07-26-url4-cross-expression-identity.md`](../research/2026-07-26-url4-cross-expression-identity.md)
and
[`docs/research/2026-07-26-aigateway-request-caching-ownership.md`](../research/2026-07-26-aigateway-request-caching-ownership.md)
for the source review.

**Owner question:** What is the authoritative cache identity, scope, independence, scheduling,
storage, provenance, and capability-discovery contract for separate Candidate URL4 Runs?

### Capability Requirement 5 — Run continuity and reconnect

**Status:** blocked

A Candidate Run may outlive one WebSocket connection. A transient network failure must not lose
its progress or cause the Client to start a second paid Run.

The current `url4-cloud` lifecycle already provides:

- monotonically increasing Event sequence numbers;
- `ai.url4.attach` with `from_sequence` for replaying a gap; and
- heartbeat and terminal Events on the Run stream.

Those mechanics are insufficient until the Engine publishes:

- how the Client obtains fresh authorization for the same existing Run after its original
  capability expires;
- how long nonterminal Events and terminal results remain replayable;
- the authoritative or advertised heartbeat interval and silence threshold;
- whether the server closes the WebSocket after terminal state or expects the Client to close it;
- how an unavailable replay gap is reported;
- reconnect backoff and any maximum reconnect window; and
- when recovery becomes a terminal `ExecutionError`.

The recommended Client behavior, pending that contract, is to retain the last contiguous sequence,
reconnect to the same Engine Run, and attach from the next sequence. It must never mint an
unrelated topic or submit the Candidate URL4 again as a substitute for resuming the existing Run.
Replay duplicates may be ignored only by sequence identity; gaps and contradictory Events fail
closed.

Explicit resume remains transport plumbing rather than a public Client method. `run(plan)` owns
recovery internally and continues delivering one ordered Event stream to `on_event`.

**Owner question:** How does a Client reauthorize and reattach to the same existing Run, and what
retention, heartbeat, terminal-close, replay-gap, and reconnect-backoff policies govern that
recovery?

### Capability Requirement 6 — Caller authentication and credential separation

**Status:** blocked

The Client participates in three distinct credential planes:

- a **Caller Credential** authenticates the researcher or programmatic Client to SF Engine and may
  carry identity, authorization, and compute-budget policy;
- a **Run Capability** authorizes one Engine Run or WebSocket topic and remains internal transport
  state; and
- a **Provider Credential** authorizes AI Gateway to call a model or Tool provider and is managed
  only through Engine-proxied connection contracts.

Linear confirms the product boundary:

- [OME-326](https://linear.app/openmined/issue/OME-326/ome-326-openmineds-key-issuance-for-fusion-monsters-tbd-for)
  requires an OpenMined-issued key attached to participant identity and subsidized-compute budget;
- [OME-470](https://linear.app/openmined/issue/OME-470/integrate-auth-key-for-fusion-monsters-participants-in-the-client)
  requires a Python Client authentication flow for executing against OpenMined compute and
  submitting results, but remains blocked by OME-326;
- [OME-556](https://linear.app/openmined/issue/OME-556/dedicated-capability-token-header-url4-capability-decouple-from)
  deliberately moves the per-Run token to `URL4-Capability`, leaving the primary caller-identity
  header plane independent; and
- [OME-489](https://linear.app/openmined/issue/OME-489/implement-full-auth-so-that-non-fusion-monsters-can-submit-their)
  leaves broader public authentication as future work.

The AI Gateway proposals in
[OME-588](https://linear.app/openmined/issue/OME-588/cloudflare-access-federated-authentication-for-aigateway)
and
[OME-592](https://linear.app/openmined/issue/OME-592/add-gateway-issued-api-keys-for-programmatic-clients)
describe Cloudflare Access plus Gateway-issued `aigw_*` programmatic keys. They are still in
Triage and target direct AI Gateway identity resolution, not the unpublished SF Engine proxy
contract. The SF Client must not adopt those headers or call AI Gateway directly by inference.

The Engine must still publish:

- the Caller Credential format, issuance, revocation, expiry, and refresh contract;
- the SF Engine header or transport mechanism carrying it;
- whether a separate username remains necessary;
- its identity, account, organization, scope, and compute-budget semantics;
- which discovery and execution routes require it;
- the typed authentication and authorization error contract;
- whether Cloudflare-specific credentials are visible to the Client or terminated before SF
  Engine; and
- local Engine behavior, including whether trusted local execution may be anonymous.

The recommended public shape remains an optional `api_key` Client configuration value with
environment-variable support, but that name and wire mapping are provisional. A local and hosted
Client should expose the same domain API; only connection and authentication configuration should
differ.

The Client never exposes a Run Capability publicly, forwards a Caller Credential as a Provider
Credential, or persists provider secrets outside the published Engine connection contract.

**Owner question:** What Caller Credential does SF Engine accept, how does it map to identity and
budget, and what hosted, Cloudflare, and trusted-local authentication behavior must the Client
implement?

### Capability Requirement 7 — Authoritative discovery surfaces

**Status:** blocked

The Engine capability profile, changing catalogues, and complete reproducible definitions are
different resources:

- a **Capability Profile** describes the Engine protocol versions, schemas, features, and
  compatibility guarantees;
- a **Catalogue** lists the Models, Providers, and Benchmarks currently available to this caller;
- a **Model Contract** describes one Model's account/profile-specific parameters, Tools, and
  transport support; and
- a **Benchmark Manifest** is the pinned, immutable definition required to compile and reproduce
  an Evaluation.

The capability profile may link to the discovery resources, but it cannot replace them. Inventory
can vary by caller, provider connection, profile, and deployment without changing the Engine
protocol itself.

Linear confirms the intended Model-discovery boundary:

- [OME-490](https://linear.app/openmined/issue/OME-490/list-all-models-offered-by-a-provider)
  requires the Client/App to obtain connected-provider Models through the URL4/SF Engine;
- [OME-492](https://linear.app/openmined/issue/OME-492/ai-gateway-can-list-all-models-offered-through-an-api)
  and
  [OME-491](https://linear.app/openmined/issue/OME-491/url4-sdk-and-engine-can-proxy-the-listing-of-models-to-the-ai-gateway)
  mark the AI Gateway catalogue and Engine proxy portions as done; and
- [OME-478](https://linear.app/openmined/issue/OME-478/the-url4-engine-and-ai-gateway-should-expose-all-the-params-offered-by)
  requires provider-supported Model controls to reach the Client, but its Engine and Client
  exposure work remains blocked.

Provider/auth discovery follows the same intended proxy chain in
[OME-496](https://linear.app/openmined/issue/OME-496/model-providers-list-the-auth-methods-supported),
but its Gateway and Engine implementation chain is incomplete.

Linear does not currently publish:

- a ScreamingFace `/.well-known` route or Capability Profile schema;
- final SF Engine routes or schemas for Model, Model Contract, Provider, or Benchmark discovery;
- an authoritative Benchmark catalogue or immutable manifest resolution contract;
- catalogue pagination, revision, caching, authorization, or degraded-discovery behavior; or
- a settled ownership rule for all Benchmark grading. In particular,
  [OME-493](https://linear.app/openmined/issue/OME-493/scoring-function-can-be-provided-by-the-end-user-since-it-is-benchmark)
  still proposes Client/App-provided scoring for custom Benchmarks.

The Client therefore obtains all authoritative discovery through SF Engine and never calls AI
Gateway directly, but it must not invent the missing SF Engine routes. Planning by Model or
Benchmark name remains unavailable until the destination Engine publishes these contracts.

See
[`docs/research/2026-07-26-linear-engine-discovery-contract.md`](../research/2026-07-26-linear-engine-discovery-contract.md)
for the Linear evidence.

**Owner question:** What separate versioned Engine contracts expose its Capability Profile,
caller-specific catalogues, per-Model contracts, and pinned Benchmark manifests, and which
Benchmark grading responsibilities are Engine-owned?

### Capability Requirement 8 — Stable operation and Event attribution

**Status:** blocked

The published `url4-cloud` lifecycle identifies a Run, orders and deduplicates its Events, and
can carry a runtime trace tree. It does not currently identify which stable operation in an
inspected Candidate graph produced an Event.

The current and proposed runtime identifiers have different purposes:

- a W3C `trace_id` and `span_id` identify one runtime occurrence and its causal parent; and
- a stable **operation ID** must connect that occurrence to the compiled graph and its
  ScreamingFace meaning.

`run_id` identifies the Candidate execution lifecycle and remains conceptually distinct from W3C
`trace_id`, even if a particular transport currently derives both from one topic. A CloudEvent
`id` identifies one message, while `sequence` identifies its replay position. None is an
operation identity.

Random runtime spans cannot serve as stable operation IDs. Model names, URL text, Event order,
and implementation node kinds are also unsafe attribution keys: names and expressions may repeat,
equal-looking Recipes may be deliberately independent, execution is concurrent, and iteration,
Tools, and operational attempts create dynamic occurrences.

The URL4 observation seam under
[OME-446](https://linear.app/openmined/issue/OME-446/url4-sdk-execution-observability-node-level-stop-traceparent-streaming)
and the real-executor integration under
[OME-587](https://linear.app/openmined/issue/OME-587/url4-cloud-run-the-real-url4-engine-replace-mockexecutor-distro-split)
now provide real URL4 node spans and parent relationships in local and hosted execution. They do
not define stable compiled-operation identity or ScreamingFace semantic roles, and the published
wire contract still does not provide the complete operation-to-runtime mapping required here.

[OME-558](https://linear.app/openmined/issue/OME-558/source-lifecycle-events) explicitly describes
the current wire as lacking a source lifecycle: per-node work appears only as telemetry spans.
[OME-314](https://linear.app/openmined/issue/OME-314/ome-314-live-progress-from-real-completions)
requires real per-question and per-model progress, while
[OME-303](https://linear.app/openmined/issue/OME-303/ome-303-per-call-usage-accounting-latency-tokens-cost)
requires per-call and per-model accounting. None publishes the identifiers needed to implement
those Client experiences deterministically.

For every flat Candidate Run, the Engine must provide a versioned operation mapping that:

- parses and compiles the Client-constructed Candidate URL4 without executing paid work;
- returns its canonical URL4 and assigns stable identities to the statically executable Operations
  in the actual compiled DAG;
- exposes each Operation's ordered dependencies from that compiled DAG rather than requiring the
  Client to reconstruct them;
- gives each Operation a ScreamingFace semantic kind and human-readable label;
- maps every runtime source/span to its stable operation;
- classifies Candidate generation, direct members, synthesis, grading, aggregation, explicit Tool,
  and data Operations;
- represents dynamic Cases, criteria, judge passes, model-selected Tool calls, Tool rounds, and
  operational attempts as runtime occurrences with explicit coordinates rather than pre-expanding
  them into static Operations or relying on arrival order;
- preserves deliberately independent equal-looking operations as distinct; and
- correlates Logs and `CostUsage{self}` with the same operation and runtime occurrence.

The Engine/URL4 inspection boundary assigns the IDs; the Client only preserves them in
`Operation` values and joins them to Events/results. IDs should be deterministic for the
same canonical compiled graph where possible, while deliberately independent equal-looking
Operations must remain distinct. The mapping may be a separate operation table plus compact IDs
on Events; it need not duplicate all semantic coordinates onto every CloudEvent. URL4 core should
remain domain-neutral. SF Engine owns the ScreamingFace operation map, while `url4-cloud`
transports the opaque identity and runtime telemetry without losing correlation.

See
[`docs/research/2026-07-26-event-attribution-contract.md`](../research/2026-07-26-event-attribution-contract.md)
and
[`docs/research/2026-07-26-operation-identity-terminology.md`](../research/2026-07-26-operation-identity-terminology.md)
for the source review.

**Owner question:** What versioned no-spend SF Engine/URL4 inspection contract returns canonical
URL4 plus the compiled Operation DAG and maps its stable IDs to runtime `source`/span identity?
How are dynamic Cases, criteria, passes, Tool calls, and attempts carried as occurrence coordinates,
and how do Logs and cost Events retain that attribution? Will `run_id`, transport topic,
CloudEvent `subject`, and W3C `trace_id` remain distinct or be formally equated?

### Capability Requirement 9 — Provider connection management

**Status:** blocked

Provider connections are a separate SF Engine control plane, not URL4 expressions and not part of
the `url4-cloud` Run lifecycle. Their intended ownership is:

```text
Python Client -> SF Engine -> AI Gateway -> Provider
```

Current AI Gateway `origin/main` already owns most Provider-facing behavior:

- caller-account-scoped OAuth and API-key connection records;
- API-key validation against the Provider before create or replacement;
- provider-neutral actionable validation states;
- OAuth start, completion, refresh, and connection status;
- encrypted Provider Credential persistence; and
- credential deletion and connection revocation.

This implementation does not itself define a Client contract. AI Gateway exposes two overlapping
profile/connection APIs, has no implemented Provider/auth-method catalogue, and its native
connection response includes internal `account_id` and `credential_locator` fields. A backend-only
route can also return a live OAuth access token. The SF Client must never call these routes
directly, and SF Engine must not proxy their wire shapes unchanged.

SF Engine must publish one sanitized, versioned, caller-scoped Provider Connection contract that:

- discovers stable Provider identities, display names, and available authentication methods;
- lists current public connection state;
- creates or replaces an API-key connection in one validation-before-persistence operation;
- optionally validates an API key without persisting it when explicitly requested;
- begins OAuth and returns only the authorization URL, public flow identity, and bounded expiry;
- exposes bounded OAuth completion/status without exposing PKCE, tokens, or Gateway state;
- disconnects a connection and removes or revokes its managed Provider Credential;
- returns safe typed retryability and actionable errors; and
- never returns stored API keys, access/refresh tokens, Gateway account IDs, credential locators,
  raw Provider errors, or secret-bearing logs.

The Client must not automatically call the optional validation action before create/replace:
AI Gateway already validates the mutation, and its minimal readiness probe may consume Provider
quota or credit.

The Engine contract must still decide:

- whether v1 manages exactly one connection per Provider or permits several named connections;
- how a Caller Credential maps to an AI Gateway Account in local and hosted deployments;
- how local and hosted OAuth redirects/callbacks complete safely;
- whether pending OAuth state survives process or deployment changes;
- polling cadence, expiry, retry, replacement, and idempotent disconnect semantics;
- whether Engine-owned Tool credentials share this public catalogue; and
- the exact public state and error redaction allowlists.

Linear assigns Provider/auth-method discovery to AI Gateway in
[OME-497](https://linear.app/openmined/issue/OME-497/ai-gateway-can-return-model-providers-list-auth-methods-supported-by)
and Engine facilitation to
[OME-498](https://linear.app/openmined/issue/OME-498/url4-engine-is-able-to-facilitate-the-providersauth-list-via-the-url4);
both remain incomplete. The existing API-key validation behavior is specified by
[OME-307](https://linear.app/openmined/issue/OME-307/ome-307-api-key-validation-with-actionable-states).

See
[`docs/research/2026-07-26-provider-connection-management.md`](../research/2026-07-26-provider-connection-management.md)
for the source review.

**Owner question:** Can SF Engine publish one sanitized, account-scoped Provider Connection
contract covering Provider/auth discovery, connection list/status, validated API-key
create-or-replace, OAuth start/completion, and disconnect? For v1, is there exactly one managed
connection per Provider, and how does SF caller identity map to the AI Gateway Account locally and
when hosted?

### Capability Requirement 10 — Retry ownership and attempt safety

**Status:** blocked

The stack already contains more than one mechanism called retry:

- AI Gateway retries proven Provider overloads with bounded backoff, jitter, total-wait limits,
  and `Retry-After`;
- URL4 `GuardNode` can retry a transient source through the explicit `;retry=N` annotation;
- Benchmark graders may deliberately re-ask invalid structured outputs; and
- the Client must reconnect and replay the same Run after transport loss.

These mechanisms are not interchangeable. A Benchmark pass or answer sample is an independent
scientific observation. A grading repair is pinned protocol behavior. An operational attempt
recovers one logical operation. A WebSocket reconnect only resumes observation of the same Run.

The Client exposes no generic retry count and never automatically starts a replacement paid Run.
The Engine must not wrap AI Gateway-backed model routes in a second default URL4 retry loop:
layered retry budgets multiply Provider calls, and ambiguous responses may already have been
billed. Any Engine-level retry around a billable operation requires a published idempotency,
request-deduplication, or proven-before-dispatch-failure guarantee.

The production contract must:

- identify one authoritative operational retry owner for each Provider, Tool, and data boundary;
- publish a shared retryability classification and safe `Retry-After` behavior;
- keep Benchmark passes, samples, and typed grading repair separate from infrastructure attempts;
- preserve one logical operation ID while giving every runtime attempt a distinct occurrence;
- attribute usage and cost from failed as well as successful attempts;
- expose exhausted failures through the typed Failure contract; and
- guarantee that reconnect/replay preserves the existing `run_id` without resubmission.

AI Gateway's Provider retry behavior is implemented, but the full cross-layer classification,
idempotency, Engine Tool policy, and attempt telemetry are not yet a published SF Engine
capability. URL4 source-retry lifecycle Events and richer error classification are separately
tracked by
[OME-558](https://linear.app/openmined/issue/OME-558/source-lifecycle-events) and
[OME-563](https://linear.app/openmined/issue/OME-563/align-error-classification-errorinfo-transientpermanent-http-map).

See
[`docs/research/2026-07-26-retry-ownership.md`](../research/2026-07-26-retry-ownership.md)
for the source review.

**Owner question:** Which layer owns each operational attempt, how are layered retries prevented
for billable calls, and what versioned classification, idempotency, and attempt-attribution
contract does SF Engine publish?

### Capability Requirement 11 — Fusion member settlement and degraded reduction

**Status:** blocked

Within each independently runnable Candidate URL4, the Engine must implement one generic Fusion
invariant:

- settle every declared member independently and retain it in declared order;
- pass only successful member outputs to the Reducer, preserving relative order and member
  identity;
- preserve each failed member as a typed outcome rather than empty text or error prose;
- attempt reduction when at least one member succeeds;
- fail the Fusion only when no member succeeds or the Reducer fails; and
- apply the same rule recursively to nested Fusions.

This is not multi-root execution across Candidates. Each Candidate remains one flat-root URL4 Run;
the requirement concerns member operations inside that one Candidate expression. The Client
exposes no strict/lenient policy knob, and Benchmark Manifests cannot override the invariant.

The result and Event contracts must preserve failed-member evidence, operation identity, usage,
and cost even when the Fusion produces a valid answer and receives a score. In that case the
Candidate can be scored while `report.ok` remains false.

**Owner question:** What generic SF Engine/URL4 construct provides ordered settled member outcomes
and successful-only Reducer input inside one Candidate expression, and what capability identifier
advertises those semantics?

## Requirement matrix

| Requirement | Client need | Status | Missing Engine decision |
|---|---|---|---|
| New-Run execution capability | Open a Run-scoped REST/WebSocket lifecycle without exposing its token publicly | confirmed | None for a new Run |
| WebSocket attach | Subscribe before start and replay from a monotonic sequence | confirmed | Initial attach uses no cursor; replay supplies `from_sequence` |
| Asynchronous start | Submit one URL4 expression and receive `202` while Events stream | confirmed | None for the current `url4-cloud` contract |
| CloudEvents lifecycle | Decode ordered started/log/span/usage/heartbeat/result/terminated/error Events | confirmed | None for the current event envelopes |
| Best-effort stop | Cancel invisible paid work after callback failure or interruption | confirmed | Use `ai.url4.stop` on the attached socket |
| Run continuity and reconnect | Resume the same paid Run after WebSocket loss without resubmission | blocked | Existing-Run reauthorization, retention, heartbeat/liveness, terminal close, replay-gap, and retry policy |
| Caller authentication and credential separation | Authenticate the researcher to SF Engine without confusing Caller, Run, or Provider credentials | blocked | Credential format/header, issuance/revocation/refresh, identity and budget mapping, Cloudflare boundary, errors, and trusted-local behavior |
| Authoritative discovery surfaces | Discover compatibility, inventory, Model controls, and reproducible Benchmark definitions without calling AI Gateway directly | blocked | Separate Engine routes/schemas for Capability Profile, catalogues, Model Contracts, and Benchmark Manifests; grading ownership |
| Stable operation and Event attribution | Inspect each actual Candidate URL4 DAG and map real-time progress, logs, usage, and failures onto it | blocked | No-spend canonicalization/inspection contract, stable compiled-operation IDs and dependencies, runtime span/source mapping, SF semantic roles, dynamic-occurrence coordinates, and Log/cost correlation |
| Model catalogue | Populate `models.list()` and validate portable model controls | blocked | Authoritative route and response schema |
| Benchmark catalogue | Populate `benchmarks.list()` | blocked | Authoritative route and response schema |
| Benchmark manifest | Pin revision, routes, cases, grading, aggregation, Tools, and defaults during planning | blocked | Manifest route, schema, identity, and immutability guarantees |
| Capability profile | Check a Plan against its destination before paid execution | blocked | Profile route/schema and compatibility rules |
| Provider connection management | Discover and manage Engine-proxied BYOK/OAuth connections without exposing Gateway internals or Provider Credentials | blocked | Sanitized routes/schemas, one-vs-many policy, Caller-to-Gateway account mapping, OAuth callback behavior, managed-credential semantics, and Provider/auth discovery |
| Candidate scheduling and cache reuse | Run one flat-root URL4 per Candidate under the published reuse policy | blocked | Identity, scope, independence, scheduling/coalescing, storage ownership, provenance, accounting, and capability discovery |
| Benchmark result | Strictly decode each Candidate root result and combine them into one `Report` | blocked | Final versioned Candidate-result schema and Failure/usage ownership rules; `run()` fails closed before execution while this and compatibility preflight are unavailable |
| Event attribution | Map Events to Candidate/member/grader/aggregator/Tool operations | provisional | Stable SF operation identity plus URL4 source/span mapping |
| Retry ownership and attempt safety | Recover safe transient failures without multiplying billable calls or changing Benchmark science | blocked | Cross-layer retry owner, shared classification/Retry-After, idempotency/deduplication, typed protocol repair, and attempt usage attribution |
| Fusion member settlement and degraded reduction | Reduce successful members while retaining ordered typed failures inside one Candidate URL4 | blocked | Generic Engine/URL4 construct, recursive semantics, result/Event evidence, and capability identifier |
| Real lifecycle integration target | Verify the adapter against real URL4 execution, not only a controlled server | confirmed | OME-587 provides the real executor and the same protocol through in-process local mode or hosted NATS/workers |

## Production DRACO conformance gate

Implementing the contracts above makes full DRACO executable; it does not by itself prove that an
implementation reproduces a particular DRACO protocol. A production claim must name and pin its
reference target. The current `screamingface-benchmarks` notebook smoke configuration, its full
repository configuration, the DRACO paper protocol, and the OpenRouter article are not identical:
they differ in case limits, judge passes or exact Judge availability, and published Tool details.

Before the SDK or Engine claims production DRACO reproduction, one controlled conformance fixture
must verify that the pinned manifest and complete 7-solo/9-Fusion Candidate set produce the
reference operation ledger and outputs for:

- the stable full case set and exact answer and Synthesis prompts;
- Model routes, generation controls, and output budgets;
- answer-only Tool policy, limits, and credential preflight;
- tool-free Synthesis and judging;
- deterministic panel-answer reuse plus independent sampled self-Fusion members;
- generic Fusion member-settlement and degraded-reduction conformance;
- Benchmark-owned scientific-repetition and protocol-repair policy;
- one official judge request per criterion for every pinned independent pass;
- exact Judge prompt, controls, structured-output validation, and missing-verdict behavior;
- weighted score, pass-rate, axis, coverage, and cross-case aggregation formulas;
- typed partial failures, usage, cache provenance, and declared Candidate ordering; and
- one complete versioned Candidate result per independently runnable Candidate URL4.

This gate has two levels:

1. a deterministic no-spend conformance suite using controlled Model, Tool, and Judge responses;
2. an explicitly approved live acceptance run against the pinned Models, Tool services, and full
   case set.

The live run is not ordinary CI and must remain budget-gated. A substituted Judge, inferred private
Tool setting, disabled required Tool, reduced case set, or reduced judge-pass count must appear in
the Benchmark identity and Report provenance; such a run cannot be labelled paper-exact.

## Confirmed new-Run lifecycle

The Client-visible lifecycle is:

```text
POST /token
  -> open /ws?ticket=<capability> with cloudevents.json
  -> send ai.url4.attach with from_sequence omitted/null
  -> GET /?q=<url4> with URL4-Capability and Prefer: respond-async
  -> consume ordered CloudEvents
  -> receive exactly one root result followed by terminal state
  -> close the WebSocket
```

The route spellings above describe the current `url4-cloud` contract adapter. They are isolated
behind the Client's Engine transport port and are not embedded in domain objects.

This lifecycle executes one `Candidate.url4`. A multi-Candidate `Plan` creates one
such Engine Run per Candidate; there is no shared multi-root Run. The Client retains declared order
when it combines the independently scored Candidate results into one Report.

The adapter is tested independently while the production planning, compatibility-preflight, and
result contracts remain blocked. Public `run(plan)` does not open this lifecycle until it can both
verify the destination before paid work and return a strictly decoded Report.

`URL4-Capability` is a short-lived per-Run capability, not the researcher's hosted API key and not
a provider credential. The Client owns it internally.

## Contract-test rule

The confirmed transport adapter is verified at two levels:

1. deterministic adapter tests against a controlled protocol server, while public `run()` tests
   verify that blocked preflight fails before network or paid work; and
2. an opt-in integration run against an OME-587 real-runner target.

Tests do not monkeypatch private Client or transport functions. Once the preflight and result
contracts are published, the same lifecycle scenarios move through the public Client interface. A
blocked contract remains a named skipped integration requirement in
`tests/test_external_contract_requirements.py` rather than a fake production implementation.

`tests/test_url4_cloud_integration.py` is an opt-in adapter check for a runner-backed target. Set
`SCREAMINGFACE_URL4_CLOUD_INTEGRATION_URL` when that target is available and optionally set
`SCREAMINGFACE_URL4_CLOUD_INTEGRATION_URL4` to a target-specific no-spend expression. OME-587
provides a real in-process local runner and a hosted runner adapter; the test verifies the same
Client-visible lifecycle in either mode.

## Deferred Linear follow-up inventory

No Linear issue is changed by this Client implementation. Before implementation owners close the
remaining external contracts, review the following existing issues against the requirements above:

- cache identity, provenance, and accounting: OME-305, OME-304, OME-306, OME-344, and OME-311;
- Fusion settlement and DRACO execution semantics: OME-427;
- reconnect/replay transport: OME-521, with a still-missing existing-Run reauthorization contract;
- retry and failure taxonomy: OME-563 and OME-298;
- caller authentication: OME-326, OME-470, OME-588, and OME-592;
- Model discovery: OME-490, OME-491, and OME-492;
- Provider/auth discovery and connections: OME-496, OME-497, and OME-498; and
- real URL4 execution and local/hosted parity: OME-587.

Likely new owner contracts, rather than updates guessed inside the Client, are:

1. Benchmark Manifest resolution, compatibility preflight, and no-spend Candidate inspection;
2. the versioned Candidate-result schema and stable Operation/Event attribution;
3. existing-Run reauthorization plus heartbeat, replay-retention, and terminal-close policy; and
4. cross-layer retry ownership and billable-call idempotency.

Provider-connection management and catalogue listing are follow-up Client features. They are not
release blockers for the minimal approved `plan → run` workflow once known Models and Benchmarks
can be planned through authoritative Engine contracts.
