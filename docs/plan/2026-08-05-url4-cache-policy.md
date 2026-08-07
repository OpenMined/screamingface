---
title: url4 per-run cache policy — implementation plan
status: proposed — **all spec decisions locked**; awaiting approval to implement
created: 2026-08-05
revised: 2026-08-05 (r6 — D3/D4/D6/D11 locked; §9 removed, nothing left to flip)
ticket: UNFILED — Linear MCP unauthenticated at authoring time
spec: docs/spec/2026-08-05-url4-cache-policy-spec.md
ledger: docs/work/2026-08-05-UNFILED-url4-cloud-cache-policy-spec.md
---

# Implementation plan — url4 per-run cache policy

> **r4 is a clean rewrite.** r1–r3 accumulated patches as the design moved (url4-cloud REST →
> `packages/url4` protocol; cache OFF → ON; aigateway chart in scope → deleted). Those turns live
> in the spec's revision table and the ledger; this document describes only the work as it now
> stands.

## 1. What this builds

A caller can declare that one url4 run must **not** participate in aigateway's global response
cache. Caching is otherwise **on**, because aigateway v2 makes it on.

Two carriers, one meaning:

```
Cache-Control: no-store              (HTTP, on GET /)
{"cache": {"participate": false}}    (WS attach frame)
```

## 2. The upstream this depends on

**aigateway PR #507 (`OME-305`) — MERGED 2026-08-06 as `4f2a55ea`.** It replaces the v1 per-account cache
with one **global, never-expiring, ON-by-default** cache whose control grammar is **closed to a
single field, `use-cache`**.

Three consequences that shape every batch below:

1. **url4 may send only `use-cache`.** Under v2 an unrecognised control key does not degrade to
   "ignored" — it makes the request **bypass** (`global_controls.py`), even alongside a valid
   `use-cache: true`. A well-meant `no-store` or `ttl` would silently cost every cache hit.
2. **Absent, `null` and `{}` all mean participate.** So the default run sends **no `cache` field
   at all** — the smallest body, and the least exposed to the closed-grammar bypass.
3. **No aigateway work.** #507 ships its own chart (`requestCache.enabled` — `false` in
   `values.yaml`, `true` in `values-prod.yaml`). url4 depends on it landing; it does not touch it.

**This work is unobservable until #507 lands.** A green url4 suite is not evidence the cache works
end to end — see Verification step 3.

## 3. Decisions

**Locked:** cache ON by default · protocol types in `packages/url4` · both carriers · per-run
scope · response headers folded onto spans · no aigateway change.

**All locked** (spec r7):

| | decision | value |
|---|---|---|
| **D3** | frame shape | extend `AttachData` — no new inbound verb |
| **D4** | precedence | **header wins**, override emits a `LogEvent` at `warn` |
| **D6** | header name | standard **`Cache-Control`**; intermediaries may participate |
| **D11** | `max-age` | **honour it** — blocked upstream today, so it degrades to opt-out (§6) |

Implementation starts only on explicit approval in plain words (CLAUDE.md rule 3).

## 4. One architectural note

The spec's protocol type carries **intent only** — `participate: bool | None`. The translation to
aigateway's wire vocabulary (`{"cache": {"use-cache": false}}`) lives in `apps/url4-cloud`.

`packages/url4` is the protocol and engine and must not know an adapter's request-body shape;
CLAUDE.md's architecture rule is explicit. The two vocabularies are nearly identical, which is
convenient and must not become a coupling — a change to aigateway's body shape must never edit a
file that ships to SDK users.

## 5. Stacks & gates

| stack | root | gate | note |
|---|---|---|---|
| `url4` | `packages/url4` | `run_gates.py url4` | **`--cov-fail-under=95`** |
| `url4-cloud` | `apps/url4-cloud` | `run_gates.py url4-cloud` | includes `check_layering.py` |

Both Python → the `sdlc-python` loop: RED first, append-only tests, gates before commit.

---

## Batch 1 — protocol types (`packages/url4`)

No behaviour; schema only.

- `protocol/signals.py`
  - `class CachePolicy(BaseModel)` — **exactly one field**, `participate: bool | None = None`,
    with `model_config = ConfigDict(extra="forbid")`.
  - `AttachData` gains `cache: CachePolicy | None = None`.
  - `SpanData` gains `cache_status: Literal["hit","miss","bypass"] | None` and
    `cache_reason: str | None`.
- `protocol/__init__.py` — export `CachePolicy`, extend `__all__`.

**Tests**

1. An attach frame **without** `cache` still validates — backward compatibility is the whole risk
   of touching a live wire type. Treat a failure here as stop-the-line.
2. Absent, `null` and `{}` all parse such that "not stated" is distinguishable from an explicit
   `participate=False`. Collapsing them makes opt-out unexpressible and breaks D4.
3. Round-trip through `InboundFrameAdapter` preserves the policy.
4. **Unknown fields are rejected** (`extra="forbid"`). A caller inventing `no_store` fails loudly
   at the url4 edge instead of having it forwarded to a grammar that bypasses on it.
