---
ticket: OME-508
stack: url4
status: in_progress
started: 2026-07-20
finished:
---

> **Cycle 2 (reopened 2026-07-20).** Cycle 1 enforced the intent on `expression`
> / `local-expr` / `iteration-expr` but left the OTHER two productions that
> carry `intent-op intent` untouched — so the ticket's own acceptance ("every
> surface entry") was not met. See "Cycle 2" below.

# OME-508 — mandatory `intent-op intent` on expression groups and iteration bodies

## Intent

The grammar gives `expression = "(" source-list ")" intent-op intent [ expr-params ]`
(and `local-expr` identically): `intent-op intent` is unbracketed, so a parenthesized
source group always carries an intent. `iteration-expr = collection-ref "*" expression`
takes a full expression after `*`. The engine currently accepts intent-less groups
("bare groups", `Expression(intent=None)`) and intent-less iteration bodies. Owner
ruling (2026-07-20): those forms are not legal — enforce.

## Owner decisions

1. **Fully strict on iteration bodies** (explicit choice over the exempting
   alternative): `src*(body)` without a trailing `!intent` raises; the cross-row
   shape must carry the per-row intent — `(src*(body)!peri)!reducer`.
2. **Fragment roots stay**: `build("https://x")` / `run("a=https://x")` — a lone
   non-parenthesized source is an API convenience, not a paren group; unchanged.
3. **DAG machinery untouched**: `Expression(intent=None)` remains the internal
   carrier for `paren-collection` and AST-path compilation; `GatherNode` /
   `MapNode` keep working. Enforcement lives at the parse/render/builder boundary.

## Design

