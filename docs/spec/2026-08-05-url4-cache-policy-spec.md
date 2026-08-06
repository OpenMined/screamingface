---
title: url4 per-run cache policy — technical specification
status: PROPOSED — **all decisions LOCKED**. Awaiting approval to implement. No code written.
created: 2026-08-05
revised: 2026-08-06 (r8 — corrections found by the implementation's adversarial review)
author: Claude (Opus 5) + Sergey
ticket: UNFILED — Linear MCP unauthenticated at authoring time (see the ledger)
related:
  - packages/url4/src/url4/streaming/protocol/     # where the protocol types land
  - docs/spec/2026-07-21-url4-cloud.md
  - docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md   # the HTTP-caching precedent
  - docs/spec/2026-07-15-url4-cloud-runner-spec.md          # §14 doctrine fork F4
  - apps/aigateway/src/aigateway/core/request_cache/keys.py # the upstream contract consumed
---

# url4 per-run cache policy (v1)

## 0. Status & revision history

| rev | date | change |
|---|---|---|
| r1 | 2026-08-05 | First draft — located the change in url4-cloud's REST layer. |
| r2 | 2026-08-05 | **Superseded r1's location.** Owner: protocol belongs in `packages/url4`; both HTTP header *and* protocol frame are carriers. Adds §3 D3/D4 and §5.2. |
| **r8** | 2026-08-06 | **Corrections from the implementation review.** §4.1 said "exactly one field" while the type carries two (`participate`, `max_age`) — the plan superseded itself and the spec never caught up. §9.7 struck (unsatisfiable under v2). §9.10 restated as N/A. §5.2's "first attach wins" narrowed to what the code actually guarantees. |
| **r7** | 2026-08-05 | **Owner locked the last four**: D3 extend `AttachData` · D4 header wins · D6 standard `Cache-Control` · D11 **honour `max-age`**. D11 carries two upstream blockers — §3.5. Spec is decision-complete. |
| **r6** | 2026-08-05 | **Standards alignment.** Read-back prefers **`Cache-Status`** (RFC 9211) over the ad hoc `X-AIGW-Cache*`; **`Age`** (RFC 9111 §5.1) makes `max-age` honourable, so **D11 is reopened** (§3.5). Adds §2.2 with the registry evidence. |
| **r5** | 2026-08-05 | **Rebased on aigateway v2** (`OME-305`, PR #507 — WIP, assumed landing). v2 is a **global, never-expiring, ON-by-default cache with a CLOSED one-field grammar**. This **revokes r4** (v2 rows never expire, so TTL knobs are v1's), **deletes the aigateway sub-issue** (#507 does the chart itself), and **collapses the protocol to a single opt-out signal** — §1.0. Security section rewritten: the cache is now shared across accounts. |
| r4 | 2026-08-05 | ~~TTL/size knobs pinned explicitly in the chart~~ — **REVOKED by r5.** |
| r3 | 2026-08-05 | **D1 LOCKED: caching is ON by default; only disabling is explicit.** That makes the aigateway **chart** part of the deliverable (D8 reversed) and makes this cross-app — see §2.1. Ensemble-determinism tradeoff (§8.2) accepted by the owner on the record. |

**Nothing here is implemented.** Per CLAUDE.md rule 3, implementation starts only on explicit
approval in plain words.

## 1.0 Upstream contract — aigateway v2 (PR #507), assumed

This spec is written against **`OME-305` / PR #507 `feat(aigateway): add global exact-request
cache`** — open, non-draft, +12152/-547 at time of writing. It is **assumed to land**; url4 must
be ready for it. Everything below consumes that contract rather than the v1 one this spec
originally targeted.

**What v2 is**, from its own source:

| property | v2 | consequence for url4 |
|---|---|---|
| **Scope** | **ONE global cache shared by every hosted caller.** "identity is structurally absent" — no account, profile, user, auth-mode or credential anywhere in the key (`global_keys.py`) | The per-account scoping this spec's §8.1 relied on is **gone** |
| **Default** | **ON** — "an ordinary request participates; the control object exists only to OPT OUT" (`global_controls.py`) | D1 is now aigateway's own design, not a url4 choice |
| **Expiry** | **Rows never expire** (`values-prod.yaml`: *"rows never expire"*) | The owner's no-expiry requirement is satisfied upstream. **r4's chart TTL pinning is void** — those knobs belong to the v1 lane |
| **Grammar** | **CLOSED. Exactly one field: `use-cache`.** Any other key — including alongside a valid `use-cache: true` — makes the request **bypass** | url4 may send **only** `use-cache`. `no-store`/`no-cache`/`ttl`/`s-maxage` are **retired** and now *cause* a bypass |
| **Key** | the complete effective output-affecting call — prompt + every `keyed` parameter + the provider's pure projection | a run's `temperature` etc. now participate; v1 bypassed on them |
| **Operator gate** | `request_cache_enabled` still `False` in code; `values.yaml` `requestCache.enabled: false`, **`values-prod.yaml` `true`** | **#507 does the chart work.** The aigateway sub-issue this spec added in r3 is deleted |

**The exact parse (`parse_global_cache_controls`):**

| body | result |
|---|---|
| no `cache` key · `cache: null` · `cache: {}` | **participate** — "absent, null or an empty object all state nothing" |
| `{"use-cache": true}` | participate |
| `{"use-cache": false}` | bypass, reason `opted_out` |
| `{"use-cache": "yes"}` (non-bool) | bypass, `malformed_controls` |
| **any other key**, even with a valid `use-cache` | bypass, `unsupported_control` |

**So the entire protocol surface url4 needs is one signal: participate, or opt out.** Anything
richer is not merely unnecessary — it actively causes a bypass.

## 1. Purpose & scope

### 1.1 The gap

aigateway has a complete response cache — keyed store, TTL, bypass reasons, response headers —
and **url4 cannot reach any of it**.

| # | fact | evidence |
|---|---|---|
| 1 | Caching is **opt-in**; absent opt-in the request bypasses | `aigateway/routes/chat_dispatch.py:191` — `if not controls.use_cache: return None, "bypass", "not_requested"` |
| 2 | Opt-in arrives as a `cache` object in the **request body**, popped before provider plugins | `aigateway/core/request_cache/keys.py:71-86` |
| 3 | url4-cloud's outgoing body is **hardcoded** | `url4_cloud/runner/connector.py:337-339` — `json={"model": model, "messages": messages, **extra}`; `extra` is only `{tools, tool_choice}` |
| 4 | Therefore **every url4 run bypasses today**, reason `not_requested` | 1 + 3 |
| 5 | aigateway reports outcome in headers nothing reads | `chat_dispatch.py:218-226` sets `X-AIGW-Cache`, `X-AIGW-Cache-Reason`, `X-AIGW-Cache-Key` |
| 6 | The url4 protocol has **no** cache vocabulary inbound | `packages/url4/.../protocol/unions.py:81` — `InboundFrame = StopEvent \| AttachEvent` |
| 7 | …but it **already has** the reporting half | `packages/url4/.../protocol/taxonomy.py:19-42` — `cache_read_tokens`, `cache_creation_tokens`, `cache_read_usd`, `cache_creation_usd` |

**The inversion that shapes this spec:** the obvious request — "a switch that turns caching off"
— is a **no-op**, because off is already the state of every path. The mechanism must carry
policy in *both* directions or it changes nothing.

Fact 7 is the argument for locating this in `packages/url4`: the protocol can already *describe*
a cached turn and simply cannot *ask* for one.

### 1.2 Non-goals

- **Per-node cache intent.** A url4 expression fans out to many aigateway calls; this policy
  covers all of them. "Node A cacheable, node B fresh" needs grammar
  (`packages/url4/src/url4/core/grammar.py` has no cache token) and reopens doctrine fork **F4**
  (`docs/spec/2026-07-15-url4-cloud-runner-spec.md:118`). Deliberately out of scope.
- **A url4-native / Enclave GET cache.** Still deferred, same §14.
- **Any aigateway *code* change.** Its request-cache contract is complete and consumed as-is.
  Its **chart** does change — see §2.1.
- **Streaming turns.** `build_cache_key` bypasses on `stream: true`
  (`aigateway/core/request_cache/keys.py:104`) — caching exists only on the transactional half,
  the same WS/GET split doctrine N1 already draws.

## 2. Where this lives, and why

**Protocol types: `packages/url4/src/url4/streaming/protocol/`.** That is where `InboundFrame`,
`AttachData` and the cost taxonomy already live; it ships with the SDK, and url4-cloud already
consumes it via the editable path dependency in its `pyproject.toml:58`.

> **Note for the owner.** `apps/url4-cloud/src/url4_streaming_protocol/` — along with
> `url4_cloud_nats/` and `url4_cloud_runner/` — is an **empty, untracked, unreferenced**
> directory (not in git, not in `pyproject.toml`'s `packages = ["src/url4_cloud"]`, imported
> nowhere). Treated as a stale local artifact. If a package split is genuinely intended, it is
> its own epic and this spec should not pre-empt it.

**Consumption: `apps/url4-cloud`.** Unavoidable and consuming-side only — it is the only thing
that talks to aigateway (`runner/connector.py:337`) and the only thing that terminates the WS
(`ws/bridge.py:141`). It defines no protocol types.

**`apps/aigateway`: chart only, no code.** See §2.1.

## 2.1 The server flag — why this is cross-app (r3)

Caching is off at **two independent layers**, and D1 only addresses one of them:

| layer | state | evidence |
|---|---|---|
| **Server flag** | `False` by default, and **the chart never sets it** | `aigateway/config.py:127-129` — `request_cache_enabled: bool = Field(default=False, validation_alias="AIGW_REQUEST_CACHE_ENABLED")`; its own comment says *"Disabled by default"*. The chart passes 16 env keys (`AIGW_ALLOWED_NETWORKS`, `AIGW_AUTH_MODE`, `AIGW_OPENROUTER_ENABLED`, …) and this is not among them. |
| **Per-request opt-in** | `False` unless asked | `chat_dispatch.py:191` |

**The deployed gateway therefore answers `bypass / disabled` today**, before per-request controls
are consulted. D1=ON alone changes nothing observable.

"Active by default" requires **both**:

```
AIGW_REQUEST_CACHE_ENABLED=true    ← apps/aigateway chart  (values.yaml)
              AND
cache.use-cache defaults to true   ← apps/url4-cloud       (D1)
```

Note the env prefix is **`AIGW_`**, not `AIGATEWAY_`. aigateway uses both inconsistently
(`AIGATEWAY_ADMIN_EMAILS` vs `AIGW_AUTH_MODE`); this setting is `AIGW_`.

**Consequence — CLAUDE.md rule 8.** The work now spans three components, so it is an **epic with
one sub-issue per landing**, never one ticket:

| sub-issue | landing | content |
|---|---|---|
| 1 | `pkg` → url4 | protocol types (§4) |
| 2 | `app` → url4-cloud | both carriers, threading, egress, read-back (§5-§7) |
| 3 | `app` → aigateway | chart sets `AIGW_REQUEST_CACHE_ENABLED` **plus the three TTL/size knobs, pinned** (r4) |

Sub-issue 3 has a different CODEOWNERS reviewer and can land **first and independently** — it is
a no-op until sub-issue 2 sends `use-cache`.

## 2.2 Standards alignment (r6)

Every claim here was verified against the RFC text and the IANA registry, not recalled.

**Where a standard exists and fits exactly — use it:**

| need | standard | fit |
|---|---|---|
| "do not cache this run" (request) | **`Cache-Control`** — RFC 9111 §5.2.1 | Exact. `no-store` is *"A cache MUST NOT store any part of either this request or any response to it"* — both directions, which is precisely v2's all-or-nothing `participate`. |
| "was this cached, and why not" (response) | **`Cache-Status`** — RFC 9211 §2, Standards Track | Exact, including `fwd=bypass` and `fwd=miss` as **defined tokens** (§2.2). Parameters: `hit` §2.1 · `fwd` §2.2 · `stored` §2.5 · `key` §2.7 · `detail` §2.8. |
| "how old is this answer" | **`Age`** — RFC 9111 §5.1 | *"the sender's estimate of the time since the response was generated"* — see §3.5. |

**Where no standard exists — verified against the IANA HTTP Field Name Registry:**

| our header | registry |
|---|---|
| `X-Profile` (routing/tenant selection) | **no permanent registered field** for tenant, profile or routing selection |
| `X-User-Email` (mesh-injected identity) | **no permanent registered field** for conveying end-user identity from a proxy/gateway |

Legitimately custom. The only defect is the **`X-` prefix**: RFC 6648 / **BCP 178** (June 2012)
says *"Creators of new parameters… SHOULD NOT prefix their parameter names with 'X-'"*. A rename,
not a redesign — and out of scope here.

**Where a standard exists and was deliberately rejected — correctly:** `URL4-Capability` could
have been `Authorization: Bearer`. Commit `79f6e9dc` explains why not — *"so an API gateway /
mesh / SDK that owns the primary identity slot cannot strip or overwrite it"*. Sound in a
topology where Envoy and Cloudflare Access both touch `Authorization`. It also already complies
with BCP 178. **Unchanged.**

**Consequence for this spec:** url4 reads **`Cache-Status` first**, falling back to the
`X-AIGW-Cache*` triple. Forward-compatible whether or not #507 adopts the suggestion (§7).

## 3. Design decisions

**LOCKED** where the codebase or an owner ruling settles it; **OPEN** where the owner must
choose. The OPEN items are the point of this review.

| # | decision | value | status |
|---|---|---|---|
| **D1** | Default when nothing is declared | **ON** — caching active; only disabling is explicit (§3.1) | 🟢 **LOCKED** (owner, r3) |
| D2 | HTTP carrier | header on `GET /`, mirroring `X-Profile` (`rest/routes.py:347`) | 🟢 LOCKED |
| D3 | Frame shape | **extend `AttachData`** (§3.2) | 🟢 LOCKED (owner, r7) |
| D4 | Precedence when both carriers speak | **header wins**, override logged (§3.3) | 🟢 LOCKED (owner, r7) |
| D5 | Scope | whole run — every leaf, every fan-out branch | 🟢 LOCKED (§1.2) |
| D6 | Header name / intermediary participation | **standard `Cache-Control`**; intermediaries may participate (§3.4) | 🟢 LOCKED (owner, r7) |
| D7 | Response headers read back and folded onto spans | mandatory, every variant | 🟢 LOCKED (§7) |
| D8 | aigateway changes | **none — PR #507 does it all**, chart included. url4 depends on it landing (§1.0) | 🟢 LOCKED (r5 — reverts r3) |
| D11 | `Cache-Control: max-age=N` | **honour it** — blocked upstream today; opt-out until then (§3.5) | 🟢 LOCKED (owner, r7) |
| D9 | Protocol location | `packages/url4/.../streaming/protocol/` | 🟢 LOCKED (owner, r2) |
| D10 | Both carriers supported | yes | 🟢 LOCKED (owner, r2) |

### 3.1 D1 — the default — **LOCKED: ON**

> **Owner ruling (r3):** caching is **active by default**; only *disabling* is specified
> explicitly. The spec had recommended the opposite; the owner overruled it, and the
> determinism consequence in §8.2 was **explicitly accepted**.

| | |
|---|---|
| **Default** | `use_cache = True` when neither carrier declares a policy |
| **To disable** | `Cache-Control: no-store` (HTTP) or `{"cache": {"participate": false}}` (frame) |
| **Prerequisite** | The operator gate, which **PR #507 already sets** — `requestCache.enabled: true` in `values-prod.yaml`. url4 does nothing here (§1.0). |

**What this buys:** a fan-out with repeated sub-prompts collapses to one provider call, and the
owner's original ask (`no-store` for a specific execution) becomes meaningful rather than a
restatement of the default.

**What it costs, accepted:** cost *and* determinism change for every existing run the moment the
chart flag lands — see §8.2. The rollout order in §2.1 is the mitigation: the chart sub-issue is
inert until url4-cloud ships the default, so the two can be sequenced deliberately rather than
landing together by accident.

**The `None` vs `CachePolicy()` distinction (§4.1) survives this decision and gets *more*
important:** "did not declare" now resolves to ON, while an explicit `use_cache=False` resolves
to off. Collapsing them would make `no-store` unexpressible.

### 3.2 D3 — frame shape

| option | trade |
|---|---|
| **Extend `AttachData`** (`signals.py:141`) | No new verb, no new union member. `_require_subscriber` (`rest/routes.py:363`) already guarantees attach precedes the run, so policy is in place before any aigateway call. Cost: `AttachData` becomes two concerns (resume-from-sequence + config), and a mid-run **re-attach** could restate policy — spec must rule first-attach-wins. |
| **New `ConfigureEvent`** | Clean separation, room to carry future run config beyond caching. Cost: a third `InboundFrame` member, a new ordering contract nothing currently enforces, and a decision about what a `Configure` after run start means. |

**Recommendation: extend `AttachData`** for v1 — smallest protocol delta, and attach ordering is
already enforced. Revisit if run configuration grows a second field unrelated to caching.

### 3.3 D4 — precedence when both carriers speak

Given D10, a run can be configured twice: once on WS attach, once on the `GET /` that starts it.

| option | trade |
|---|---|
| **(a) Header wins, override is observable** | Causal order — attach happens first, the GET starts the run and is later. Last-writer-wins is the intuitive reading. A `LogEvent` records that a frame policy was overridden, so it is never silent. |
| (b) Frame wins | The session declared intent up front; the header is per-request noise. Inverts causal order, which will surprise. |
| (c) Conflict is fatal | Fail closed, no ambiguity. Harsh: a whole ensemble run dies over a cache directive. |

**Recommendation: (a).** Explicit-beats-absent in all cases; on genuine disagreement the later,
run-scoped statement wins and says so.

### 3.4 D6 — header name and intermediaries

**Proposed: the standard `Cache-Control` request header.** RFC 9111 already defines `no-store`,
`no-cache`, `max-age`, `only-if-cached` as *request* directives, and aigateway's control names
(`no-cache`, `no-store`, `s-maxage`, `ttl`) were deliberately HTTP-shaped, so the vocabularies
aligned and nothing had to be invented. **(r5: v2 retired all four; only `use-cache` remains, so
the alignment is now at the level of *meaning* rather than field names — url4 collapses every
directive to participate/opt-out at its own edge, §5.1.)** It composes with doctrine N1, which justifies GET *on the
grounds the call is cacheable*.

**Consequence:** a genuine `Cache-Control` may be honoured by Envoy or a CDN. Usually desirable —
it is what the header means. If the directive must reach *only* aigateway, the header must be
`URL4-Cache` instead, matching `URL4-Capability` as a url4-owned contract.

**D6 is one decision in two parts:** standard header *and* intermediary participation, or private
header *and* aigateway-only. A standard header intermediaries are asked to ignore is the worst of
both.

### 3.5 D11 — `max-age`, reopened (r6)

r5 proposed treating `max-age=N` as opt-out on the grounds that "v2 rows never expire, so no
freshness bound can be honoured." **That conflated *never expiring* with *unknown age*.**

`RequestCacheEntry` already carries `created_at` (`auto_now_add=True`), so an entry's age is
computable exactly. RFC 9111 §5.1 **`Age`** is the standard field for reporting it, and RFC 9211
carries the same fact as the `ttl` parameter inside `Cache-Status`.

| option | trade |
|---|---|
| **(a) Honour `max-age` when `Age` is available** | Serve the stored answer if younger than *N*, forward otherwise. Turns a permanent global corpus into something with a **caller-controlled staleness bound** — "reuse yesterday's answer, not last month's" — using only standard fields. **Depends on aigateway emitting `Age` or `Cache-Status; ttl=`**, which it does not today. |
| **(b) Treat as opt-out** *(r5's proposal)* | Conservative, works today, needs nothing from #507. Costs a hit the caller would have accepted. |
| (c) Ignore the directive | The caller silently receives an arbitrarily old answer having explicitly asked not to. Rejected. |

**LOCKED: (a) — honour `max-age`.** Two upstream blockers stand between that decision and a
working implementation, both verified against #507's branch on 2026-08-05:

| blocker | evidence |
|---|---|
| **url4 cannot ASK for a bound.** v2's grammar is closed to `use-cache`; `{"cache": {"max-age": 60}}` returns `_refuse(BYPASS_UNSUPPORTED_CONTROL)` | `global_controls.py:79-83` |
| **aigateway does not REPORT age.** No `Age` header, no `Cache-Status; ttl=` | #507 adds `CACHE_HEADER`/`REASON_HEADER`/`WRITE_HEADER`/`KEY_HEADER` and no age field |

So url4 can neither request a freshness bound nor measure one. **Until one of these changes,
`max-age` degrades to opt-out** — the conservative direction, and observably so via
`X-AIGW-Cache-Reason: opted_out`.

**Two routes to honouring it, in preference order:**

1. **Upstream — aigateway accepts a bound** (`{"cache": {"use-cache": true, "max-age": N}}`).
   One decision, made where the cache lives, and the only version that avoids serving a response
   the caller will discard. Requires v2 to widen its grammar by one field — deliberately, since
   "closed" is currently an invariant. **Raised on #507.**
2. **Client-side revalidation**, buildable by url4 alone the moment `Age` exists: participate,
   read `Age`, and if the entry is older than `max-age`, re-issue the call with
   `use-cache: false`. Costs one extra round trip on a too-old hit — cheap (a cache read, not a
   provider dispatch) but it does transfer a body that is then thrown away, and it multiplies
   across a fan-out.

**Implementation posture:** Batch 3 **parses and preserves** `max-age` rather than collapsing it
to opt-out at the edge, so the value survives to the point where it can be honoured. Batch 7
applies it when an age is available and falls back to opt-out when it is not. That way the day
either blocker lifts, the change is a branch, not a redesign.

## 4. Protocol definitions — `packages/url4`

### 4.1 `protocol/signals.py` — the policy type

```python
class CachePolicy(BaseModel):
    """Per-run cache intent. TWO fields — one that reaches aigateway, one that never does.

    INVARIANT: url4 must never send a control key v2 does not understand. Under v2 an
    unrecognised key does not degrade to "ignored" — it makes the whole request BYPASS
    (`global_controls.py`), so a well-meant `no-store` would opt the caller out for the
    WRONG reason and a well-meant `ttl` would silently lose caching altogether.
    """
    participate: bool | None = None   # None = "not stated" -> D1 default (participate)
    max_age: int | None = None        # url4-INTERNAL. Never sent: v2's grammar would bypass on it.
```

**`max_age` is url4-internal (r8).** It exists so a stated bound survives to the point where it
could be honoured; it is never serialised into the `cache` object, because v2's closed grammar
bypasses on any key but `use-cache`. `extra="forbid"` plus a test pinning
`set(CachePolicy.model_fields) == {"participate", "max_age"}` keeps a third field from appearing.

**Deliberately absent: `no_cache`, `no_store`, `s_maxage`.** r2 had all three. v2 retires them
(`LEGACY_CONTROL_FIELDS`) and bypasses on them, so carrying them in the url4 protocol would model
a capability the upstream does not have.

Resolution table:

| declared | effective | sent to aigateway |
|---|---|---|
| no `cache` field | **participate** (D1) | field omitted |
| `cache: {}` | **participate** — every field unstated | field omitted |
| `cache: {"participate": false}` | **opt out** | `{"cache": {"use-cache": false}}` |
| `cache: {"participate": true}` | participate, explicitly | `{"cache": {"use-cache": true}}` |

Under **D3 (recommended)**, `AttachData` gains one optional field:

```python
class AttachData(BaseModel):
    from_sequence: int | None = Field(default=None, ge=1)
    cache: CachePolicy | None = None      # NEW — absent means "not declared", not "off"
```

`None` vs a default-constructed `CachePolicy()` is load-bearing: **absent must mean "did not
declare"**, so D4 precedence can distinguish silence from an explicit `use_cache=False`.

### 4.2 `protocol/signals.py` — reporting the outcome

`SpanData` gains the cache outcome, so a hit is visible per turn:

```python
    cache_status: Literal["hit", "miss", "bypass"] | None = None
    cache_reason: str | None = None       # aigateway's vocabulary, verbatim
```

`taxonomy.py` needs **no change** — `cache_read_tokens` / `cache_creation_tokens` /
`cache_read_usd` / `cache_creation_usd` already exist (`:19-42`).

### 4.3 `protocol/unions.py`

Unchanged under D3-recommended (`AttachEvent` already a member). Under `ConfigureEvent`,
`InboundFrame` at `:81` gains a third member and `InboundFrameAdapter` follows.

## 5. The two request contracts

### 5.1 HTTP — `GET /`

```http
GET /?q=(A,B)!reduce HTTP/1.1
URL4-Capability: <jwt>
X-Profile: prod
Cache-Control: no-store
```

| directive | effective | why |
|---|---|---|
| *(absent)* | **participate** | D1 |
| `no-store` | **opt out** → `{"cache": {"use-cache": false}}` | The caller means "do not use the cache". Mapped to v2's opt-out, **not** forwarded as `no-store` — that key is retired and would bypass with reason `unsupported_control` instead of the honest `opted_out`. |
| `no-cache` | **opt out**, same mapping | v2 has no read-only/write-only lane; "don't serve me a stored answer" can only be honoured by not participating. |
| `max-age=<n>` | **opt out** (D11, §3.5) | v2 rows never expire, so no freshness bound can be honoured. |
| `url4-use-cache` | participate, explicitly | RFC 9111 §5.2.3 extension token. Rarely needed now ON is the default. |

**Only `use-cache` ever reaches aigateway.** Every directive above collapses to participate or
opt out at the url4 edge; none is forwarded verbatim.

**`only-if-cached` is rejected** — see §8.3.

**Unparseable directives are ignored, never fatal**, matching `parse_cache_controls`, whose
docstring states malformed values parse as "not requested".

### 5.2 WS — attach frame

```json
{"type": "ai.url4.attach", "data": {"from_sequence": 1, "cache": {"participate": false}}}
```

**First attach wins, for the life of the subscription (r8).** A re-attach carrying a different
policy does **not** restate it while a subscriber remains. Precise scope, per the implementation:
the registry forgets the declaration when the **last** subscriber leaves, so a client that fully
disconnects and reconnects before `GET /` can state a different policy — that is a new session,
not a re-attach. No run in flight can change: the policy is captured into the job env at schedule
time, and `_require_subscriber` gates run start. A differing re-attach
emits a `LogEvent` at `warn`. Rationale: a run's aigateway calls may already have executed under
the original policy, so a mid-run change would make the run's cache behaviour unreproducible.

### 5.3 Convergence

Both carriers produce a `CachePolicy | None`. Per **D4(a)**: header wins when both are present
and differ, and the override emits a `LogEvent`. Absent on both → D1 default.

## 6. url4-cloud consumption

| hop | file | change |
|---|---|---|
| WS ingress | `ws/bridge.py:141` | `_parse_inbound` already returns the validated frame; carry `data.cache` into session state |
| HTTP ingress | `rest/routes.py:337` | new `Header(...)` param on `start_run`; parse → `CachePolicy` |
| converge | `rest/routes.py` `_schedule` | one new kwarg beside `profile`/`identity`; apply D4 |
| thread | `job_env` / runner | per-**run** value, exactly as `profile` travels — **not** `AigatewayConfig`, which is world config shared by all runs |
| egress | `runner/connector.py:337` | `json={…, **extra, **policy.as_body_field()}` |
| ingress back | `runner/connector.py` | read `X-AIGW-Cache*`, fold onto the span beside `_report_usage` |

`as_body_field()` returns `{}` when there is nothing to say, so **a default run's body stays
byte-identical to today's** — which keeps aigateway's `unsupported_fields` bypass path untouched.

## 7. Observability (D7 — mandatory)

The connector currently calls `_raise_for_status` → `_json_or_raise` → `_report_usage` →
`_parse_choice`, all body-only. It must additionally read the cache outcome and fold it onto the
owning span, the same seam `#506` used for `finish_reason`/`refusal`.

**Read `Cache-Status` first, fall back to the `X-AIGW-Cache*` triple (r6).**

| source | precedence | mapping |
|---|---|---|
| **`Cache-Status`** (RFC 9211) | preferred | `hit` → `hit` · `fwd=<token>` → `miss`/`bypass` with the token as reason · `key=` → key · `detail=` → reason detail · `ttl=` → entry age, feeds D11 |
| `X-AIGW-Cache` / `-Reason` / `-Key` | fallback | today's ad hoc triple, verbatim |

Preferring the standard costs nothing and means url4 needs no change on the day aigateway adopts
it. Parse `Cache-Status` as an RFC 8941 Structured Field **List** — it may legitimately carry one
member per cache that handled the response (aigateway, Envoy, a CDN), ordered origin-closest
first; take the aigateway member, not blindly the first.

**Without this, enabling caching makes the cost taxonomy wrong.** A hit costs nothing upstream,
but `_report_usage` would bill it as a fresh call — an error that *hides savings*, so nobody
notices.

Run-level counters follow the catalog spec's precedent (`…model-catalog-spec.md:309-311`): hits,
misses, and **bypasses by reason** — the load-bearing one, since it turns "I asked for caching
and got none" into an answerable question. **No metric may be labelled by cache key, prompt, or
credential.**

## 8. Security & correctness consequences

1. **Key scope — GLOBAL under v2, and this is the headline change.** v1 keyed
   `{v, account_id, profile_name, provider, model, prompt_hash}`, so two accounts never shared a
   row. **v2 removes identity entirely** — `global_keys.py`'s stated invariant is *"identity is
   structurally absent… That is what makes one row safe to share globally."* Its own story is a
   benchmark operator re-running a suite **from a second account** and being served the first
   run's responses, with the second account's credential never read.

   Consequences url4 inherits rather than creates, and which the owner should see stated:
   - **Any two callers sending the identical effective call get the identical stored response.**
   - Rows are stored as **plaintext compact JSON** in `request_cache_entries.response_ciphertext`;
     `values-prod.yaml` states database readers, replicas, snapshots and backups can read the
     entire corpus. Provider credentials stay encrypted in `credential_blobs` — responses do not.
   - **Rows never expire**, so the shared corpus only grows.

   url4 adds **no new sharing axis** — but it does become a major *producer* into a shared,
   permanent, plaintext corpus, which is a different posture from v1's per-account cache. Enabling
   it is `values-prod.yaml`'s decision, deliberately taken there.
2. **Ensemble determinism — ACCEPTED TRADEOFF (owner, r3).** Two nodes with identical prompts but
   distinct node identities miss the engine's `_memo` (keyed on node identity,
   `dag/executor.py:109`) and hit aigateway's cache (keyed on prompt hash,
   `keys.py:124-130`). Usually the desired dedup — but an ensemble deliberately sampling one
   model twice for variance receives **one answer twice**, and scores it as agreement.

   With **D1 = ON this is the default path, not an edge case.** Narrower than it first sounds,
   because `temperature` participates in the normalised prompt — two samples that differ in any
   sampling parameter key differently. It bites exactly when a run repeats an *identical* request
   expecting non-identical answers.

   **The owner has accepted this.** Recorded here rather than buried so a future reader finds a
   decision, not a bug.

   **v2 makes it strictly worse and the acceptance should be re-confirmed against the new facts:**
   the repeat no longer has to come from the same account, or the same run, or the same day — the
   corpus is global and permanent. A variance sample repeated a month later from another account
   still collapses. Conversely v2 keys the *complete* effective call including `keyed` parameters,
   so anything varying `temperature`, `seed` or a routing control keys differently and is
   unaffected — the collapse needs a genuinely byte-identical call.

   If it needs undoing, the carve-out is the same and still needs no protocol change: a per-run
   nonce in the effective request. Not built now.