5. `SpanData` without cache fields still validates.

**Gate:** `run_gates.py url4` green at ≥95% coverage.

---

## Batch 2 — the aigateway mapping (`apps/url4-cloud`)

- `url4_cloud/runner/cache.py` (new) — `policy_to_body_field(policy: CachePolicy) -> dict`.

Takes a **resolved** policy, never `None`: the default is applied once at convergence (Batch 5),
so this stays a dumb translation and the policy decision lives in exactly one place.

**Tests**

1. `participate=True` → **`{}`**. The field is *omitted*, not sent as `{"use-cache": true}`.
2. `participate=False` → `{"cache": {"use-cache": false}}`.
3. **Property: `set(out.get("cache", {})) <= {"use-cache"}` for every input.** The single most
   important guard in this plan — any extra key silently costs every cache hit, with no error
   anywhere.

**Gate:** `run_gates.py url4-cloud`, including `check_layering.py` — this module must not be
importable from `packages/url4`.

---

## Batch 3 — HTTP ingress (`apps/url4-cloud`)

- `url4_cloud/rest/cache_header.py` (new) —
  `parse_cache_control(raw: str | None) -> CachePolicy | None`.
- `rest/routes.py:337` — new `Annotated[str | None, Header(alias="Cache-Control")]` on
  `start_run`, mirroring `x_profile` at `:347`.

Every directive collapses to participate / opt-out **at this edge**; none is forwarded verbatim.

| directive | → |
|---|---|
| absent | `None` — not stated |
| `no-store`, `no-cache` | `participate=False` |
| **`max-age=<n>`** | **`participate=True, max_age=n`** — parsed and **preserved**, not collapsed (D11, §6) |
| `url4-use-cache` | `participate=True` |

`CachePolicy` therefore carries a second field, `max_age: int | None`, which is **url4-internal
and never sent to aigateway** — v2's closed grammar rejects it (`global_controls.py:79-83`).
Batch 7 is where it is applied.

**Tests**

1. Each row above.
2. Multiple directives in one header combine; conflicting ones resolve to opt-out (the safe side).
3. Absent header → `None`, not a default-constructed policy.
4. **Garbage is ignored, never 4xx.** A cache directive must never fail a run.
5. Unknown directives are dropped without affecting known ones.

---

## Batch 4 — WS ingress (`apps/url4-cloud`)

- `ws/bridge.py` — carry `AttachData.cache` into per-topic session state on attach.
- **First attach wins.** A re-attach with a different policy does not restate it; emits a
  `LogEvent` at `warn`.

**Tests**

1. Attach carrying a policy records it for the topic.
2. Attach without a policy records `None`.
3. Re-attach with a *different* policy leaves the recorded policy unchanged **and** logs.
4. Re-attach with an *identical* policy logs nothing — no warning noise on ordinary reconnect.
5. `_require_subscriber` (`rest/routes.py:363`) still guards run start, so the attach-before-run
   ordering this design relies on is tested rather than assumed.

---

## Batch 5 — convergence & precedence

- `rest/routes.py` — resolve `(header_policy, frame_policy)` → effective policy; pass to
  `_schedule` as one new kwarg beside `profile` / `identity`.

| header | frame | effective | log |
|---|---|---|---|
| absent | absent | `participate=True` — the default, applied **here and nowhere else** | — |
| set | absent | header | — |
| absent | set | frame | — |
| set | set, same | header | — |
| set | set, **differ** | **header** | **warn: override** |

---

## Batch 6 — threading & egress

- `job_env` / runner — thread as a **per-run** value, exactly as `profile` travels. **Not** on
  `AigatewayConfig`: that is world config shared by every run, and a per-run value there leaks
  across runs.
- `runner/connector.py:337` —
  `json={"model": …, "messages": …, **extra, **policy_to_body_field(policy)}`.

**Tests**

1. A default run's body is **byte-identical to today's** — no `cache` field, which under v2 *is*
   participation.
2. An opted-out run sends `cache: {"use-cache": false}` and nothing else.
3. Two concurrent runs with different policies do not contaminate each other — the regression an
   `AigatewayConfig` placement would cause.
4. The tool-calling loop (`connector.py:325-360`) applies the policy on **every** round trip. One
   turn is several calls, and a policy that lapsed after the first would be worse than none.

---

## Batch 7 — reading the answer back

- `runner/connector.py` — read the cache outcome and fold it onto the owning span beside
  `_report_usage`, the seam `#506` used for `finish_reason` / `refusal`.

**Prefer the standard, fall back to the ad hoc (spec §2.2, §7):**

1. **`Cache-Status`** (RFC 9211) if present — parse as an RFC 8941 Structured Field **List** and
   select the **aigateway member**, not blindly the first: the list may carry one entry per cache
   that touched the response (aigateway, Envoy, a CDN), ordered origin-closest first.
   `hit` → `hit`; `fwd=<token>` → `miss`/`bypass` with the token as reason; `key=`; `detail=`.
2. Else the `X-AIGW-Cache` / `-Reason` / `-Key` triple, verbatim.

