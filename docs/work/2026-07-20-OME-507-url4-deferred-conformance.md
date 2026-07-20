---
ticket: OME-507
stack: url4
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-507 — deferred conformance items (`q=` ordering, `path`/`port`, `param-key`/`param-value`)

## Intent

The three items split out of `OME-504` because each changes wire behaviour or
depended on an unresolved design question. `OME-506` (§27.3 delegation) has
landed, which unblocks item 3. Three focused cycles, one commit each.

## Owner decisions

1. **Valueless flag params stay** (`?stream&q=…`, `;meta=full;stream`). The
   grammar's `protocol-param` / `nested-query-param` / `expr-param` all require
   `key "=" value` and name only `broadcast` as a bare flag, but the owner ruled
   flags an accepted extension. Only the CHARSETS are enforced; a param with no
   `=` is left alone.
2. **Charsets are enforced on both sides, against the decoded value.** One
   validator, used by the grammar sites and by the HTTP ingress
   (`extract_expression_params`, which validates post-`unquote_plus` and raises
   → 400 `malformed_source`). A node then refuses over HTTP exactly what it
   refuses in text — the split-rule defect `OME-501` removed does not come back.

---

## Cycle 1 — `q=` is always last

`query-string = *( query-param "&" ) "q=" expression-body`.

**The mandatoriness question, resolved.** `q=` is mandatory *within this
production*, not for every URI a node serves. A plain data route carries no
`q=` because it is a different production — `relative-uri = "/" path-segment
*( "/" path-segment ) [ "?" query-tail ]`, whose `query-tail` is a loose
charset with no `q=` at all. So the two forms are distinguished by whether a
depth-0 `q=` is present, and data routes need no exemption:

| Query string | Production | Rule |
|---|---|---|
| `a=1&q=(x)!y` | `query-string` | `q=` present → must be LAST |
| `q=(x)!y&a=1` | — | REJECT: `q=` is not last |
| `a=1&b=2` | `query-tail` (data) | untouched |

The engine's own `encode_subrequest` already documents and emits `q` last, so
nothing url4 generates is affected — only hand-written or third-party queries.

**Site:** `subrequest.extract_expression_params` only — see deviation 1. The
grammar already enforces this by construction, so a second check there would
be dead code.

## Cycle 2 — `path` / `port` charsets

`path = segment *( "/" segment )`, `segment = *( ALPHA / DIGIT / "-" / "_" /
"." / "~" )`, `port = 1*DIGIT`.

The asymmetry `OME-504` recorded: `render._check_path` ALREADY enforces exactly
this segment charset on output, so `/foo$bar(x)!y` parses but cannot re-render
— a value that round-trips nowhere. Parse-side enforcement closes it.

**Scope boundary — the two path charsets are different productions:**

| Node | Production | Charset |
|---|---|---|
| `RelExpr` / `RemoteExpr` path | `path` / `segment` | NARROW — `ALPHA DIGIT - _ . ~` |
| `RelUrl` (data fetch) | `relative-uri` / `path-segment` | WIDE — adds `: @ ! $ & + =` |

So `/data/$topic` (a `RelUrl` with an embedded variable ref, used throughout
the suite) stays legal; only expression-bearing paths narrow. `_check_path` and
the new parse guard read from ONE shared pattern so they cannot drift.

**`host` is deliberately NOT validated:** `host = hostname / IPv4address` and
the grammar defines neither `hostname` nor `IPv4address` — inventing a charset
would be asserting a rule the spec does not state. `port = 1*DIGIT` IS defined
and is enforced. The existing `render._render_remoteexpr` authority guard stays
as-is.

## Cycle 3 — `param-key` / `param-value`

`param-key = 1*( ALPHA / DIGIT / "." / "_" )` (no `-`);
`param-value = 1*( ALPHA / DIGIT / "." / "-" / "_" / "," / ":" / "/" )`;
`nested-param-value = param-value / processor-value`.

