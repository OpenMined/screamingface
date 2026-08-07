---
ticket: OME-712
stack: url4-cloud
status: completed
started: 2026-08-06
---

# OME-712 — Engine benchmark foundation

## Intent

Reconstruct the generic Engine-owned Benchmark and Candidate Invocation foundation from current
`main`, without carrying forward DRACO, IFEval, connections, deployment, SDK, AI Gateway, URL4,
or generic command/data changes.

## Artifacts

- Spec: `docs/spec/2026-08-06-OME-712-engine-benchmark-foundation.md`
- Plan: `docs/plan/2026-08-06-OME-712-engine-benchmark-foundation.md`
- Task mirror: `docs/tasks/2026-07-31-ome-712-run-draco-url4.md`

## Implemented shape

- Immutable explicit Benchmark registry; no default alias or installer deduplication.
- Structured `Node` builders and strict exact `limit` specialization.
- Metadata-complete list plus selection-complete detail resources with body-derived ETags.
- Shared-world `/benchmarks/candidate` adapter rather than a second restricted node.
- Explicit task-local retrieval ceilings with nested intersection and exclusion union.
- Search-result post-filtering and direct-fetch blocking in addition to Tavily request filters.
- Generic task-local terminal outcome recording; refusal remains provider data at the Candidate
  boundary.
- Runner composition owns Candidate/Benchmark installation and immutable asset-root injection;
  Connector owns model routes only.
- Startup validation for duplicate/missing routes and malformed full-selection protocols.
- One terminal outcome per logical model call: the Connector records when its tool loop returns
  content, not on each round trip, so a consumer can tell a call that progressed from two calls
  that disagreed. The Candidate reports an agreed outcome and reports null when branches differ.
- Retrieval exclusions fail closed on any host this comparison cannot decide, including a
  percent-encoded one.
- Install-time route validation covers relative data references and `data()` routes, not only
  `RelExpr` calls against endpoints, and treats an iteration row template as unvalidatable rather
  than as a route named `/judge` when it reads `/judge/$item`.
- The Candidate binding is published: `candidate_binding` in every detail resource, plus
  `link_candidate` as the one definition of how a client binds its Candidate to a protocol.

## Test plan

- Catalog: empty/list/detail, slash IDs, no alias, strict limits, selected count, per-entity ETags.
- Installation: every concrete definition, duplicate paths, missing literal model routes, injected
  asset root.
- Execution: fetched resource linking, same-world Benchmark routes, nested Candidate composition.
- Policy: required values, unknown values, no parent-policy escalation, capability preflight,
  concurrent task isolation.
- Retrieval: Tavily exclusions, search post-filter, blocked direct fetch.
- Outcomes: normal completion, provider refusal envelope, nested and concurrent recorder scopes.
- Full URL4 Cloud lint, format, type, layering, and coverage gates.

## Boundaries

- No scored Benchmark is installed here.
- Benchmark reducers must add exact ordered case-ID enforcement in their own PRs.
- Client selection/preflight/report changes remain in the Client PR.
- Case browsing waits for the first benchmark-owned case-source implementation.
- No deployment or authentication behavior changes.

## Verification

- Focused Benchmark foundation tests: 41 passed.
- Full URL4 Cloud suite: 961 passed, 5 skipped, 96% coverage. Counts are measured after the
  rebase onto `main`, so they include the cache-policy and connections work that landed there.
- Ruff lint/format, Pyright, and Engine/control-plane layering: passed.
- Two-axis branch review: Standards findings resolved in code; accepted spec passes with no
  missing, partial, incorrect, or out-of-scope behavior.
- Open follow-up: `Url4Node` publishes no accessor for its data routes, so the registry reads the
  table privately. An accessor belongs upstream in the URL4 engine, which is outside this
  landing's boundary.
- Open follow-up: installation does not verify that a protocol's free reference is the declared
  Candidate binding, so a misspelled `$candiate` still fails at run time rather than at install.
- Deliberate test-history exception: the inherited URL4 importer boundary test was updated because
  the accepted architecture explicitly makes `url4_cloud.benchmarks` an Engine-owned structured
  URL4 extension. No behavioral assertion was weakened; the boundary became path-specific.
