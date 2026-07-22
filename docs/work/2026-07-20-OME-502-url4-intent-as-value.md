---
ticket: OME-502
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-502 — Honor `intent = value`

## Intent

`intent = value`: an intent may be any value form. `grammar.intent_atom` — the
single classifier for EVERY `!intent` position — recognises only four shapes (quoted → `Text`,
`scheme://` → `Url`, `/path` → `RelUrl`, else → `Text`), so nested expressions, struct
objects, self/identity refs and variable refs all collapse to `Text`.

**This is functional, not cosmetic.** `dag/compiler.py` dispatches lowering by node type, and
`_intent_from_ast` already falls through to `registry.lower(atom, edges)` for any non-`Text`
node — the lowering side is READY. Only the classification is narrow. The consequence is that
`(a,b)!(c,d)!agg` is never compiled into a nested subgraph; the text `"(c,d)!agg"` is handed to
the model as a literal prompt.

`$var` / struct / self-ref intents degrade *harmlessly* today (their proper lowering
re-renders to the same surface text), so the nested-expression case is the real loss and
drives the design.

## Design

Two sides must widen in lockstep, or round-tripping breaks:

1. `grammar.intent_atom` — add dispatch for the collapsed shapes: a depth-0 `*(` (iteration),
   `(`, `{`, `@`, `$`. **Preserve** quoted / `scheme://` / `/path` exactly as-is.
2. `render._render_intent` — currently hard-raises `RenderError` for anything but
   Text/Url/RelUrl. Delegate the widened kinds to the existing `_render_value` registry.

### Out of scope

`/path` intents keep classifying as `RelUrl`. The audit flagged only the four COLLAPSED
shapes; `/path → RelUrl` was recorded as existing, correct behaviour, and `!/reduce()` /
`!/score()` are the fan-out **reducer route** form, load-bearing in
`tests/unit/test_parser.py` and `tests/spec/test_iteration_spec.py`. Changing it would
rewire reduce dispatch and is not part of this unit.

## Planned changes

- `packages/url4/tests/spec/test_intent_as_value.py` — NEW; RED tests
- `packages/url4/src/url4/grammar.py` — widen `intent_atom`
- `packages/url4/src/url4/render.py` — widen `_render_intent`

## Test plan

- **The real defect:** a nested-expression intent COMPILES to a subgraph — assert the inner
  expression's sources are actually fetched, not just that the AST shape changed
- AST: `!(c,d)!agg` → `Expression`; `!$style` → `VarRef`; `!{a:'x'}` → `StructObject`;
  `!@` → `SelfRef`; `!@bob` → `IdentityRef`
- **Preservation:** `!summarize` → `Text`; `!'quoted'` → `Text`; `!https://x` → `Url`;
  `!/reduce()` → `RelUrl` (the deliberate non-change)
- **Round-trip:** `build(render(x))` stable for every new intent kind
- Regression: reduce-over-iteration and the `/score()` descriptor case still pass

## Acceptance

- [ ] A nested-expression intent compiles to a subgraph instead of prompt text
- [ ] All four collapsed shapes classify correctly
- [ ] `/path`, quoted, and `scheme://` intents unchanged
- [ ] Render round-trips every new kind
- [ ] Every prior test passes unmodified; `run_gates.py url4` green

## Outcome

- **Actual files:** as planned — `tests/spec/test_intent_as_value.py` (NEW, 21 tests),
  `src/url4/grammar.py` (`intent_atom` + new `_intent_value_or_text` helper),
  `src/url4/render.py` (`_render_intent`).

- **Gates:** `run_gates.py url4` — ALL GREEN (862 tests, coverage >=95%)

- **Deviations:**
  1. **`$ref` intents stay `Text` — the audit's premise was wrong.** The `OME-500` audit
     claimed `$var` intents "degrade harmlessly" because their proper lowering re-renders
     to the same text. Widening `$` proved that FALSE: it broke
     `test_execution.py::test_later_source_sees_earlier_binding`, which regressed to the
     literal string `$b`. A `Text` intent is substituted against the run scope by
     `TextNode._substitute`; a `VarRef` intent lowers to a node that does not resolve the
     same way. **`Text` IS the correct realization of a variable-ref intent**, not a
     degraded one. `$` is excluded from `_INTENT_VALUE_HEADS` with that rationale inline.
     Caught by a prior test during GREEN — no prior test was modified.
  2. **`render._render_intent` explicitly rejects `VarRef`.** Because `intent_atom` can
     never produce one, rendering it would emit `$a`, which reparses as `Text` — breaking
     render's inverse property. This keeps the prior
     `test_render.py::test_non_leaf_intent_raises` passing UNMODIFIED, and turns
     "render rejects what the parser cannot produce" into a stated invariant.
  3. **`/path` intents keep classifying as `RelUrl`** rather than as a relative
     expression, per the ledger's Design section — `!/reduce()` is the fan-out reducer
     route form. Out of scope for this unit.
  4. `intent_atom` split into two functions to satisfy ruff PLR0911 (max 3 returns).
