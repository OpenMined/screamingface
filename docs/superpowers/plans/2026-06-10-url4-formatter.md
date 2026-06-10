# Plan: url4 pretty-formatter (Format button)

**Status:** plan for review (not ticketed/implemented)
**Confidence:** ~92% (one architecture choice + the string-wrap policy to confirm)
**Owners to loop in:** Kevin (url4 grammar / ensemble parsing internals)

## Goal
A one-press **Format** that rewrites a url4 expression into a canonical, readable layout:
- `()` groups nest at **2-space** indent; closing `)` unindents.
- `!<intent>` starts on a **new line** at the parent indent.
- `;foreach.*` directives each on their **own line** at the group's indent.
- `{...}` json-blob intents → **pretty-printed JSON** (indented).
- weights/names (`claude:0.40:/claude(...)`) and `,`-separated list items laid out one-per-line at the current indent.
- Monaco tab for `url4` = **2 spaces**.
- long strings: **soft-wrap only** (see caveat) — do not insert real newlines into `'…'`.

## The hard architectural fact (drives everything)
`/ensemble` parses an ensemble expression in **layers**, not via one grammar (`ensemble.py:118-168`):
1. `split_intent(expr)` → `(source_expr, raw_intent, broadcast)` (`decoder.py`)
2. `split_foreach_annotations(source_expr)` → `(clean, ForeachDirectives)` — strips `;foreach.concurrency=…`, `;foreach.on_error=…`
3. `split_collection_iteration(source_expr)` → `(collection_source, iteration_body)` for `SOURCE*(BODY)`
4. only the **leaf** pieces go through the base TatSu `parse()` (`url4_grammar.py:275`, AST in `url4_ast.py`)

The base grammar (`url4_grammar.py`) has **no `;foreach`/fan-out productions** — calling `parse()` on a full ensemble spec fails (this is the SF-251 `/ensemble/highlight` gap). 

**Therefore the formatter must reuse the interpreter's decomposition functions** (`split_intent`, `split_foreach_annotations`, `split_collection_iteration`, `parse`) and mirror its recursion — *not* just call `parse()`. Doing so makes the formatter handle exactly the specs that matter (MainOne, ScoredLiveTruth) and **sidesteps SF-251** (we never feed the base grammar the ensemble envelope).

## Design

### Server (`apps/server`, `url4_executor` plugin)
New module `formatter.py` — `format_url4(expr: str) -> str`:

A recursive pretty-printer that mirrors `EnsembleInterpreter.evaluate`'s structure:
```
format(expr, indent):
  expr = expr.strip()
  body, directives = split_foreach_annotations(expr)        # ;foreach.* → own lines
  source, intent, broadcast = split_intent(body)            # !intent / !* → new line
  coll_src, coll_body = split_collection_iteration(source)  # SOURCE*(BODY)
  if coll_body is not None:   # fan-out
      emit: format(coll_src) + "*(" + newline
             + format(coll_body, indent+2)                   # recurse body
             + newline + ")" at indent
  elif source is a balanced (group):  # list/ensemble group
      emit "(" + newline + each item on its own line via format(item, indent+2) + newline + ")"
  else:
      node = parse(source)                                  # base grammar on the leaf
      emit format_node(node, indent)                        # AST walk (below)
  if intent: emit newline + indent + "!" + format_intent(intent, indent)   # '*' if broadcast
  for d in directives: emit newline + indent + ";foreach.<k>=<v>"
```
`format_node(node, indent)` walks the 8 AST dataclasses (`url4_ast.py`): `Url4BackendCall` (emit `name:weight:` prefix + `path` + `(packed_context)` + `!intent`), `Url4List` (items one-per-line), `Url4Binding` (`name=`/`name:` + value), `Url4Reduce`, `Url4ExpandedSource` (`*inner`), `Url4Url`/`Url4RelUrl`/`Url4Text` (verbatim).