Exempt positions (all grammar-derived): `paren-collection` — a `(…)` immediately
followed by `*(` (the grammar's own lookahead disambiguation); `structured-weight`;
`structured-budget-value`; `{struct-object}`.

Enforcement sites — the boundary, not the dataclass:

| Site | Rule |
|---|---|
| `parser.decode_envelope` | a parenthesized envelope with no `!intent` raises; an `IterationEnvelope` with no per-row intent raises. Single source of truth for BOTH `build()` and the DAG text path. |
| `grammar._parse_local_expr` | nested `(…)` in value position with nothing after the `)` raises (`missing_intent`). Iteration collections parse through a permissive path (`paren-collection` is legal). |
| `grammar._parse_iteration` | a body with no `!intent` after it raises. |
| `parser.assemble_expression` | parses the source side permissively (the envelope holds the intent externally); rejects only when the envelope carried none. |
| `render` | an intent-less `Expression` outside collection position, or an intent-less `Iteration`, raises `RenderError` (inverse stays faithful). Top-level composite sources no longer paren-wrap (the wrap would be a bare group); unfaithful cases raise via `_verify`. |
| `builders` | `expr()` and `iterate()` require an intent; `_shield_iterations` retired (its output `(iter)` is a bare group; the unrepresentable single-source aggregate case raises in the renderer instead). |

## Planned changes

- `packages/url4/tests/spec/test_mandatory_intent.py` — NEW; RED tests
- `packages/url4/src/url4/grammar.py` — `_parse_local_expr` / `_parse_iteration` enforcement + collection carve-out
- `packages/url4/src/url4/parser.py` — envelope enforcement, permissive internal group parse
- `packages/url4/src/url4/render.py` — inverse enforcement
- `packages/url4/src/url4/builders.py` — constructor validation, shield retirement
- `packages/url4/docs/spec/…v1-spec.md` §2.2 — bare-group row removed
- Prior tests asserting bare-group behavior: rewritten under the owner ruling
  (each one enumerated in the Outcome and the close comment — sanctioned
  prior-test changes, SDLC rule 5 confidence-gate resolved by the ruling)

## Test plan

- Reject: `build("(a,b)")`, nested `(a,(b,c),d)!x`, `run("(a,b)")` (DAG text path),
  `src*(body)` map-only, `(src*(body))!red` reducer-only, serve/spawn paths
- Accept (unchanged): `(a,b)!x`, `(a,b)!*x`, `(a,b)*('x')!i` paren-collection,
  `name:(m:0.9):src=…` struct weight, `budget=(scope:(d:5))`, `{a:1}`,
  wire `q=()!intent` reduce sub-request, fragment roots
- Builders/render: `expr(a,b)` raises; `iterate(coll, body)` without intent raises;
  `render(Expression(intent=None))` raises outside collection position
- Form-3 processor: all-bindings interpolation expression `(x='/gpt4')!'$x'`
  still resolves (the strict-legal replacement for the old bare-group form)

## Acceptance

- [ ] Every enforcement site rejects its illegal inputs with a clear ParseError/RenderError
- [ ] Every exempt position still parses byte-identically
- [ ] DAG execution of all still-legal forms unchanged; `run_gates.py url4` green
- [ ] Rewritten prior tests enumerated with the reason each had to change

## Outcome

- **Actual files (src):** as planned, plus three not anticipated:
  - `dag/compiler.py` — `compile_expression(bare_root_ok=)` threading +
    `_reject_bare_group` (see deviation 2)
  - `dag/executor.py` — the spawn boundary compiles with `bare_root_ok=True`
    (deviation 1)
  - `client.py` — the remote encoding moved to the passthrough group
    `(r=<call>)!'$r'` (deviation 3)
  - `processor.py` — Form-3 values are strict-validated via `build()` before
    spawning (deviation 4)
  - `nodes.py` / `dag/nodes.py` docstrings + spec §2.2 — bare-group rows removed
- **Tests:** `tests/spec/test_mandatory_intent.py` (NEW, 24) + 19 prior test
  files rewritten under the owner ruling — every rewrite is one of four moves:
  (a) rejection tests for the outlawed forms, (b) the binding-interpolation
  passthrough `(r=<call>)!'$r'` where the old bare wrap only grouped a call,
  (c) hand-built `Iteration`/`Expression` AST for DAG-machinery pins whose
  text form no longer exists (map-only iteration, gather-join), (d) goldens
  losing the top-level paren wrap. Suite 920 → 941, all green.
- **Gates:** ruff check · ruff format · pyright · pytest+coverage(≥95) ALL
  GREEN. **Append-only gate deliberately overridden** (`--skip-append-only`):
  the 19 modified prior test files ARE the ruling's consequence — the
  Confidence-Gate decision was taken explicitly by the owner ("bare groups
  are not legal"; iteration: "fully strict everywhere") before any edit.

- **Deviations:**
  1. **The spawn boundary compiles permissively.** The engine's own wrappers
     legally arrive intent-less — a map row's `(body)`, a deferred collection,
     a wire `(context)` whose intent travels separately. `decode_envelope`
     gained `require_intent` and only the executor's spawn passes False.
     Without this, every map row and context-only sub-request broke (caught
     by running the suite, exactly the "don't break the DAG" constraint).
  2. **Nested bare groups reject EAGERLY in the compiler.** `_slot_from_text`
     used to defer any `(…)` segment to a lazy thunk; deferral would have let
     a user's bare group slip through the now-permissive spawn. Rejecting at
     slot-build keeps build() and the DAG text path byte-identical in what
     they refuse.
  3. **Client remote encoding.** The old `(url4://node(ctx)!'i')` wrapper was
     itself a bare group. The conformant equivalent with identical wire
     behavior is the all-binding passthrough `(r=url4://node(ctx)!'i')!'$r'`
     — interpolation, no processor hop. `Url4Result.request` strings changed
     accordingly.
  4. **Form-3 `processor=` values validate strictly before spawn** — they are
     user surface (§27.3 expression-body) and must not ride the permissive
     internal boundary.
  5. **Top-level composite renders unwrapped.** `render(Binding(...))` emits
     the fragment root; shapes whose fragment form reparses differently
     (RelExpr/RemoteExpr with intent, annotated lone sources) now raise
     `RenderError` — the grammar genuinely has no faithful text for them.
  6. **`_shield_iterations` retired** — its output was a bare-group wrap; the
     unrepresentable single-source-aggregate case now raises in the renderer.
- **Follow-up observed (not in scope):** `/path(ctx)` and `url4://…(ctx)`
  WITHOUT `!intent` remain accepted as source values while the grammar's
  relative/remote sugar productions carry `intent-op intent`; same vein as
  the `OME-507` deferred items — candidate for that ticket's next pass.

---

# Cycle 2 — relative and remote expressions

## Intent

Four productions in the grammar carry `intent-op intent`. Cycle 1 enforced two
(`expression` / `local-expr`) plus `iteration-expr`. The remaining two were
missed:

```
relative-expr-canonical = "/" path "?" rel-query-params "q=" expression
relative-expr-sugar     = "/" path "(" source-list ")" intent-op intent [ expr-params ]
remote-expr-canonical   = "url4://" authority "/" path "?" rel-query-params "q=" expression
remote-expr-sugar       = "url4://" authority "/" path "(" source-list ")" intent-op intent [ expr-params ]
```

The sugar forms name `intent-op intent` directly; the canonical forms inherit it
by taking a full `expression` after `q=`. Verified missing: `(/path(ctx))!'x'`,
`(/path?q=(ctx))!'x'`, `(url4://h/v1(ctx))!'x'`, `(url4://h/v1?q=(ctx))!'x'`
all parse today.

## Design

`grammar._parse_expr_sugar` / `_parse_expr_canonical` raise `missing_intent`
when no `!intent` follows the context. The distinction that keeps this safe:

| Form | Production | Intent |
|---|---|---|
| `/path` (no parens, no `?q=`) | `relative-uri` | none — a DATA fetch, unchanged |
| `/path?a=1` | `relative-uri` + `query-tail` | none — data fetch with a query, unchanged |
| `/path(ctx)!i` | `relative-expr-sugar` | MANDATORY |
| `/path?a=1&q=(ctx)!i` | `relative-expr-canonical` | MANDATORY |

So `RelUrl` (data) is untouched; only `RelExpr`/`RemoteExpr` (expression-bearing)
gain the requirement. The engine's own context-only sub-request
(`encode_subrequest(path, ctx, intent=None)` → `/path?q=(ctx)`) is a WIRE
artifact decoded by `decode_subrequest`, never re-parsed by the grammar — it is
unaffected, and `test_relexpr_roundtrip["(/claude())!'Empty context call'"]`
pins the empty-CONTEXT (not empty-intent) shape, which stays legal.

## Planned changes

- `tests/spec/test_mandatory_intent.py` — appended: rel/remote RED tests
- `src/url4/grammar.py` — `_parse_expr_sugar` / `_parse_expr_canonical` enforcement
- `src/url4/render.py` — `_render_target_expr` rejects an intent-less RelExpr/RemoteExpr
- `src/url4/builders.py` — the rel/remote builders require an intent
- prior tests using intent-less rel/remote calls: rewritten

## Acceptance

- [x] All four rel/remote forms reject a missing intent, nested and top-level
- [x] `RelUrl` data fetches (`/path`, `/path?a=1`, `/data/$topic`) unchanged
- [x] The context-only WIRE sub-request still decodes and dispatches
- [x] `run_gates.py url4` green

## Outcome

- **Actual files:** `tests/spec/test_mandatory_intent_calls.py` (NEW, 28),
  `grammar.py` (`_parse_expr_intent`), `render.py` (`_render_target_expr`), and
  — not anticipated — `parser.py` (`_is_backend_call_tail`, see deviation 1).
- **Gates:** ALL GREEN. Suite 941 → 969.
- **Prior tests rewritten (9 files):** every one is the same idiom — a call
  that omitted its intent (`/solve($item.q)`, `/reduce(all)`, `/claude(ctx)`)
  now names one. Plus `test_value_detection.py::test_relative_expression_
  without_intent`, whose comment asserted the opposite rule ("§5.2 rule 2.2 —
  intent tail is optional"); it is now a rejection test.

- **Deviations:**
  1. **The envelope no longer hoists a lone call's intent** — the change this
     cycle turned on. `split_intent("/claude(ctx)!'sum'")` used to split at the
     depth-0 `!`, producing `RelExpr(intent=None)` + an expression-level intent.
     That tree is now underivable AND unrenderable, so the split had to go.
     `_is_backend_call_tail` was generalized from "a `!` right after `()`" to
     "a `!` closing a leading call token" (`/path(…)`, `url4://auth/path(…)`),
     which is what `grammar.parse` has always done with the same text.
     **This removes a real duplication:** `compiler._fold_intent_into_call`
     exists precisely to undo that disagreement between the text and AST paths;
     the two now agree at the parse layer. (The fold is still reached for the
     single-call GROUP shape and is left alone.)
  2. **`!*` on a call is left as-is.** `intent-op` admits `!*` in the call
     productions, but `RelExpr`/`RemoteExpr` carry no broadcast flag — folding
     it in would silently drop the semantics. The `*` keeps its existing
     reading as intent text; representing a broadcast call needs a node field.
     Recorded as a follow-up, not smuggled in here.
  3. **Empty source lists are still accepted** (`()!'x'`, `/p()!'i'`).
     `source-list = source *( "," source )` requires ≥ 1 source, so strictly
     these are underivable too — but that is a `source-list` cardinality rule,
     not the intent rule this ticket owns. Filed separately rather than
     widened into scope.