**The `OME-506` unblock.** `nested-param-value` admits a `processor-value`,
which may be a full `expression-body` starting with `(` and can never satisfy
`param-value`'s charset. `url4.processor.classify_processor` now owns that
three-way split, so the validator dispatches on the key: `processor` → validate
as a `processor-value` (an expression form is parsed by `build`, an id/uri by
its own charset); every other key → `param-value`.

**Sites (one validator, `_annotations.validate_param` — the module already
owning `validate_exec_annotations`, and low enough that grammar, parser and
subrequest can all import it):** `extract_expression_params` (wire, decoded),
`grammar._decode_query_params` (nested rel/remote params), and
`parser.decode_envelope` (the `;` chain — `expr-param` uses the very same two
productions; see deviation 5 for why not `split_expr_params`).

## Planned changes

- `tests/spec/test_query_ordering.py`, `test_path_port_conformance.py`,
  `test_param_conformance.py` — NEW, one per cycle (separate files so the
  append-only gate stays green as each cycle commits)
- `src/url4/_annotations.py` — `validate_param` / `validate_params` + charsets
- `src/url4/subrequest.py` — `q`-last check, wire validation, flag encoding
- `src/url4/grammar.py` — path/port guards; `_decode_query_params` validation
- `src/url4/parser.py` — expression-param validation in `decode_envelope`
- `src/url4/render.py` — `_check_path` reads the shared pattern

## Acceptance

- [x] `q=` not last raises; `q=`-absent data queries unchanged
- [x] Expression paths narrow; `RelUrl` data paths (incl. `$ref`) unchanged; non-numeric port raises
- [x] `param-key`/`param-value` enforced at all three sites via one validator; `processor=` expression values still accepted
- [x] Valueless flags still parse (owner decision 1)
- [x] `run_gates.py url4` green; every cycle a separate commit

## Outcome

Three cycles, three commits, gates green at each.

| Cycle | Commit | New tests | Prior tests changed |
|---|---|---|---|
| 1 — `q=` last | `7aeee2c` | `test_query_ordering.py` (13) | 3 |
| 2 — path/port | `2def759` | `test_path_port_conformance.py` (26) | 0 |
| 3 — param charsets | `eca6164` | `test_param_conformance.py` (38) | 0 |

Suite 969 -> 1046.

- **Deviations:**
  1. **Cycle 1 needed no grammar change.** The grammar ALREADY implements
     "`q=` is last" by construction — `_parse_expr_canonical` takes everything
     after the `q=` body as the intent tail, so it rejects
     `/p?q=(a)!'go'&tone=formal` outright. Only the wire splitter tolerated it,
     and the two therefore disagreed: a node honoured over HTTP what it refused
     in text. The fix is one-sided, and that asymmetry is the whole
     justification — recorded because "enforce on both sides" was the plan.
  2. **`host` is not charset-checked.** `host = hostname / IPv4address`, and
     the grammar defines NEITHER. Validating would mean inventing a rule the
     spec does not state, so only `port = 1*DIGIT` is enforced. The same
     reasoning excluded `query-tail`, which depends on an undefined
     `unreserved`.
  3. **Quoted param values are an accepted extension** — not covered by the
     owner's flag ruling, decided here on the same grounds. `param-value` has
     no quoting form, so `?note='a&b'` is underivable; but quoting is the ONLY
     way to carry `&`, `(` or a space in a param, it is long-standing tested
     behaviour (`test_ampersand_inside_quotes_is_not_a_param_boundary`,
     `test_quoted_segment_skipped_when_scanning_relative_expression`), and
     removing it would leave no replacement. Checked on the key alone.
     **Owner: overrule this if quoted values should go.**
  4. **`encode_subrequest` gained a flag form.** It emitted a valueless param
     as `key=`, which the new decoder rejects (an empty value has no
     production). It now emits `key` bare, so encoder and decoder agree — found
     by `test_remote_broadcast_rides_as_param`, not by inspection.
  5. **Expression-chain validation runs on the RESOLVED params**, not inside
     `split_expr_params`: at split time `_split_source_side` has not yet
     decided which `;` pairs are expression-level and which belong to a bare
     source's exec chain (whose keys obey `OME-504`'s different rule). Same
     trap `OME-504` deviation 2 recorded.
