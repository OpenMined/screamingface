---
ticket: OME-504
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-504 — Character-class validation sweep

## Intent

The `OME-500` audit found the parser is a strict **superset** of the ABNF in a dozen places:
it validates *structure* (colon/semicolon boundaries) but never *character classes*, and
several identifier patterns use Python's `\w`, which is Unicode-aware where the ABNF means
ASCII `ALPHA`. None of this causes wrong behaviour today — it accepts input the grammar
rejects. This is hardening.

## Scope — what is IN

1. **ASCII anchoring.** `_IDENT_RE`, `_IDENTITY_NAME_RE`, `_VARREF_HEAD_RE`, `_FIELD_SEG_RE`
   (`grammar.py`) and `_PATH` / `_ENV_VAR_RE` (`ensemble.py`).
2. **`identity-name`** = `name-part / 1*DIGIT` — reject digit-led-then-alpha (`@9lives`).
3. **`identity-collection`** segments → the `path-segment` charset.
4. **`budget-key`** = `1*(ALPHA / "_")` — reject digits.
5. **`scalar-budget-value`** = `1*(ALPHA / DIGIT / "." / "-" / "_")`.
6. **`exec-key`** (extensible form) and **`exec-value`** charsets.
7. **`coord-key`** restricted to its closed 4-member enum.
8. **`structured-weight`** rejects nesting (flat `struct-pair` only).
9. **`quoted-char`** — escapes limited to `\'` and `\\`; reject raw control chars (`< %x20`).

## Scope — what is OUT, and why

- **`bare-value` charset** and **non-ASCII in `quoted-text`** — Tier-3 items. The ABNF is
  under-specified for natural-language content; tightening these would reject `'a b c'` and
  `'héllo 世界 🎉'` and break url4's actual purpose. Gated on `OME-503`. Item 10 above
  deliberately tightens ONLY escapes and control chars, NOT the non-ASCII bound.
- **`q=` ordering / mandatoriness** — deferred. The same `_dispatch` path serves plain data
  routes that legitimately have no `q=`, so "q= is mandatory and always last" is an
  architectural/wire-compatibility decision, not a charset fix. Needs its own ticket.
- **`param-key` / `param-value`** — MOVED OUT during implementation. `nested-param-value =
  param-value / processor-value`, and a `processor-value` may be a full expression starting
  with `(`, which can never satisfy `param-value`'s character class. Validating nested param
  values therefore requires knowing whether the key is `processor` — which lands in
  `OME-506`'s unimplemented §27.3. Validating only one of the two call sites would recreate
  the duplicated-rule defect `OME-501` just removed. Filed as `OME-507`.
- **`path` / `port` parse-time validation** — deferred. Real (and asymmetric: `render._check_path`
  enforces on output, so a leniently-parsed value can raise `RenderError` on re-render), but
  tightening the parse side risks rejecting paths that work today. Own ticket.

- **`exec-value` includes `:`** — pre-applies `OME-503` amendment A1. Without it, tightening
  `exec-value` would break `;iteration.slice=1:3`, which is spec-documented, implemented, and
  covered by the PASSING prior test `test_slice_parses`. The ABNF omitting `:` is the
  grammar's bug, not the code's.

## Planned changes

- `packages/url4/tests/spec/test_charclass_conformance.py` — NEW; RED tests
- `packages/url4/src/url4/grammar.py` — ASCII patterns, identity/budget/weight validation
- `packages/url4/src/url4/_annotations.py` — exec/coord key + value charsets
- `packages/url4/src/url4/ensemble.py` — ASCII patterns
- `packages/url4/src/url4/subrequest.py` — param-key/value charsets

## Test plan

Each item above: one rejection test (grammar-illegal input now raises `ParseError` with
`malformed_source`) plus one acceptance test (the legal neighbour still parses). Explicit
NON-regression tests that NL content still parses: `'a b c'`, `'héllo 世界 🎉'`,
`hello!world`, `;iteration.slice=1:3`.

## Acceptance

- [ ] Every in-scope production rejects its illegal inputs and accepts its legal ones
- [ ] NL content (bare values, non-ASCII quoted text) still parses — the Tier-3 exclusion holds
- [ ] Every prior test passes unmodified; `run_gates.py url4` green
- [ ] Deferred items recorded as follow-up tickets

## Outcome

- **Actual files:** `tests/spec/test_charclass_conformance.py` (NEW, 46 tests),
  `src/url4/grammar.py`, `src/url4/_annotations.py` (new `validate_exec_annotations`),
  `src/url4/ensemble.py`.

- **Gates:** `run_gates.py url4` — ALL GREEN (908 tests, coverage >=95%)

- **Deviations:**
  1. **`exec-value` must admit `:` AND `/`.** The ABNF's class cannot express two forms
     this codebase ships and tests: `;iteration.slice=1:3` needs `:` and
     `;accept=application/json` needs `/`. Found empirically by surveying real annotation
     values before tightening. **Both are grammar defects** — added to `OME-503`'s
     amendment list, which previously recorded only the `slice`/`:` case.
  2. **Exec validation runs from `grammar._attach_tail`, not `split_annotation_pairs`.**
     At split time the §8.1.2 boundary has not yet separated expression params from source
     annotations, and expression `param-key`s legally contain digits while exec-keys do
     not. Validating too early would reject legal expression params (`;mode2=x` as a
     protocol param). The validator therefore runs only on the resolved `source_ann`.
  3. **`param-key`/`param-value` moved OUT of scope** — see the Scope section; filed as
     `OME-507`.
  4. **`_parse_nested_struct_val` reordered** so well-formedness is checked BEFORE the depth
     rule. Making structured-weight flat-only surfaced the prior test
     `test_grammar.py::test_malformed_nested_struct_value_raises` reporting `(b:1)x` as
     "nested too deep" when it is simply malformed. Fixed in the CODE — the prior test
     passes unmodified.
  5. **A Unicode-named binding degrades to bare text rather than raising.** `articleé=…` is
     not the `name=value` sugar form once `name-part` is ASCII, so it falls through to
     `bare-value` — which is a deliberate Tier-3 exclusion. Correct outcome: the Unicode
     name simply never becomes an identifier.
