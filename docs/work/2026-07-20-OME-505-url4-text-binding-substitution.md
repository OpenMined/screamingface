---
ticket: OME-505
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-505 — Verify Text source bindings reach substitute_env_vars

## Intent

Close the one UNVERIFIED thread from the `OME-500` audit. The `$$` literal-dollar escape is
resolved at substitution time rather than lexing time; the audit confirmed it applies to
intent/context/path templates but did NOT confirm it applies to literal `Text` **source**
bindings. If some source path bypassed substitution, `$$` (and `$name` interpolation
generally) would behave differently depending on where a value landed — a silent, confusing
inconsistency.

## Finding — no defect

Traced statically and confirmed by execution: `compiler._lower_text` lowers EVERY `Text` node
to a `TextNode`, whose `resolve` calls `_substitute` → `substitute_env_vars`. `Binding` lowers
its value through the same registry (`_lower_binding` → `registry.lower(node.value)`), so a
named or colon-bound literal takes the identical path.

Probed six shapes, all correct:

| Expression | Result |
|---|---|
| `('$$literal')` | `$literal` |
| `('cost: $$5')` | `cost: $5` |
| `(x='$$lit', $x)` | `$lit` |
| `(name:'$$w', $name)` | `$w` |
| `('a $$b c')` | `a $b c` |
| `(/echo('$$x')!go)` | `'$x'` |

## Planned changes

- `packages/url4/tests/spec/test_grammar_conformance.py` — characterization tests pinning the
  invariant. NO production change.

## Test plan

- `$$` collapses in a bare `Text` source
- `$$` collapses inside a `name=` binding AND a `name:` descriptor (the sub-case the audit
  could not confirm)
- `$$5` does not decay into a positional `$5` lookup
- `$$` collapses inside a relative-expression context

## Acceptance

- [ ] Every `Text`-source → backend path enumerated and covered
- [ ] Tests pin the answer so a future lowering change cannot silently regress it
- [ ] `run_gates.py url4` green

## Outcome

- **Actual files:** `tests/spec/test_substitution_coverage.py` (NEW, 6 tests).
  **No production change** — the invariant already held.

- **Gates:** `run_gates.py url4` — ALL GREEN (841 tests, coverage >=95%)

- **Deviations:**
  1. **Tests landed in a NEW file, not appended to `test_grammar_conformance.py`.** The
     append-only gate flags ANY modification of a previously-committed test file, even a
     purely additive one (verified: 35 insertions, 0 deletions). Rather than ask for an
     exception to a gate I could simply satisfy, `OME-505` got its own file. One ticket,
     one test file — cleaner, and it keeps the gate's guarantee absolute.
  2. **No fix was needed.** The ticket was scoped as a verification spike and it verified
     clean. The value delivered is the pinning tests, not a behaviour change.