Costs nothing now and means url4 needs no change the day aigateway adopts the standard.

Without this, a hit costs nothing upstream but `_report_usage` bills it as a fresh call — an error
that **hides savings**, so nobody reports it.

**Tests**

1. `hit` / `miss` / `bypass` each reach `SpanData.cache_status`, from **either** source.
2. Reason carried verbatim, including v2's vocabulary: `opted_out`, `malformed_controls`,
   `unsupported_control`, `disabled`.
2a. **`Cache-Status` wins when both are present**, and a multi-member list selects the aigateway
   member rather than the first — the test that stops an Envoy or CDN entry being misread as
   aigateway's answer.
2b. A malformed `Cache-Status` falls back to the `X-AIGW-*` triple rather than losing the signal.
2c. **`max_age` with no age reported → the run opts out** (`bypass`/`opted_out`), never a silent
   stale serve. This is the D11-inert path and is the behaviour that actually ships.
2d. **`max_age` with an age reported → honoured**: within bound is a legitimate `hit`; beyond
   bound triggers the opt-out re-issue. Written now, dormant until aigateway reports age.
3. **Missing headers degrade to `None`, never crash** — an older gateway, or a non-cache error
   path.
4. `X-AIGW-Cache-Key` recorded only for hit/miss; never any prompt content.

---

## Batch 8 — observability & docs

- Run-level counters: hits, misses, **bypasses by reason** — the load-bearing one, since it turns
  "I asked for no caching and something still cached" into an answerable question.
- **No metric labelled by cache key, prompt or credential.**
- `schemas/openapi.py` — document the request header.
- `schemas/asyncapi.py` — document the attach-frame field.
- `apps/url4-cloud/README.md`; `packages/url4` docs as needed.

---

## 6. D11 — honouring `max-age`, and why it is inert today

The decision is to honour it. Two upstream blockers stand in the way, both verified on #507's
branch:

1. **url4 cannot ask for a bound.** `{"cache": {"max-age": 60}}` returns
   `_refuse(BYPASS_UNSUPPORTED_CONTROL)` — v2's grammar is closed to `use-cache`.
2. **aigateway does not report age.** No `Age`, no `Cache-Status; ttl=`.

So url4 can neither request a freshness bound nor measure one, and `max-age` **degrades to
opt-out** until one changes — observably, via `bypass` / `opted_out`.

**This plan builds the degraded behaviour and keeps the value.** Batch 3 parses and preserves
`max_age`; Batch 7 applies it when an age is available and opts out when it is not. The day
either blocker lifts, the change is a branch in Batch 7 — not a redesign.

Preferred fix is upstream (aigateway accepts a bound); raised on #507. The client-side
alternative — participate, read `Age`, re-issue with `use-cache: false` if too old — is
buildable by url4 alone once `Age` exists, at the cost of one extra round trip on a stale hit
and a discarded body, multiplied across a fan-out.

## Verification

1. `run_gates.py url4` and `run_gates.py url4-cloud` both green.
2. Batch 2's property test passes — `cache` never carries a key other than `use-cache`.
3. **End-to-end against a local aigateway built from `origin/main`** (#507 having merged), with
   `AIGW_REQUEST_CACHE_ENABLED=true`:
   - default run → participates; `miss`, then `hit` on an identical repeat
   - `Cache-Control: no-store` → `bypass` with reason **`opted_out`** (not `unsupported_control`
     — that distinction is the whole point of collapsing at the url4 edge)
   - `max-age=60` behaves as `no-store` (D11)
   - the same policy via header and via frame produces an identical egress body
4. A streaming turn reports `bypass` regardless of policy.
5. Spec §9 acceptance items each map to a test above.

## Risks

1. ~~**#507 is WIP.** Its control grammar could still change~~ — **RETIRED 2026-08-07.** #507
   merged as `4f2a55ea` and `global_controls.py` was re-read on `origin/main`: the grammar is
   byte-equivalent to what this plan was written against, the sole change being a rename url4
   never referenced (`LEGACY_CONTROL_FIELDS` → `UNSUPPORTED_CONTROL_FIELDS`). The mapping stands.
2. **Touching a live wire type.** `AttachData` is protocol. Batch 1 test 1 is the guard.
3. **`packages/url4` coverage gate is 95%**; small additions with error branches can dip it.
4. **The closed grammar is a silent failure mode.** An extra control key costs every hit and
   raises nothing. Batch 2 test 3 exists solely for this, and it should be treated as a
   correctness test, not a style one.
5. **Ensemble determinism** — accepted by the owner, but v2 widens it: the collapsing repeat need
   not share an account, a run or a day. Flagged in spec §8.2 for re-confirmation. Not a plumbing
   risk; a thesis-level one.

## Out of scope

- Per-node cache intent — needs url4 grammar, reopens doctrine fork **F4**.
- A url4-native / Enclave GET cache.
- Any `apps/aigateway` change — #507 owns it.
- Extracting `url4_streaming_protocol` as its own package (spec open question 4).
