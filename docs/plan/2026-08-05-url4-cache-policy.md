---
title: url4 per-run cache policy — implementation plan
status: proposed — awaiting owner approval AND resolution of spec D1/D3/D4/D6
created: 2026-08-05
ticket: UNFILED — Linear MCP unauthenticated at authoring time
spec: docs/spec/2026-08-05-url4-cache-policy-spec.md
ledger: docs/work/2026-08-05-UNFILED-url4-cloud-cache-policy-spec.md
---

# Implementation plan — url4 per-run cache policy

## 0. What this plan assumes

The spec leaves **four decisions open**. This plan is written against the spec's
recommendations so it is reviewable as a whole; §9 states exactly what changes if you flip
each one. **The plumbing is ~90% identical under every combination** — only the marked steps move.

| decision | assumed here | if flipped |
|---|---|---|
| **D1** default | **OFF** — caller opts in | §9.1 — one default value + test matrix |
| **D3** frame shape | **extend `AttachData`** | §9.2 — Batch 1 and 4 grow a union member |
| **D4** precedence | **header wins, override logged** | §9.3 — one function in Batch 5 |
| **D6** header name | **`Cache-Control`** | §9.4 — one constant + parser |

Implementation starts only on explicit approval in plain words (CLAUDE.md rule 3).

## 0.1 Correction to spec §4.1 — surfaced while planning

The spec put `as_body_field()` — the `{"cache": {...}}` mapping to aigateway's vocabulary — on the
protocol `CachePolicy` in `packages/url4`.

**That is wrong and this plan does not do it.** `packages/url4` is the protocol and engine; it must
not know aigateway's request-body shape. CLAUDE.md's architecture rule is explicit — core defines
ports, adapters implement them, core never imports the adapter's concerns. `apps/url4-cloud` owns
the aigateway client (`runner/connector.py`) and is where the translation belongs.

So: **the protocol carries *intent*; url4-cloud translates intent → aigateway's body vocabulary.**
The two happen to use near-identical field names, which is convenient but must not become a
coupling. Spec needs an r3 amendment; noted rather than silently diverged.

## Stacks & gates

| stack | root | gate command | note |
|---|---|---|---|
| `url4` | `packages/url4` | `uv run .claude/scripts/run_gates.py url4` | **`--cov-fail-under=95`** — new code needs near-total coverage |
| `url4-cloud` | `apps/url4-cloud` | `uv run .claude/scripts/run_gates.py url4-cloud` | includes `check_layering.py` |

Both are Python → the `sdlc-python` loop: RED first, append-only tests, gates before commit.

---

## Batch 1 — protocol types (`packages/url4`, no behaviour)

**RED first.** Schema tests only; nothing consumes these yet.

- `protocol/signals.py`
  - `class CachePolicy(BaseModel)` — `use_cache`, `no_cache`, `no_store`, `s_maxage: int|None (ge=1)`.
    **No `as_body_field()`** (see §0.1).
  - `AttachData` gains `cache: CachePolicy | None = None`.
  - `SpanData` gains `cache_status: Literal["hit","miss","bypass"] | None` and
    `cache_reason: str | None`.
- `protocol/__init__.py` — export `CachePolicy`; extend `__all__`.

**Tests**
1. An attach frame **without** `cache` still validates — backward compatibility is the whole
   risk of touching a wire type.
2. `cache: null` and an absent key both parse to `None`, and `None` is distinguishable from
   `CachePolicy()`. **This distinction is load-bearing for D4** — "did not declare" must not
   collapse into "declared off".
3. Round-trip through `InboundFrameAdapter` preserves the policy.
4. `s_maxage=0` and negative values are rejected (`ge=1`).
5. `SpanData` without cache fields still validates.

**Gate:** `run_gates.py url4` green at ≥95% coverage.

---

## Batch 2 — the aigateway mapping (`apps/url4-cloud`, pure function)

- `url4_cloud/runner/cache.py` (new) — `policy_to_body_field(policy: CachePolicy | None) -> dict`.

**Tests**
1. `None` → `{}` — **the byte-identical-body guarantee**; a default run's payload must not change
   shape at all, or aigateway's `unsupported_fields` bypass path may trigger.
2. Each field maps to aigateway's spelling (`no_store` → `"no-store"`, `s_maxage` → `"s-maxage"`).
3. A policy with every field `False`/`None` still yields `{}`, not `{"cache": {}}`.

**Gate:** `run_gates.py url4-cloud`, including `check_layering.py` — this module must not be
imported by anything in `packages/url4`.

---

## Batch 3 — HTTP ingress (`apps/url4-cloud`)

- `url4_cloud/rest/cache_header.py` (new) — `parse_cache_control(raw: str|None) -> CachePolicy|None`.
- `rest/routes.py:337` — new `Annotated[str|None, Header(alias="Cache-Control")]` param on
  `start_run`, mirroring `x_profile` at `:347`.

**Tests**
1. `no-store` / `no-cache` / `max-age=60` / `url4-use-cache` each parse correctly.
2. Multiple directives in one header combine.
3. Absent header → `None` (not a default-constructed policy).
4. **Garbage is ignored, never 4xx** — matches `parse_cache_controls`' documented posture that
   malformed values parse as "not requested". A cache directive must never fail a run.
5. Unknown directives are dropped without affecting known ones.

---

## Batch 4 — WS ingress (`apps/url4-cloud`)

- `ws/bridge.py` — carry `AttachData.cache` into per-topic session state on attach.
- **First attach wins.** A re-attach with a *different* policy does not restate it; emits a
  `LogEvent` at `warn`.

