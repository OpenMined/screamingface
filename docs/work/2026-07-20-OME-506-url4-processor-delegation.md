---
ticket: OME-506
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-506 — `processor=` delegation (§27.3)

## Intent

`processor-param = "processor=" processor-value` selects which processor handles an intent.
It is expression-bearing: like `q=`, its value may be a full url4 expression. None of its
three value forms existed — the wire param was captured and dropped (`server.py`
`_TRANSPORT_PARAMS`, with a comment saying §27.3 was unimplemented), and `run(processor=…)` /
`ServeConfig.resolved_default_route` are an unrelated mechanism: a bare local route string
chosen at Python construction time, never sourced from a request.

## Owner decisions

1. **`processor-id` resolves against the node's registered endpoints.** No capabilities-document
   concept is invented. `Url4Node._endpoints` and `StaticIOLayer._routes` are already such a
   registry. Unknown id → `ResolutionError` listing the declared routes.
2. **The wire param is honored.** `Url4Node._dispatch_expression` reads `processor=` and threads
   it into the run, so a remote caller can select the processor.

## Design

**A new optional port** (hexagonal: core defines, adapters implement) —
`io_layer.SupportsProcessorRoutes.resolve_processor(processor_id) -> str | None`. Implemented by
`Url4Node` (against `_endpoints`) and `StaticIOLayer` (against `_routes`). Adapters without a
route registry simply don't implement it.

**One owner for §27.3 classification**, `url4/processor.py`:

| Value shape | Form | Dispatch |
|---|---|---|
| starts with `(` | 3 — expression | evaluate via `ctx.spawn`, re-classify the result ONCE |
| contains `://` | 2 — URI | absolute fetch; `kind` from the scheme |
| starts with `/` | — route path | relative fetch (**existing behaviour, preserved**) |
| otherwise | 1 — id | `resolve_processor` → route path → relative fetch |

The `/`-leading case is a deliberate fourth branch, not in the spec's 3-way split: the spec's
`processor-id` charset excludes `/`, and `default_route()` already returns paths. Keeping it
preserves every current `run(processor="/claude")` caller and every adapter that does not
implement the new port.

**Re-classification is single-pass.** A Form-3 expression resolving to another expression is
not re-evaluated — that would be unbounded.

## Planned changes

- `packages/url4/tests/spec/test_processor_delegation.py` — NEW; RED tests
- `packages/url4/src/url4/processor.py` — NEW; classification + resolution
- `packages/url4/src/url4/io_layer.py` — `SupportsProcessorRoutes`
- `packages/url4/src/url4/io_static.py` — `StaticIOLayer.resolve_processor`
- `packages/url4/src/url4/server.py` — `Url4Node.resolve_processor`; honor the wire param
- `packages/url4/src/url4/dag/nodes.py` — `FanoutReduceNode` dispatches via the resolver

## Test plan

- Form 1: `processor="claude"` → dispatches to the registered `/claude`
- Form 1 unknown: `processor="nope"` → `ResolutionError` naming the declared routes
- Form 2: `url4://node/p` and `https://host/p` → ABSOLUTE fetch, correct `kind`
- Form 3: an expression evaluating to a route → dispatches there
- Form 3 no recursion: a result that looks like an expression is not re-evaluated
- **Back-compat:** `processor="/claude"` unchanged; an adapter without the new port still works
- Wire: `GET /v1?processor=…&q=(…)!intent` honors it; `processor` is still not re-attached
  to the expression's `;` chain
- Unchanged: with no processor at all, the existing "no processor route" error still raises

## Acceptance

- [ ] All three value forms dispatch per the disambiguation rule
- [ ] Unknown id fails with a clear, route-listing error
- [ ] The wire param is honored end-to-end
- [ ] Existing `processor=` callers and registry-less adapters keep working
- [ ] Every prior test passes unmodified; `run_gates.py url4` green

## Outcome

- **Actual files:** as planned, plus two not anticipated:
  - `tests/spec/test_processor_delegation.py` (NEW, 12 tests)
  - `src/url4/processor.py` (NEW), `io_layer.py`, `io_static.py`, `server.py`, `dag/nodes.py`
  - **`dag/node.py`** — `BoundedIOLayer` must forward the new port (see deviation 1)
  - **`__init__.py`** — export `SupportsProcessorRoutes` alongside the other io ports

- **Gates:** `run_gates.py url4` — ALL GREEN (920 tests, coverage >=95%)

- **Deviations:**
  1. **`BoundedIOLayer` had to forward `processor_routes`.** `run()` wraps the adapter in
     `BoundedIOLayer` for the run-wide I/O cap, and that wrapper only re-exposes the ports it
     explicitly forwards. A `processor=` id therefore resolved against an EMPTY route list at
     execute time even though the adapter declared routes. Forwarded unbounded — declaring
     routes is not I/O. Caught by the RED tests; would have been invisible in a unit test that
     called the resolver directly.
  2. **The port declares routes; the core matches them.** The first sketch had each adapter
     implement `resolve_processor(id)`. Moved to `processor_routes()` + one matching rule in
     `url4/processor.py`, so the id-resolution semantics have a single definition rather than
     one per adapter.
  3. **A fourth classification branch.** The spec's rule is three-way; a `/`-leading value is
     handled as a route path before the id branch. `processor-id` cannot contain `/` and
     `default_route()` returns paths, so this preserves every existing
     `run(processor="/claude")` caller and every adapter with no route registry.
  4. **Form-3 re-classification is single-pass**, and an expression resolving to another
     expression raises rather than recursing.
