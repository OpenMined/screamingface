---
ticket: OME-535
stack: url4
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-535 — ABNF conformance patch: resolve call-context source-lists caller-side

## Intent

CONFORMANCE PATCH (2 of 2) toward the external formal ABNF (owner-adopted
2026-07-21). `relative-expr-sugar = "/" path "(" source-list ")" intent-op
intent` (same for canonical and both remote forms): a call's parens carry a
SOURCE-LIST the engine must resolve before dispatch. The engine instead ships
the paren content as opaque text (`$var`-substituted only) — verified by
endpoint instrumentation: `/python(judged:/gemini(...)!'grade')!score.py`
hands the literal expression string to /python and the nested judge never
runs, silently neutering canonically-nested pipelines.

Decided semantics: at LOWERING time the context parses as a source-list and
lowers to `ctx:i` deps; resolve packs the resolved values per OME-534 rules
(named → `name: value`, weight-0.0 instrumental excluded) and dispatches the
packed context. A context that does NOT parse as a source-list (prose with a
`name: bare word` shape, unbalanced quotes) falls back verbatim to the raw
text path — prompts keep working. INVARIANT: resolution happens exactly once,
CALLER-side; `Url4Node._call_endpoint` keeps handing handlers opaque
pre-resolved context (re-resolving on receipt would double-resolve
engine-internal dispatches — the server AIDEV-NOTE's warning).

## Planned changes

- `src/url4/dag/compiler.py` — `_context_slots(context, registry)` (source-
  list parse with whole-context fallback-to-None on any ParseError);
  `_lower_rel_expr` / `_lower_remote_expr` wire `ctx:i` deps with outer-edge
  visibility; `_fold_intent_into_call` copies the new field.
- `src/url4/dag/nodes.py` — `RelUrlNode.ctx_slots` / `RemoteFetchNode.
  ctx_slots`; resolve packs gathered ctx slots (shared `_gather` with a key
  prefix) instead of `_substitute` when slots are present.
- `tests/spec/test_abnf_call_context.py` — NEW spec test file (RED first).
- Prior tests pinning raw-context delivery (`test_endpoint_dispatch_from_
  engine_internals` and any relying on literal-URL contexts) rewritten under
  the owner's sign-off; itemized below.

## Test plan

- named URI source in call parens resolves and packs labeled.
- nested call in context executes; receiver gets its resolved output.
- outer `$ref` bindings visible inside call contexts.
- instrumental (`:0:`) context member excluded from the packed context.
- prose context (no commas/colons-with-bare) unchanged verbatim; a context
  that fails source-list parsing falls back to raw text end-to-end.
- absolute URL in context is FETCHED (the decided behavioral flip).
- empty context unchanged; `$item` in call contexts inside map rows works.
- INVARIANT: single caller-side resolution — engine-internal endpoint
  dispatch still delivers opaque resolved text.

## Acceptance

- New spec tests green; full suite green; rewrites itemized.
- `run_gates.py url4` all green; OME-535 closed with sha + mirror.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, with ONE scope narrowing found during GREEN
  (below): `dag/compiler.py` (`_wire_context_slots` / `_context_slots` /
  `_build_ctx_nodes`, `_fold_intent_into_call` field carry),
  `dag/nodes.py` (`RelUrlNode.ctx_slots`, shared `_resolved_context`,
  `_gather` prefix param), `tests/spec/test_abnf_call_context.py` NEW
  (+9 tests).
- **Commits:** `76bd3c7` — feat(url4)!: caller-resolved call-context source-lists.
- **Gates:** ALL GREEN — ruff, format, pyright, pytest cov ≥95 (1073 passed).
- **Prior-test rewrites (itemized; owner sign-off this session):**
  - `unit/test_server.py` — `test_endpoint_dispatch_from_engine_internals` +
    `test_eval_path_accepts_standard_encoded_call_expression`: endpoint now
    receives the FETCHED content (`ARTICLE`), not the literal URL text.
  - `unit/test_characterization.py` — 3 bare-relexpr characterizations gain
    the context-source fetch preceding the dispatch.
  - `spec/test_substitution_coverage.py` — rel-expr `$$` pin: quotes are
    delimiters on resolved context slots (`'$x'` → `$x`).
  - `spec/test_abnf_contribution.py` (this epic's own U1 file) — fan-out
    sections show unquoted resolved context (`EP['a'|x]` → `EP[a|x]`).
- **Deviations (design refinements during GREEN):**
  1. REMOTE calls deliberately ship their context UNRESOLVED — the remote
     q= is an expression the REMOTE node evaluates (canonical
     `?q=expression`); caller-side resolution applies to RELATIVE calls
     only, where the caller IS the evaluating node. Surfaced by client
     remote tests attempting a real network fetch of a context URL.
  2. An `@`-bearing context always falls back to the raw-text path —
     preserves spec §5.6.3.1/.2 holdings pass-through (pinned by
     `test_holdings`); conservative by design.