**Tests**
1. Attach carrying a policy records it for the topic.
2. Attach without a policy records `None`.
3. Re-attach with a different policy leaves the recorded policy unchanged **and** logs.
4. Re-attach with an identical policy logs nothing (no warning noise on ordinary reconnect).
5. A run started before any attach is impossible — assert `_require_subscriber`
   (`rest/routes.py:363`) still guards it, so the ordering the design relies on is tested, not
   assumed.

---

## Batch 5 — convergence & precedence (D4)

- `rest/routes.py` — resolve `(header_policy, frame_policy)` → effective policy; pass to
  `_schedule` as one new kwarg beside `profile`/`identity`.

**Tests** — the full matrix:

| header | frame | effective | log |
|---|---|---|---|
| absent | absent | D1 default | — |
| set | absent | header | — |
| absent | set | frame | — |
| set | set, same | header | — |
| set | set, **differ** | **header** | **warn: override** |

---

## Batch 6 — threading & egress

- `job_env` / runner — thread as a **per-run** value, exactly as `profile` travels.
  **Not** on `AigatewayConfig`: that is world config shared by every run, and a per-run value
  placed there would leak across runs.
- `runner/connector.py:337` — `json={"model":…, "messages":…, **extra, **policy_to_body_field(policy)}`.

**Tests**
1. A run with no policy produces a body **byte-identical** to today's (assert on the exact dict).
2. A `no-store` run sends `cache: {"no-store": true}`.
3. Two concurrent runs with different policies do not contaminate each other — the regression
   `AigatewayConfig` placement would have caused.
4. The tool-calling loop (`connector.py:325-360`) applies the policy on **every** round trip, not
   just the first — a turn is several calls.

---

## Batch 7 — reading the answer back (D7, mandatory)

- `runner/connector.py` — read `X-AIGW-Cache`, `X-AIGW-Cache-Reason`, `X-AIGW-Cache-Key`; fold
  onto the owning span beside `_report_usage`, the seam `#506` used for `finish_reason`/`refusal`.

**Tests**
1. `hit` / `miss` / `bypass` each reach `SpanData.cache_status`.
2. The reason string is carried verbatim (`not_requested`, `disabled`, `stream`,
   `unsupported_fields`).
3. **Missing headers do not crash** — an older aigateway, or a non-cache error path, must degrade
   to `None`.
4. `X-AIGW-Cache-Key` is recorded only for hit/miss, and never any prompt content.

---

## Batch 8 — observability & docs

- Run-level counters: hits, misses, **bypasses by reason** (the load-bearing one — it makes
  "I asked for caching and got none" answerable). **No label may carry cache key, prompt or
  credential**, per the catalog spec's rule.
- `schemas/openapi.py` — document the request header.
- `schemas/asyncapi.py` — document the attach-frame field.
- `apps/url4-cloud/README.md` + `packages/url4` docs as needed.

---

## Verification

1. `run_gates.py url4` and `run_gates.py url4-cloud` both green.
2. **End-to-end against a local aigateway with `AIGATEWAY_REQUEST_CACHE_ENABLED=1`** (see Risk 1):
   - run with no policy → `bypass` / `not_requested`
   - opt-in run → `miss`, then an identical immediate repeat → `hit`
   - `no-store` run after a hit → `bypass`, and the stored entry is untouched
   - same policy via header and via frame → identical egress body
3. A streaming turn reports `bypass` / `stream` regardless of policy.
4. Spec §9 acceptance items 1-10 each map to a test above.

## Risks

1. **`request_cache_enabled` may be off in the deployed aigateway.** Then every path answers
   `bypass / disabled` and this is inert. **Confirm before Batch 1** — it decides whether this is
   worth building now.
2. **Touching a wire type.** `AttachData` is live protocol. Batch 1 test 1 (old frame still
   validates) is the guard; treat a failure there as a stop-the-line.
3. **`packages/url4` coverage gate is 95%.** Small additions with error branches can dip it;
   budget for exhaustive schema tests.
4. **Ensemble determinism** (spec §8.2) — if D1 flips to ON, two nodes sampling one model for
   variance may receive one answer twice. Not a plumbing risk; a thesis-level one.
5. **Two ingress paths, one policy.** Batch 5's matrix is the whole defence; do not ship Batch 3
   or 4 without it.

## Out of scope

- Per-node cache intent — needs url4 grammar, reopens doctrine fork **F4**.
- A url4-native / Enclave GET cache.
- Any `apps/aigateway` change.
- Extracting `url4_streaming_protocol` as its own package (spec open question 6).

## 9. What changes if a decision flips

### 9.1 D1 → default ON
Batch 6 supplies `use_cache=True` when no policy is declared; Batch 3/4 tests for "absent" invert
their expected effective policy. **No structural change.** Note this makes spec §8.2's determinism
risk live for every existing run.

### 9.2 D3 → `ConfigureEvent` instead of `AttachData.cache`
Batch 1 adds a new `ConfigureData` + `ConfigureEvent` and a third member to `InboundFrame`
(`unions.py:81`); Batch 4 handles a new inbound verb and must define what a `Configure` arriving
*after* run start means (recommend: ignored + warn, consistent with first-attach-wins). Batches
2, 5, 6, 7 unchanged.

### 9.3 D4 → frame wins, or fatal on conflict
One function in Batch 5 and its matrix row. If **fatal**, add a 409 path on the REST side and an
`ErrorEvent` on the WS side — the only variant that grows the error surface.

### 9.4 D6 → `URL4-Cache` instead of `Cache-Control`
Batch 3's header constant and parser grammar (a private header can use a simple JSON or
key=value form rather than RFC 9111 directives, and needs no `url4-use-cache` extension token).
Batches 1, 2, 4-8 unchanged.
