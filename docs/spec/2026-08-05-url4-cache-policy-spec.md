---
title: url4 per-run cache policy — technical specification
status: PROPOSED — awaiting owner decisions D3, D4, D6 (§3). No code written.
created: 2026-08-05
revised: 2026-08-05 (r4 — TTL/size knobs pinned explicitly in the chart)
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
| r4 | 2026-08-05 | Owner: **TTL/size knobs pinned explicitly** in the chart rather than inherited (§10). Closes the last non-D question. |
| r3 | 2026-08-05 | **D1 LOCKED: caching is ON by default; only disabling is explicit.** That makes the aigateway **chart** part of the deliverable (D8 reversed) and makes this cross-app — see §2.1. Ensemble-determinism tradeoff (§8.2) accepted by the owner on the record. |

**Nothing here is implemented.** Per CLAUDE.md rule 3, implementation starts only on explicit
approval in plain words.

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

## 3. Design decisions

**LOCKED** where the codebase or an owner ruling settles it; **OPEN** where the owner must
choose. The OPEN items are the point of this review.

| # | decision | value | status |
|---|---|---|---|
| **D1** | Default when nothing is declared | **ON** — caching active; only disabling is explicit (§3.1) | 🟢 **LOCKED** (owner, r3) |
| D2 | HTTP carrier | header on `GET /`, mirroring `X-Profile` (`rest/routes.py:347`) | 🟢 LOCKED |
| **D3** | Frame shape | extend `AttachData` vs new `ConfigureEvent` — §3.2 | 🔴 **OPEN** |
| **D4** | Precedence when both carriers speak | §3.3 | 🔴 **OPEN** |
| D5 | Scope | whole run — every leaf, every fan-out branch | 🟢 LOCKED (§1.2) |
| **D6** | Header name / intermediary participation | §3.4 | 🔴 **OPEN** |
| D7 | Response headers read back and folded onto spans | mandatory, every variant | 🟢 LOCKED (§7) |
| D8 | aigateway changes | **chart only** — set `AIGW_REQUEST_CACHE_ENABLED=true`; no code (§2.1) | 🟢 LOCKED (owner, r3 — reverses r2's "none") |
| D9 | Protocol location | `packages/url4/.../streaming/protocol/` | 🟢 LOCKED (owner, r2) |
| D10 | Both carriers supported | yes | 🟢 LOCKED (owner, r2) |

### 3.1 D1 — the default — **LOCKED: ON**

> **Owner ruling (r3):** caching is **active by default**; only *disabling* is specified
> explicitly. The spec had recommended the opposite; the owner overruled it, and the
> determinism consequence in §8.2 was **explicitly accepted**.

| | |
|---|---|
| **Default** | `use_cache = True` when neither carrier declares a policy |
| **To disable** | `Cache-Control: no-store` (HTTP) or `{"cache": {"no_store": true}}` (frame) |
| **Prerequisite** | `AIGW_REQUEST_CACHE_ENABLED=true` in the aigateway chart — §2.1. Without it the default is inert and every run answers `bypass / disabled`. |

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
(`no-cache`, `no-store`, `s-maxage`, `ttl`) are deliberately HTTP-shaped — the vocabularies
already align and nothing is invented. It composes with doctrine N1, which justifies GET *on the
grounds the call is cacheable*.

**Consequence:** a genuine `Cache-Control` may be honoured by Envoy or a CDN. Usually desirable —
it is what the header means. If the directive must reach *only* aigateway, the header must be
`URL4-Cache` instead, matching `URL4-Capability` as a url4-owned contract.

**D6 is one decision in two parts:** standard header *and* intermediary participation, or private
header *and* aigateway-only. A standard header intermediaries are asked to ignore is the worst of
both.

## 4. Protocol definitions — `packages/url4`

### 4.1 `protocol/signals.py` — the policy type

```python
class CachePolicy(BaseModel):
    """Per-run cache intent. Declared once, applied to every aigateway call in the run.

    Names mirror aigateway's request-body controls (`use-cache`, `no-cache`, `no-store`,
    `s-maxage`) so the mapping is identity, not translation — there is no second vocabulary
    to keep in step.
    """
    use_cache: bool | None = None     # None = "not stated" — resolves to the D1 default (ON)
    no_cache: bool = False
    no_store: bool = False
    s_maxage: int | None = Field(default=None, ge=1)
```

**`use_cache` is tri-state, and that is a direct consequence of D1=ON (r3).** With a plain
`bool = False` there would be two different ways to say nothing — an absent `cache` field, and a
present-but-empty `cache: {}` — and they would resolve differently: absent → ON via D1,
`{}` → OFF via the field default. A caller sending `{"cache": {}}` would silently disable caching
while believing they had expressed no opinion.

Resolution table:

| declared | effective |
|---|---|
| no `cache` field at all | **ON** (D1) |
| `cache: {}` | **ON** — every field "not stated" |
| `cache: {"no_store": true}` | OFF, and nothing is written |
| `cache: {"use_cache": false}` | OFF — the explicit form |
| `cache: {"s_maxage": 60}` | ON, entry must be younger than 60s |

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

| directive | → aigateway `cache` | meaning |
|---|---|---|
| `no-store` | `no-store: true` | do not read, do not write |
| `no-cache` | `no-cache: true` | do not read a stored entry; still store the result |
| `max-age=<n>` | `s-maxage: <n>` | accept an entry only if younger than *n* seconds |
| `url4-use-cache` | `use-cache: true` | **(r3)** re-enable after a disabling directive earlier in the same header; rarely needed now that ON is the default. RFC 9111 §5.2.3 extension token, ignored by intermediaries. |
| absent | field omitted | D1 default |

RFC 9111 has no "please cache" *request* directive, hence the extension token. If that is
unpalatable it is a further argument for `URL4-Cache` under D6.

**`only-if-cached` is rejected** — see §8.3.

**Unparseable directives are ignored, never fatal**, matching `parse_cache_controls`, whose
docstring states malformed values parse as "not requested".

### 5.2 WS — attach frame

```json
{"type": "ai.url4.attach", "data": {"from_sequence": 1, "cache": {"no_store": true}}}
```

**First attach wins.** A re-attach (reconnect, or `from_sequence` resume) carrying a different
policy does **not** restate it; the run's policy is fixed at run start. A differing re-attach
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
`_parse_choice`, all body-only. It must additionally read `X-AIGW-Cache`,
`X-AIGW-Cache-Reason`, `X-AIGW-Cache-Key` (12 hex, hit/miss only, hash-derived — never prompt
content) and fold them onto the owning span, the same seam `#506` used for
`finish_reason`/`refusal`.

**Without this, enabling caching makes the cost taxonomy wrong.** A hit costs nothing upstream,
but `_report_usage` would bill it as a fresh call — an error that *hides savings*, so nobody
notices.

Run-level counters follow the catalog spec's precedent (`…model-catalog-spec.md:309-311`): hits,
misses, and **bypasses by reason** — the load-bearing one, since it turns "I asked for caching
and got none" into an answerable question. **No metric may be labelled by cache key, prompt, or
credential.**

## 8. Security & correctness consequences

1. **Key scope.** `{v, account_id, profile_name, provider, model, prompt_hash}`
   (`aigateway/core/request_cache/keys.py:124-130`) — per account *and* profile. Two runs under
   different profiles never share an entry. url4 adds no new sharing axis.
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
   decision, not a bug. If it later needs undoing, the cheapest carve-out is engine-level — never
   cache within one run's own fan-out — which needs no protocol change, only a per-run nonce in
   the prompt normalisation. Not built now.
3. **`only-if-cached` rejected.** RFC 9111 requires `504` when nothing is cached. A url4 run is a
   fan-out of many calls; one uncached leaf failing the whole run is a footgun with no present
   use case.
4. **No new secret material.** The policy is non-sensitive; `X-AIGW-Cache-Key` is a hash prefix
   by construction.

## 9. Acceptance

1. **(r3)** A run declaring nothing sends `cache: {"use-cache": true}` and reports `miss` on
   first execution — **not** `bypass`. *(r2's "byte-identical body" criterion is void under
   D1=ON: the default request now carries a cache field. It survives only for a `no-store` run,
   item 2a.)*
2. `Cache-Control: no-store` reaches aigateway as `cache: {"no-store": true}` and reports
   `bypass`.
2a. A `no-store` run leaves no entry behind: an immediately following default run on the same
   prompt reports `miss`, not `hit`.
2b. `cache: {}` on the frame behaves **identically to declaring nothing** (§4.1) — the
   tri-state guard.
3. The same policy delivered on the attach frame produces the identical egress body.
4. Header and frame disagreeing → header applies, and a `LogEvent` records the override.
5. A re-attach with a different policy does **not** change the run, and warns.
6. A default run reports `miss` first, then `hit` on an identical immediate repeat.
7. Two runs under different `X-Profile` never share an entry.
8. A malformed directive is ignored; the run proceeds and is not 4xx'd.
9. Cache status/reason appear on spans for every case above.
10. A streaming turn reports `bypass` / `stream`, and no policy makes it cacheable.

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