`format_intent(intent, indent)`:
- **json-blob** intent (`!{…}`, the SF-235 form) → `json.loads` then `json.dumps(indent=2)` re-indented to the parent; on parse failure, leave verbatim.
- quoted string `'…'` → leave **as one token** (see caveat); only place it on its own line.
- otherwise (relurl/backend) → recurse `format(...)`.

Idempotency: `format_url4(format_url4(x)) == format_url4(x)` — add a test. Because the decoder strips inter-token whitespace, re-formatting is stable for everything **except** strings (caveat).

New endpoint (mirror `/ensemble/highlight`, `routes.py:69-82`): `GET /ensemble/format?q=<expr>` → `{ formatted: string }`; on parse error return the original + an `error` field (never destroy input). Reuses `tokenize`/`parse` import style.

### Desktop (`apps/desktop`)
- **Format button** in `CodeEditorPopup` header (next to the new CopyButton) — calls `GET /ensemble/format`, replaces the editor draft with `formatted` (no-op + toast on error).
- Register a **Monaco document-formatting provider** for `url4` in `url4-language.ts` so ⇧⌥F also formats (provider calls the same endpoint).
- url4 editor options: `tabSize: 2, insertSpaces: true` (currently `CodeEditorPopup` hardcodes `tabSize:4` — make it 2 for `language==='url4'`).
- Keep `wordWrap: 'on'` (soft-wrap) for the string caveat.

## The string-wrap caveat (decision needed)
url4 string literals (`'[^']*'`) **preserve embedded newlines as prompt content**. So hard-wrapping a long string inserts whitespace into the prompt the model receives, and isn't cleanly idempotent (re-format would have to collapse the string's internal whitespace — lossy). **Recommendation: do NOT hard-wrap string contents** — rely on Monaco soft-wrap for display. The "≤60 char" rule applies only to *layout between tokens*, never inside `'…'`. (Confirm; alternative is an explicit opt-in "rewrap prompt text" that documents the whitespace change.)

## Why server-side (not a TS formatter)
A TS formatter would reimplement both the base grammar **and** the ensemble decomposition — guaranteed to drift from the real parser. Server-side reuses the exact functions `/ensemble` uses, so "formats iff it runs."

## Effort
- Server `formatter.py` (recursive printer + json-blob + AST walk): the bulk, ~250-350 lines, bounded by the 8 node types + 3 splitters. + endpoint (~15 lines) + tests (idempotency, each node type, ensemble spec round-trip, json-blob).
- Desktop: Format button + formatting provider + 2-space tab (~60 lines) + a test.
- ~1–1.5 days. **Additive** (no grammar change), but **coupled to** `decoder.py`/`ensemble.py` internals → must track changes there; coordinate with Kevin.

## Test plan
- Server pytest: format each AST node; format MainOne & ScoredLiveTruth (full ensemble specs) without error; `{…}` → pretty JSON; **idempotency**; malformed input returns original + error (no data loss); strings are left byte-identical.
- Desktop vitest: Format button calls the endpoint and replaces the draft; error path toasts + leaves content; the formatting provider is registered.

## Out of scope
- Changing the url4 grammar or the ensemble decomposition (Kevin).
- Hard-wrapping string contents (unless the opt-in above is chosen).
- Auto-format-on-save (button + ⇧⌥F only).
- Fixing SF-251 (`/ensemble/highlight`) — separate; the formatter avoids the base-grammar limitation by reusing the interpreter's splitters.

## Open questions
1. **String wrapping:** soft-wrap only (recommended) or an explicit "rewrap prompt text" opt-in?
2. **Coupling:** OK to depend on `decoder.split_intent/split_foreach_annotations` + `split_collection_iteration` (internal helpers), or should we ask Kevin to expose a stable `parse_ensemble()` AST first (cleaner, but blocks on him)?
3. **Endpoint shape:** `GET /ensemble/format?q=` (mirrors highlight) vs `POST` (avoids URL-length limits on big specs) — I lean POST for large expressions.
