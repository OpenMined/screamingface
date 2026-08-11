# OME-777 — Cacheable web search

**Status:** draft for approval · **Date:** 2026-08-11 · **Stacks:** `aigateway`, `url4-cloud`

## 1. Problem

ScreamingFace runs the same benchmark prompts repeatedly. aigateway holds a global,
identity-independent response cache — a hit returns a stored answer without ever resolving a
provider credential — which is what makes reruns cheap. Web-search-backed requests are excluded
from it entirely, through both mechanisms the platform offers:

- **Path A — Tavily tool loop**, owned by url4-cloud. `runner/connector.py::_chat_completion_loop`
  iterates up to `web_tool_max_iterations` (default 5), attaching
  `{"tools": WEB_TOOLS, "tool_choice": "auto"}` (`runner/web_tools.py`) to each
  `/v1/chat/completions` call. url4-cloud executes the resulting tool calls against Tavily itself
  and appends results to `messages`.
- **Path B — OpenRouter native.** The caller sends `web_search: true` plus optional
  `web_search_excluded_domains`; `plugins/openrouter_provider/web_search.py::apply_web_search`
  turns them into a `plugins` envelope.

Three independent reasons keep both out of the cache. Each is a deliberate, documented ruling
with a named failure it prevents — none is a mistake, which is why this is an extension of the
design rather than a repair.

| # | Reason | Where | Status after this spec |
|---|---|---|---|
| 1 | Tool-bearing requests bypass by presence alone | `core/request_cache/global_eligibility.py` | Lifted by decision D1 |
| 2 | A deployment env var changes the upstream call without reaching the key | `plugins/openrouter_provider/{settings,web_search}.py` | Removed by decision D2 |
| 3 | The projection's `prepared` is only complete because search requests never reach the cache | `plugins/openrouter_provider/parameters.py` | Dissolves with #2 |
| — | Retrieval is time-varying; the cache cannot express freshness | `core/request_cache/global_controls.py` | **Not waived.** Addressed first, §6 |

## 2. Decisions

Taken by the owner with the development team, 2026-08-11:

- **D1 — tool calls may be cached.** The `tools`/`tool_choice` presence-bypass is lifted for every
  provider, not only for web search.
- **D2 — the deployment blocklist is deleted.** `AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS` and
  its backing setting are removed. The request body becomes the single source of truth for blocked
  domains.
- **D3 — no admission-control replacement** for the operator floor D2 removes. Accepted on the
  evidence in §3.3.

D2 is the load-bearing one, and it is a **deletion, not a feature**. The escape hatch previously
scoped for this work — a new `deployment_request_defaults(body)` port on `core/plugin_base/_provider.py`
plus an ordering-sensitive call site in `routes/chat.py` — existed solely to fold that env var into
the request body so the key could observe it. With the variable gone, the port has nothing to carry.
Both core-layer changes are struck from scope. The projection-purity guard in
`tests/unit/test_global_cache_projection_purity.py` passes untouched, because the impure input has
been removed rather than routed around.

## 3. Verified current state

### 3.1 How a key is built

`core/request_cache/global_keys.py` assembles nine fields — `provider`, `requested_model`,
`resolved_model`, `messages`, `system`, `keyed_parameters`, `prepared_request`,
`parameter_contract_revision`, `provider_adapter_revision` — plus `schema` and `operation`
constants, then serializes with
`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` and
SHA256s the UTF-8 bytes.

Two consequences govern every design choice below:

- **Object keys are sorted; array order is preserved.** Any list-valued input is order-sensitive.
- Non-string object keys and over-deep nesting are rejected outright, because they would coerce
  into a colliding canonical form.

### 3.2 How a field becomes eligible

`core/request_cache/global_eligibility.py::_accept` resolves each body field to one disposition,
declared on its rule with no default permitted:

- `keyed` — the raw value enters `keyed_parameters`.
- `transport_only` — accepted, proven not to affect output, deliberately excluded.
- `bypass` — the request gets no cache entry (`BYPASS_DECLARED`).

