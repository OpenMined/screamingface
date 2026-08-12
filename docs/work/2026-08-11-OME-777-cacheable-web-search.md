---
ticket: OME-777
stack: aigateway, url4-cloud
status: in_progress
started: 2026-08-11
finished:
---

# OME-777 — Make web-search-backed requests cacheable

## Intent

Every web-search-backed request currently bypasses aigateway's shared global cache, through two
independent mechanisms and for three independent reasons. Two owner decisions taken 2026-08-11
remove two of those reasons outright: tool-bearing requests may now be cached, and the deployment
env var `AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS` is deleted, making the request body the sole
source of truth for blocked domains. The third reason — retrieval is time-varying and the cache
cannot express freshness — is not waived and is addressed first.

The unifying idea is that the second decision is a **deletion, not a feature**. The previously
scoped escape hatch (a new `deployment_request_defaults(body)` plugin port plus an
ordering-sensitive call site in `routes/chat.py`) existed only to smuggle that env var into the
request body so the key could observe it. With the variable gone, that machinery has nothing left
to carry, and the projection-purity test passes because the impure input no longer exists rather
than because we engineered around it.

Spec: `docs/spec/2026-08-11-OME-777-cacheable-web-search.md`

## Planned changes

Six units, tracked as sub-issues, delivered on one branch and one PR by owner election.

- `OME-778` — characterization tests over current cache behaviour. No production code.
- `OME-779` — `apps/aigateway`: emit `Age`; widen `core/request_cache/global_controls.py` to accept
  `max-age`; honour the bound on read; set `expires_at` via a configurable TTL policy.
- `OME-780` — `apps/url4-cloud`: parse `Age` in `runner/cache_readback.py`, send `max-age`, retire
  the defensive re-issue in `runner/connector.py` for the provable case only.
- `OME-781` — `apps/aigateway`: delete the setting in `plugins/openrouter_provider/settings.py`;
  extract `build_web_search_plugin(body)` in `web_search.py`; emit the envelope from
  `global_cache.py`; move both rules in `parameters.py` to `provider_native_rule`; bump
  `GLOBAL_CACHE_ADAPTER_REVISION` `08b` → `08c`.
- `OME-782` — `apps/aigateway`: drop `tools`/`tool_choice` from `PRESENCE_BYPASS_REASONS` in
  `core/request_cache/global_eligibility.py`; key both in `core/standard_parameters.py`; bump the
  parameter-contract revision. `metadata` untouched.
- `OME-783` — `apps/url4-cloud`: TTL'd retrieval cache around the Tavily calls in `runner/`.

## Test plan

Written RED first, per stack SDLC.

- **Projection ≡ dispatch** (property test, OME-781): the envelope in `prepared` must equal the
  `plugins` block `apply_web_search` writes. Highest-value test in the epic — it makes the
  shared-builder rule enforceable rather than merely intended.
- **Deployment independence** (OME-781): replaces the now-obsolete
  `test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key`. Two plugin instances with
  different settings must produce the *same* key for the same body — the inverse of today's
  assertion, same intent.
- Domain case/order/duplicate variance → same key; different domain sets → different keys.
- `web_search: false` ≡ field omitted → same key.
- `tools` array reordered → **different** key, asserted deliberately with the reason in a comment
  (we may not normalize what we pass through untouched).
- `metadata`-bearing requests still bypass after OME-782.
- `Age` correct on hit, absent on miss; `max-age: 0` never serves; expired row not served.
- url4-cloud: hit with in-bound `Age` → no re-issue; hit with **no** `Age` → re-issue (version-skew
  path, tested as first-class).
- Cross-provider regression for OME-782 — it touches every function-calling provider.
- `08b` rows not served under `08c`.

## Acceptance

- Search-backed requests through both mechanisms produce and serve cache entries.
- No request can be served an answer produced under a different exclusion set.
- Freshness-bounded url4-cloud runs stop paying an extra round trip for unprovable hits.
- `AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS` no longer exists anywhere in the repo.
- All stack gates green for `aigateway` and `url4-cloud`.

## Open decisions — block close of OME-779

- **Usage replay.** Cache hits return the first caller's `usage` verbatim; token counts misreport
  for every later caller. Pre-existing, but this epic raises hit rate and magnifies it. Needs the
  owner of benchmark cost accounting: leave and document, zero on hit, or annotate.
- **TTL default** for search-backed entries. Policy built configurable regardless; default unset.

## Log

- 2026-08-11 — Epic `OME-777` + sub-issues `OME-778`…`OME-783` filed; blocked-by relations set.
  Worktree `.claude/worktrees/OME-777-cacheable-web-search` branched from `origin/main`. Spec
  written. Mirrors created in `docs/tasks/`.
- 2026-08-11 — Ledger recreated after a concurrent mechanic agent deleted it while enforcing a
  file-count check. No tracked file was affected; worktree verified clean against `HEAD`.
- 2026-08-11 — `OME-779` moved to a STOP (`deferred` + comment) on two owner decisions and the
  missing `tortoise-dev` companion.

## OME-778 outcome — closed as already satisfied

**Finding: the safety net this unit was scoped to build already exists.** A coverage inventory
against the eleven characterization items in spec §5.1 found **nine already pinned** by the existing
suite (`test_global_cache_key.py`, `test_global_cache_store.py`, `test_global_cache_controls.py`,
`test_global_cache_projection_purity.py`, and others). Writing them again would be duplication, not
protection.