3. **`only-if-cached` rejected.** RFC 9111 requires `504` when nothing is cached. A url4 run is a
   fan-out of many calls; one uncached leaf failing the whole run is a footgun with no present
   use case.
4. **No new secret material.** The policy is non-sensitive; `X-AIGW-Cache-Key` is a hash prefix
   by construction.

## 9. Acceptance

1. **(r5)** A run declaring nothing sends **no `cache` field at all** and reports a v2
   participate outcome (`miss` first, `hit` on repeat). Omitting is preferred over
   `{"use-cache": true}`: v2 treats absent, `null` and `{}` identically, and the smallest body is
   the least likely to trip the closed-grammar bypass.
2. `Cache-Control: no-store` sends `{"cache": {"use-cache": false}}` and aigateway reports
   `bypass` with reason **`opted_out`** — **not** `unsupported_control`. This is the test that
   proves url4 collapses directives at its own edge instead of forwarding retired v1 keys.
2a. `Cache-Control: max-age=60` behaves identically to `no-store` (D11).
2b. `cache: {}` on the frame behaves identically to declaring nothing.
2c. **url4 never sends a key other than `use-cache`.** Assert the egress body's `cache` object
   has at most that one key — the single most important regression guard, since any extra key
   silently costs every hit.
3. The same policy delivered on the attach frame produces the identical egress body.
4. Header and frame disagreeing → header applies, and a `LogEvent` records the override.
5. A re-attach with a different policy does **not** change the run, and warns.
6. A default run reports `miss` first, then `hit` on an identical immediate repeat.
7. ~~Two runs under different `X-Profile` never share an entry.~~ **STRUCK (r8)** — a v1 leftover
   the r5 rebase missed. Under v2 identity is structurally absent from the key (§1.0), and url4
   sends the profile as a request *header*, never in the body — so two runs differing only by
   profile **do** share an entry. No url4-side code can satisfy this and none should try.
