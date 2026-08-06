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

- Focused Benchmark foundation tests: 30 passed.
- Affected Connector, finish-reason, REST, and Benchmark tests: 108 passed.
- Full URL4 Cloud suite: 523 passed, 5 skipped, 95.85% coverage.
- Ruff lint/format, Pyright, and Engine/control-plane layering: passed.
- Two-axis branch review: Standards findings resolved in code; accepted spec passes with no
  missing, partial, incorrect, or out-of-scope behavior.
- Deliberate test-history exception: the inherited URL4 importer boundary test was updated because
  the accepted architecture explicitly makes `url4_cloud.benchmarks` an Engine-owned structured
  URL4 extension. No behavioral assertion was weakened; the boundary became path-specific.
