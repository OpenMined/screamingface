---
ticket: OME-501
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-501 — Fix silent mis-parses from duplicated productions

## Intent

Three grammar-conformance bugs found by the `OME-500` audit share one root cause: a
production is implemented or enforced in **two places, and only one copy is correct**. These
need no ABNF ruling — the codebase already demonstrates the right behaviour in its own
sibling implementation, so the fix is to collapse each pair onto a single source of truth.

All three fail **silently**: no error is raised, a structurally wrong AST is produced (A, B)
or a transport-only parameter escapes to the network (C).

## The three bugs

**A — `build()` destroys intent-bearing collections.** `parser.py:decode_envelope` runs
`split_intent` on the first depth-0 `!` before `split_collection_iteration` scans for `*(`,
so the collection's own intent `!` is consumed as the outer envelope's intent.

```
grammar.parse_value("(a)!y*('b')!x") -> Iteration(collection=Expression(intent=Text('y')), …)  # correct
parser.build("(a)!y*('b')!x")        -> Expression(sources=(Text('a'),), intent=Text("y*('b')!x"))  # WRONG
```

Affects the public parse entry point AND `dag/compiler.py` (both call `decode_envelope`),
i.e. the eager tree and the lazy DAG. Hits 3 of 6 `uri-collection-ref` alternatives.

**B — nested query-param split is not paren-depth aware.** `grammar.py:_decode_query_params`
/ `_find_expression_param` use `_find_unquoted` (quotes only). `subrequest.py:extract_expression_params`
solves the identical production correctly via `_scan.split_top_level`, and is already covered
by `tests/unit/test_scan.py::test_extract_splits_on_depth_zero_ampersand_only`. The grammar
path simply does not reuse it.

**C — `resume`/`rid` leak from expression text.** `_TRANSPORT_PARAMS` is applied only in
`server.py:_reassemble` (HTTP ingress). Params written in url4 expression text flow
parse → `dag/compiler.py:_lower_rel_expr` → `dag/nodes.py:_wire_params` → `encode_subrequest`
unfiltered, reaching the outbound sub-request.

## Planned changes

- `packages/url4/tests/spec/test_grammar_conformance.py` — NEW; RED tests for A, B, C
- `packages/url4/src/url4/parser.py` — reorder `decode_envelope` so `*(` detection precedes
  intent splitting (A)
- `packages/url4/src/url4/grammar.py` — `_decode_query_params` / `_find_expression_param`
  delegate to the depth-aware scanner (B)
- `packages/url4/src/url4/subrequest.py` — host the single shared transport-param filter (C)
- `packages/url4/src/url4/server.py` — `_reassemble` consumes the shared filter (C)
- `packages/url4/src/url4/dag/nodes.py` — `_wire_params` applies the shared filter (C)

Exact placement for C's shared filter is a DESIGN-step decision; the constraint is that it
must have exactly one definition.

## Test plan

RED first, each pinning the currently-wrong behaviour:

- **A happy:** `build("(a)!y*('b')!x")` equals `grammar.parse_value(...)` — an `Iteration`
- **A matrix:** all 6 `uri-collection-ref` shapes agree between `build()` and `parse_value()`
- **A boundary:** `a*b` (no `(`) stays literal `Text`; `()*('x')!y` empty collection preserved
- **A regression:** existing reduce-over-iteration + `_is_descriptored` precedence unchanged
- **B happy:** nested `processor=` with an inner `&` inside parens parses without garbling
- **B boundary:** `&` inside quotes still not a split point
- **C invariant:** `resume`/`rid` written in expression text never reach the outbound query
- **C boundary:** non-transport params in expression text DO survive (no over-filtering)

## Acceptance

- [ ] `build()` and `grammar.parse_value()` agree for all 6 `uri-collection-ref` shapes
- [ ] Nested query-param parsing has ONE depth-aware implementation, not two
- [ ] Transport-param filtering has ONE definition, applied to both ingress and expression text
- [ ] Every prior test still passes, unmodified (rule 5)
- [ ] `run_gates.py url4` green, coverage ≥95%

## Outcome

- **Actual files:** as planned, with one addition and one change of approach:
  - `tests/spec/test_grammar_conformance.py` — NEW, 23 tests
  - `src/url4/parser.py` — new `_split_at_iteration_body` helper; `decode_envelope`
    binds a depth-0 `*(body)` BEFORE the `!intent` split (A)
  - `src/url4/grammar.py` — `_find_expression_param` + `_decode_query_params` now
    depth-aware via `iter_top_level` / `split_top_level` (B)
  - `src/url4/subrequest.py` — hosts `TRANSPORT_ONLY_PARAMS` + `strip_transport_params` (C)
  - `src/url4/dag/nodes.py` — `_wire_params` applies the shared filter (C)
  - `src/url4/server.py` — `_TRANSPORT_PARAMS` DERIVED from the shared rule (C)

- **Commits:** `f6a3ca6` — fix(url4): collapse three duplicated productions onto one source of truth

- **Gates:** `run_gates.py url4` — ALL GREEN. append-only test check ✓ · ruff check ✓ ·
  ruff format ✓ · pyright ✓ · pytest 835 passed, coverage ≥95% ✓

- **Deviations:**
  1. **Fix A implemented in `decode_envelope`, not `split_intent`.** Adding an offset
     parameter to `split_intent` would have touched 13 call sites for a bug local to the
     envelope decode. Confining the ordering rule to `decode_envelope` keeps the blast
     radius at one function and preserves it as the documented single source of ordering
     truth.
  2. **`server._TRANSPORT_PARAMS` kept broader than the spec's transport-only set.** The
     ingress set also drops `delivery`/`cb`/`meta`/`v`/`processor`. Rather than force both
     sites onto one identical set (which would have changed ingress behaviour), the ingress
     set is now DERIVED as a superset of `TRANSPORT_ONLY_PARAMS`. Verified the resulting
     frozenset is byte-identical to the pre-change one, so `OME-501` changes no server
     behaviour — only where the §11.6.3 rule is defined.
  3. **Bug C's first test draft failed for the wrong reason** (a fan-out reduce with no
     processor route). Rewritten reduce-free so it isolates the outbound query string.
     Caught during RED, before any production code was written.

- **Follow-on filed:** none new. `OME-506` already records that `processor=` delegation is
  unimplemented, which is why `processor` stays in the ingress drop set.

- **Status:** DONE