8. A malformed directive is ignored; the run proceeds and is not 4xx'd.
9. Cache status/reason appear on spans for every case above.
10. **N/A (r8)** — a streaming turn cannot reach this path. The connector only ever posts
   transactional chat completions; there is no `stream` key in the body it builds. The criterion
   was satisfied by absence rather than behaviour, so it is restated here instead of left as a
   test someone will go looking for.

## 10. Open questions for the owner

1. **D3** — extend `AttachData` (recommended) or add `ConfigureEvent`?
2. **D4** — header wins on conflict (recommended), frame wins, or fatal?
3. **D6** — standard `Cache-Control` with intermediary participation, or private `URL4-Cache`?
4. Are the three empty `apps/url4-cloud/src/url4_*` directories a stale artifact to delete, or an
   intended package split to file as its own epic?
**Resolved in r3:** D1 (ON) · D8 (chart in scope) · §8.2 tradeoff (accepted) · the
`request_cache_enabled` question (it is **off**, and turning it on is now sub-issue 3) ·
**TTL/size knobs pinned explicitly in the chart** (owner) — `ttlSeconds: 600`,
`maxTtlSeconds: 3600`, `maxResponseBytes: 1000000`, equal to today's code defaults
(`config.py:130-138`) but frozen so a patch release cannot move production behaviour. Rendered
via `config.requestCache.*` following the chart's existing `values → configmap` pattern; see
plan Batch 0.
