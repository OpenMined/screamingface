---
ticket: OME-507
stack: url4
status: in_progress
started: 2026-07-20
finished:
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

**Sites:** `subrequest.extract_expression_params` (wire) and
`grammar._find_expression_param` (expression text) — the same depth-0 scan
both already run; each gains the "nothing follows the q segment" check via one
shared helper.

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

**Sites (one validator, `subrequest.validate_param`):**
`extract_expression_params` (wire, decoded), `grammar._decode_query_params`
(nested rel/remote params), and `parser.split_expr_params` (the `;` chain —
`expr-param` uses the very same two productions).

## Planned changes

- `tests/spec/test_query_conformance.py` — NEW; RED tests for all three cycles
- `src/url4/subrequest.py` — `validate_param`, `q`-last check, charset patterns
- `src/url4/grammar.py` — path/port guards; `_decode_query_params` validation
- `src/url4/parser.py` — `split_expr_params` validation
- `src/url4/render.py` — `_check_path` reads the shared pattern

## Acceptance

- [ ] `q=` not last raises; `q=`-absent data queries unchanged
- [ ] Expression paths narrow; `RelUrl` data paths (incl. `$ref`) unchanged; non-numeric port raises
- [ ] `param-key`/`param-value` enforced at all three sites via one validator; `processor=` expression values still accepted
- [ ] Valueless flags still parse (owner decision 1)
- [ ] `run_gates.py url4` green; every cycle a separate commit

## Outcome

(pending)
