# OME-777 — Implementation plan

Derived from `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`. One SDLC iteration per unit;
each leaves the branch green and shippable. Delivered on one branch, one PR (owner election).

## Provisional decisions

Recorded on `OME-779` as a STOP comment; both are reversible and neither is mine to settle.

| Open item | Provisional choice | Rationale |
|---|---|---|
| Usage replay on hits | **Leave behaviour unchanged**, document it | Minimal change; inventing money-reporting semantics is out of my remit |
| TTL default | Configurable policy; **900s for search-backed entries**, `None` (never expires) for everything else | Only newly-cacheable traffic gets new behaviour; existing entries keep today's semantics |

## Process blocker

`tortoise-dev` is a `mandatory: true` companion for Tortoise work and is **not installed**. It gates
`OME-779` (writing `expires_at`, possible migration) and `OME-783`. Propose:
https://github.com/sergio-bershadsky/ai/tree/main/plugins/tortoise-dev

`OME-778` is unit-level against abstract interfaces (no DB) and proceeds without it.

## Unit order

Dependency-driven, matching the blocked-by graph in Linear.

```
OME-778 ──▶ OME-779 ──┬──▶ OME-780
                      ├──▶ OME-781
                      └──▶ OME-782
OME-783 (independent)
```

### OME-778 — characterization safety net

**Scope discipline:** ~20 cache test files already exist. This unit adds only *genuine gaps* against
the spec §5.1 list; anything already pinned is cited in the ledger, not rewritten. Duplicating an
existing assertion is a defect in this unit, not thoroughness.

- RED: gap tests only, unit-level, reusing existing fixtures.
- Files: new `tests/unit/` module(s) named for the invariant pinned.
- Acceptance: green on unmodified `main` behaviour; zero production changes; each test docstring
  names the risk it guards.

### OME-779 — Age, max-age, TTL

- Companion: `tortoise-dev` (blocked).
- RED: `Age` present/correct on hit and absent on miss; `max-age: 0` never serves; entry past
  `expires_at` not served; unknown cache-control field still bypasses (unchanged).
- GREEN: extend `core/request_cache/global_controls.py` grammar; compute `Age` from `created_at` in
  `routes/chat_cache_stage.py`; TTL policy applied on write.
- S1: confirm whether a migration is required — the column exists, so likely none. Declare either way
  in the ledger Outcome.

### OME-780 — url4-cloud consumes Age

- RED: in-bound `Age` → no re-issue; out-of-bound → re-issue; **no `Age` → re-issue** (version skew,
  first-class case).
- GREEN: parse into existing `age_s` in `runner/cache_readback.py`; send `max-age`; relax
  `requires_revalidation` only for the proven case.

### OME-781 — Path B

- RED: projection ≡ dispatch property test; deployment independence (inverting the obsolete
  smuggle test); domain variance → same key; different sets → different keys; `web_search: false`
  ≡ omitted; `08b` rows not served under `08c`.
- GREEN, in order: extract `build_web_search_plugin(body)` → point `apply_web_search` at it →
  point the projection at it → swap both rules to `provider_native_rule` → delete the setting and
  env var → bump revision.
- The deletion goes **last**, so each preceding step is independently green.
- Prior-test handling: the ~23 existing assertions that pin bypass semantics must be *inverted, not
  weakened*. Rule 5 makes this a Confidence-Gate item — the obsolete
  `test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key` is replaced by its inverse, and
  that replacement is called out explicitly for review rather than done quietly.

### OME-782 — Path A

- RED: identical tool-bearing request hits on replay; `metadata` still bypasses; `tools` reordered →
  **different** key (deliberate, commented); `tool_choice` object and string forms; empty `tools: []`.
- GREEN: drop the two entries from `PRESENCE_BYPASS_REASONS`; `bypass` → `keyed` in
  `function_calling_rules`; bump the parameter-contract revision.
- Widest blast radius — cross-provider regression pass required before commit.

### OME-783 — Tavily retrieval cache

- Companion: `tortoise-dev` if persisted; in-process TTL cache avoids it. Decide at DESIGN.
- RED: repeat query within TTL → no Tavily call; differing exclusions → separate entries; expiry →
  refetch; **exclusion re-enforcement still runs on a hit**.
- GREEN: cache wrapper around the Tavily calls in `runner/`, keyed on normalized `(query, exclusions)`.

## Commit convention

Conventional commits, body carries `Refs: OME-<n>` for the unit's own sub-issue. Never
`Co-Authored-By`. Never commit to `main`.

## Gates

`uv run .claude/scripts/run_gates.py aigateway` and `… url4-cloud` from the repo root — all green
before each commit, per rule 7. Coverage floors: aigateway 80, url4-cloud 80.