Plus structural bypasses: `BYPASS_UNKNOWN_PARAMETER` (no rule), `BYPASS_MODE_RESTRICTED` (rule not
offered in all of the provider's auth modes), `BYPASS_MALFORMED_PARAMETER` (schema failure), and
`PRESENCE_BYPASS_REASONS` — `metadata`, `tools`, `tool_choice` — which bypass on presence alone,
even when empty.

A fourth mode matters here: when a rule's `projection_kind` is `provider_native`, the raw value is
**not** hashed. Its *effective* form is expected inside `prepared_request`, with `projected_root`
naming where. The mechanism exists explicitly to stop spelling variance splitting one logical
request across entries.

### 3.3 The env var, and why deleting it is safe

`plugins/openrouter_provider/settings.py` reads `AIGW_OPENROUTER_WEB_SEARCH_EXCLUDED_DOMAINS`
(prefix `AIGW_OPENROUTER_`) into `web_search_excluded_domains: list[str] = Field(default_factory=list)`.
`apply_web_search` unions it with the caller's list — `sorted({*settings…, *caller_excluded})` —
and emits `{"id": "web", "engine": "native"}` plus optional `exclude_domains`.

Evidence supporting D3:

- Nothing in the repository sets the variable: no helm chart under `apps/aigateway/charts/**`, no
  `.env` example, no aigateway-ui reference.
- It defaults to an empty list, so an unset deployment already has no floor.
- url4-cloud **already** sends `web_search_excluded_domains` in the request body
  (`runner/connector.py`), sourced from `web_search_exclude` in `runner/request_parameters.py`,
  and re-enforces exclusions on results.

So the variable is a redundant second source, not the operative one, and D2 aligns Path B with what
Path A has always done. **Residual risk:** an out-of-band deployment could still set it. If one is
found, D3 must be revisited — the recommended replacement is admission control (reject a request
whose exclusions omit a mandated set) rather than silent body mutation, since a rejection produces
no cache entry and cannot corrupt the shared store.

#### 3.3.1 The operator floor, written down before it is deleted

Five existing tests are the executable specification of the capability D2 removes. They are deleted
by `OME-781`, with owner approval given 2026-08-11 on the explicit condition that what they
guaranteed is recorded here first — so the capability is recoverable from this document rather than
only from git archaeology.

The deleted guarantee, in full:

> A deployment may declare a set of domains that its web searches must never touch. That set is
> applied to **every** search request the deployment handles, whether or not the caller asked for
> it. A caller may **add** exclusions but may **not** remove or override a deployment's exclusion —
> the dispatched set is the union of the two, never the caller's alone.

Enforced by, and lost with:

| Test | Property it pinned |
|---|---|
| `test_deployment_exclusions_apply_without_the_caller_asking` (`test_openrouter_web_plugin.py:245`) | The floor applies unrequested |
| `test_caller_exclusions_are_added_to_the_deployments` (`:251`) | Caller and deployment sets union |
| `test_a_caller_cannot_drop_a_deployment_exclusion` (`:260`) | **The floor is not caller-overridable** |
| `test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key` (`test_openrouter_web_search_cache.py:121`) | The floor never reaches the cache key |
| `test_caller_exclusions_alone_are_never_keyed` (`:103`) | Caller exclusions alone do not make a request keyable |

**After this epic, no server-side floor exists**: a caller may search any domain it does not itself
exclude. That is the accepted trade of D2/D3, on the evidence that no deployment sets the variable.
Should the floor need to return, rebuild it as admission control per §3.3 — reject a request whose
exclusions omit the mandated set — never as a silent body mutation, which is what made the original
uncacheable.

### 3.4 The freshness gap

`core/request_cache/global_controls.py` states the cache-control grammar is closed: exactly
`use-cache` is understood, and any other field bypasses. `routes/chat_cache_stage.py` emits
`X-AIGW-Cache`, `-Reason`, `-Key`, `-Write` — **no `Age`**.

url4-cloud compensates defensively: `runner/cache_readback.py::requires_revalidation` returns
`True` whenever `outcome.age_s is None`, and `runner/connector.py` re-issues with
`CachePolicy(participate=False)`.

The storage layer, however, is already built for freshness.
`core/request_cache/models/request_cache_entry.py` carries `created_at`, `updated_at`,
`expires_at` (indexed, nullable, already enforced in `store.get()`), `last_hit_at` and `hit_count`,
with a comment stating nullable was chosen so "a later configurable-TTL feature can adopt the
column unchanged."

## 4. Invariants this work introduces

### I1 — one builder, two consumers

> The web-search envelope is produced by exactly one pure function, called by **both** the dispatch
> path and the key path.

Ruling 34's failure is projection and dispatch disagreeing: identical bodies, one key, two
different upstream calls. Today that is prevented by an invariant recorded in
`plugins/openrouter_provider/parameters.py` — the `plugins` envelope is emitted only when
`web_search is True`, and every such request bypasses, so no cacheable request carries one, so
`prepared` is complete. This work deliberately destroys that invariant by making those requests
cacheable. I1 replaces it: a shared implementation makes drift structurally impossible instead of
merely tested against.

### I2 — normalization follows dispatch

> A value may be normalized for the key **only if the dispatched payload is normalized identically,
> by the same code.**

`exclude_domains` may be normalized, because we construct that envelope. `tools` may **not**, because
it is forwarded untouched — tool order plausibly influences model output, so sorting for the key
while dispatching unsorted would be two different upstream calls under one key.

I2 is why §5.2 and §5.3 reach opposite conclusions about list ordering; they are the same rule
applied to different ownership.

## 5. Target state

### 5.1 Phase 0 — characterization safety net (`OME-778`)

Encode current behaviour before changing any of it: bypass reasons per cause, key stability across
process restarts, key sensitivity to keyed vs `transport_only` fields, projection purity, revision
isolation, and verbatim response replay including `usage`. The last deliberately pins a known
defect so §7's decision on it appears as a visible diff. No production code changes.

### 5.2 Phase 2 — Path B, OpenRouter native (`OME-781`)

1. Delete `web_search_excluded_domains` from `settings.py` and the env var with it.
2. Extract `build_web_search_plugin(body) -> dict | None` in `web_search.py`. Pure: body in,
   envelope or `None` out; no settings parameter. Normalizes domains — strip, casefold, dedupe,
   sort. `apply_web_search` becomes a thin writer over it.
3. `global_cache.py::project_global_cache_request` calls the same builder and emits the envelope
   into `prepared`. Legal now, because every value in it originates in the body the projection was
   handed.
4. `parameters.py`: both rules move from `direct_rule(..., cache_behavior="bypass")` to
   `provider_native_rule(...)` with `projected_root` at the envelope. This is a **rule-factory
   swap**, not a keyword change.
5. Bump `GLOBAL_CACHE_ADAPTER_REVISION` `openrouter-global-cache-2026-08b` → `-08c`. Mandatory:
   rows written under bypass semantics must be abandoned, not re-served.

**Retain** the guard in `plugin.py` rejecting `web_search_excluded_domains` without
`web_search is True`. It enforces the emission precondition at the boundary and becomes *more*
load-bearing once these requests are cacheable.

Keying the effective envelope rather than the raw fields is required by §3.1: raw-keying an
order-sensitive domain list would fragment identical questions across rows. It also yields a free
correctness cleanup — `web_search: false` produces no envelope and collapses to the same key as
omitting the field, retiring the "no falsy exemption" cost documented in `parameters.py` today.

### 5.3 Phase 3 — Path A, tool-bearing requests (`OME-782`)

1. Remove `"tools"` and `"tool_choice"` from `PRESENCE_BYPASS_REASONS`. **`"metadata"` stays** — its
   rationale is unrelated (caller-identifying, no proven closed transport-only subset) and it is not
   riding along on D1.
2. `core/standard_parameters.py::function_calling_rules` — both fields `bypass` → `keyed`.
3. Bump the parameter-contract revision.

**Correctness.** The cache stores one model call, not a negotiation: `(messages, tools, tool_choice,
params)` → the model's reply. Turn 2 of a loop carries tool results verbatim in `messages`, so
differing results yield differing keys with no special handling.

The apparent hazard — two callers defining an identically-shaped tool backed by different services,
colliding on one key — is safe, because the cached value is only *"call `web_search` with query Z"*.
Execution is caller-side and never cached. Any schema difference, including descriptions, already
separates the keys. Record this in a test comment; it is the objection a future reader will raise.

**`tools` is keyed verbatim and never sorted**, per I2, with the reason in a comment so it is not
later "optimized".

**Expected value, stated honestly.** Turn 1 of the Tavily loop is the smallest-context call; later
turns carry accumulated results and cost more. This caches the cheapest call in the chain and saves
no Tavily spend at all, since those calls never traverse aigateway. It is cheap and correct, but it
is not the answer to web-search cost — §5.5 is.

### 5.4 Phases 1a/1b — freshness (`OME-779`, `OME-780`)

Ships **before** 5.2 and 5.3, and the ordering is load-bearing rather than stylistic. Because
`requires_revalidation` discards any hit whose age is unprovable, every new hit created by phases 2
and 3 would be thrown away and re-issued — an extra round trip in place of a saving. Shipping
caching first makes the platform's primary consumer measurably slower.

**aigateway (`OME-779`)** — emit `Age` from `created_at` on hits; widen the closed grammar to accept
`max-age` alongside `use-cache`; refuse to serve an entry older than a stated bound; set
`expires_at` on write from a configurable TTL policy. Confirm during design whether a migration is
required; the column already exists.

**url4-cloud (`OME-780`)** — parse `Age` into the existing `age_s`; send `max-age` on bounded runs;
return `False` from `requires_revalidation` when age is proven within bound. **Keep** the defensive
re-issue for responses carrying no `Age`: deployments are not atomic, and this is a live version-skew
path, not dead code.

### 5.5 Phase 4 — retrieval cache (`OME-783`)

Two different caches are conflated in this problem space. aigateway's answers *"was this exact model
call made before?"*; web search needs *"was this retrieval performed recently?"*. The second belongs
in url4-cloud, which owns the Tavily client.

A TTL'd cache keyed on the normalized `(query, exclusions)` pair, wrapping the Tavily calls in
`runner/`. `web_fetch`-by-URL is cached separately from `web_search`-by-query; their staleness
profiles differ. Exclusion re-enforcement must still run on a cache hit, not only on a fresh fetch —
a cached result set must not bypass a safety check a live one receives.

This is the highest-payoff item in the epic and the easiest to drop, because it is not where the
interesting correctness problem lives.

## 6. Wire contract changes

Both are cross-app; url4-cloud parses these bytes.

| Direction | Change | Compatibility |
|---|---|---|
| Response | New `Age` header on cache hits | Additive. Older clients ignore it and keep revalidating defensively. |
| Request | `max-age` accepted in the cache-control field | Additive, but a **deliberate widening of a deliberately closed grammar** — must be reviewed as a contract change, not a parameter addition. Unknown fields continue to bypass. |

## 7. Open decisions

Both block close of `OME-779`.

- **Usage replay.** `store.get()` returns the upstream JSON verbatim and `routes/chat.py` returns it
  unmodified, so a hit replays the *first* caller's `usage`. Token counts misreport for everyone
  after. Pre-existing, but every phase here raises hit rate and magnifies it. Options: leave and
  document; zero on hit; annotate alongside the existing cache headers. Owner: whoever owns
  benchmark cost accounting.
- **TTL default** for search-backed entries. The policy is built configurable regardless; the
  default value is unset pending a call.

## 8. Out of scope

- `metadata`'s presence-bypass (§5.3).
- Admission control replacing the deleted operator floor (D3, §3.3).
- Any change to the canonical-JSON serializer, `BYPASS_MODE_RESTRICTED` handling, or
  `_is_a_whole_answer`.
- Streaming responses, unless the safety net surfaces an interaction.

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Projection and dispatch drift apart | Catastrophic, silent | I1 + the property test in §10 |
| An out-of-band deployment sets the deleted env var | High | Confirm with the owner before merge; §3.3 records the fallback |
| Version skew during the `Age` rollout | Medium | No-`Age` path tested as first-class, not as fallback |
| Stale search results served | Medium | Freshness ships first; TTL on search-backed entries |
| Usage misreporting spreads with hit rate | Medium | §7 decision required before `OME-779` closes |
| Key fragmentation from list ordering | Low, hit-rate only | Normalize where I2 permits; accept and document where it does not |

## 10. Test obligations

Non-negotiable, in addition to each phase's own coverage:

1. **Projection ≡ dispatch** — property test over arbitrary bodies asserting the envelope in
   `prepared` equals the `plugins` block `apply_web_search` writes. This is what makes I1
   enforceable; a reviewer should refuse `OME-781` without it.
2. **Deployment independence** — replaces the obsolete
   `test_the_deployment_blocklist_cannot_smuggle_itself_into_a_key`. Two plugin instances with
   different settings must now produce the **same** key for the same body: same intent, inverted
   assertion.
3. Domain case/order/duplicate variance → same key; genuinely different sets → different keys.
4. `web_search: false` ≡ omitted.
5. `tools` reordered → **different** key, asserted deliberately with its reason.
6. `metadata` still bypasses after `OME-782`; cross-provider regression pass.
7. `Age` correctness; `max-age: 0` never serves; expired row not served; url4-cloud skew path.
8. `08b` rows never served under `08c`.

Roughly 23 existing assertions across `tests/unit/openrouter/test_openrouter_web_search_cache.py`
(12 functions) and `test_openrouter_web_plugin.py` (11 tests) pin the current bypass and will
largely invert. That suite is an asset here: it already states the right intents.