The two genuine gaps were both deliberately **not** filled:

- `BYPASS_MODE_RESTRICTED` has no route-level test. Real gap, but no phase in this epic touches mode
  restriction, so pinning it here is speculative coverage. **Recorded as a pre-existing finding**
  for a future unit, not built now.
- Absence of an `Age` header is unasserted. Writing that assertion would mean deleting or inverting
  it in `OME-779` one unit later — precisely what rule 5 forbids. `OME-779`'s own RED test (`Age`
  present) demonstrates the change without manufacturing a test that must then be broken.

**Baseline recorded:** `run_gates.py aigateway` → ALL GATES GREEN on unmodified `origin/main`
(append-only check, ruff check, ruff format, pyright, check_no_enterprise, pytest with coverage ≥80).

**Deliverable produced instead:** the rule-5 inversion inventory below, which is what the
append-only gate actually requires before later phases can proceed.

### Approved prior-test changes (owner approval 2026-08-11)

Rule 5 requires a Confidence-Gate decision before modifying any prior test; the gate is enforced
mechanically by `run_gates.py`'s append-only check. Approval covers exactly these, and no others:

**`OME-782` (tools cacheable)** — `test_tool_bearing_requests_are_ineligible`
(`test_global_cache_key.py:515`) INVERTS · `test_streaming_and_tool_bearing_requests_do_not_participate`
(`test_global_cache_plan.py:399`) INVERTS · `_WIRE_CONTRACT` literal set
(`test_global_cache_reason_vocabulary.py:84`) drops `"tools"`.

Two conformance tests (`test_global_cache_registry_conformance.py:122`, `test_global_cache_key.py:743`)
compute against `PRESENCE_BYPASS_REASONS` rather than hardcoding it and adapt with no edit — noted
because that is the design working as intended.

**`OME-781` (web search cacheable)** — six INVERT (bypass → keyed) across
`test_openrouter_web_search_cache.py` and `test_openrouter_web_plugin.py`; five OBSOLETE and deleted,
their guarantee preserved first in spec §3.3.1 as the approval condition.

**Append-only gate workflow:** test inversions land in their own isolated commit, run with
`--skip-append-only` and this approval cited; every other commit runs the full gate unmodified.

## OME-782 outcome — done

**Design changed mid-unit, twice, both times because a guard rail fired.**

The first attempt flipped `cache_behavior` to `keyed` inside the shared `function_calling_rules`,
promoting all six function-calling providers at once. `test_a_provider_that_declares_a_keyed_rule_backs_it_with_a_real_projection`
refused it — correctly. Only **two** providers (Anthropic, OpenRouter) implement
`global_cache_projection`; the other four inherit `CacheBypass` from `ProviderPluginBase`, so
promoting them would advertise a cacheable parameter to callers who can never be served from cache.
The house rule for exactly this is recorded at `plugins/antigravity_provider/parameters.py:68`:
implement the projection FIRST, then flip.

Final design, after the owner cut scope to OpenRouter: **opt-in per provider.**
`function_calling_rules` gained a keyword-only `cache_behavior: CacheBehavior = "bypass"`, and
OpenRouter alone passes `"keyed"`. Adding a provider later is now a one-line change at a call site
rather than a core edit. The four missing projections are filed as `OME-787`…`OME-792`.

**Actual files:** `core/standard_parameters.py` (opt-in parameter),
`core/request_cache/global_eligibility.py` (`tools`/`tool_choice` out of `PRESENCE_BYPASS_REASONS`,
`BYPASS_TOOLS` deleted), `core/request_cache/global_keys.py` (import/`__all__` cleanup,
`PARAMETER_CONTRACT_REVISION` → `2026-08b`), `core/cache_ports.py` (`"tools"` out of
`PUBLISHED_CACHE_REASONS`), `plugins/openrouter_provider/parameters.py` (the single opt-in).
Tests: new `tests/unit/test_global_cache_tool_requests.py` (8), plus the six approved prior-test
changes.

**Gates:** ALL GREEN (`--skip-append-only`, see below). Full unit suite **3030 passed**, 0 failures.
Independently re-run by the orchestrator, not taken on the implementer's report.

**Prior tests changed (owner-approved):** the three originally approved (f/g/h) plus three more the
change surfaced — the `>= 15` reason-floor (now 14, `"tools"` legitimately left the published
vocabulary), the e2e `test_chat_request_cache.py` bypass reason (now `BYPASS_DECLARED`, still
bypassing because Anthropic is unpromoted), and OpenRouter's keyed-path proofs. Run with
`--skip-append-only`; the gate cannot see these, so a reviewer must.

**Confirmation the seam works:** `tests/unit/anthropic/test_anthropic_global_cache_projection.py`
needed **zero** edits, and the antigravity conformance failure disappeared on its own.

**Deviations:**
- Implemented before `OME-779` rather than after. Within a single PR nothing ships separately, and
  §5.4's correction removed the sequencing constraint entirely.
- `AIDEV-NOTE` for `OME-781`: `test_openrouter_top_p_promotion.py` now uses `web_search` as its
  "a genuinely declared-bypass rule exists" anti-vacuity example, because `tools` no longer is.
  `OME-781` promotes `web_search` to keyed and will therefore break that proof again — it needs a
  third example, ideally one that is permanently bypass. Expected, not a surprise.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
