# SF-249 — url4 Monaco editor: highlighting + live validation + static autocomplete

**Asana:** https://app.asana.com/1/1185126988600652/task/1215563390685246
**Depends on:** SF-247 Monaco infra (reland PR #264) · integrates with SF-248 "+ add url4" popup.
**Confidence:** ≥95% for Pass 1 + Pass 2; the deferred grammar-aware completion is explicitly out of scope.

## Context

Editing url4 expressions today is a plain `<textarea>` (`Url4Editor.tsx`) with a separate read-only `Url4Viewer` preview. Now that Monaco is wired up (SF-247: `monaco-setup.ts`, `?worker` bundling, lazy `CodeEditorPopup` shell, `@monaco-editor/react`), a real url4 editor is cheap — register a `url4` language with highlighting, live validation squiggles, and autocomplete, reusing the SF-247 shell. The expensive part (Monaco bundling) is already paid for.

The grammar already exists server-side (`url4_executor/url4_grammar.py`, TatSu PEG) and is exposed as a tokenizer/validator: **`GET /ensemble/highlight?q=<expr>`** returns `{tokens: [{type, value, depth}]}` (types: `paren|comma|ws|url|text|intent_sep|intent`) and **`400` with `"url4 parse error: <tatsu>"`** on bad syntax. `Url4Viewer.tsx` already calls this debounced + cached.

## Approach — two passes

### Pass 1 — highlight + live validation (small, high value)

1. **Register a `url4` Monaco language** with a **Monarch tokenizer** (client-side regex rules, no round-trip) covering: parentheses/commas (structure), single-quoted `'…'` intent strings, `http(s)://…` and `/data/…`/`/<backend>` paths (urls), `$item.*`/`$prompt`/`$consensus` variables, `name:0.40:` weight syntax, `foreach.*` modifiers. New file `lib/url4-language.ts` (idempotent `registerUrl4Language(monaco)`), called from `monaco-setup` or lazily on first editor mount.
2. **Live validation markers:** a small hook/util that debounces (~300ms, reuse the `Url4Viewer` cadence) and calls `GET /ensemble/highlight?q=<expr>`; on `400`, parse the TatSu message into a `monaco.editor.IMarkerData` (severity Error, message, best-effort range) and `setModelMarkers`; on success, clear markers. This makes the existing server validation appear as squiggles — near-free.
3. *(Optional, low-risk)* feed the server's typed tokens into Monaco **decorations** as a second highlight source so highlighting can never disagree with the real grammar. Default to Monarch-only for v1; add decorations only if Monarch drift shows up.

### Pass 2 — static-list autocomplete (medium)

`monaco.languages.registerCompletionItemProvider('url4', …)` returning a **static + lightly-dynamic** suggestion set (no grammar follow-sets):
- **Backend paths:** `/claude`, `/codex`, `/gemini`, `/python`, `/ollama` (source: the active backends, or hardcode the known five).
- **Variables:** `$item.`, `$prompt`, `$consensus`.
- **Spec names:** fetched from `GET /plugins/url4-specs/settings` (same source as `SpecSelector`), cached.
- **Modifiers:** `foreach.concurrency=`, `foreach.on_error=collect`.
- **Weight snippet:** `${provider}:0.40:` as a snippet.
Cheap, ~an afternoon. Provide these as `CompletionItem`s with kinds/snippets; no positional legality analysis.

### Deferred (explicitly out of scope for SF-249)
Grammar-aware contextual completion ("what tokens are legal at cursor N"). TatSu PEG answers parse/no-parse, not follow-sets; would need error-recovery parsing or follow-set derivation. Revisit only if the static list proves insufficient.

## Components / files

| File | Change |
|---|---|
| `apps/desktop/src/renderer/src/lib/url4-language.ts` | **New** — `registerUrl4Language(monaco)`: Monarch tokenizer + completion provider (idempotent) |
| `apps/desktop/src/renderer/src/lib/__tests__/url4-language.test.ts` | **New** — tokenizer rules + completion items (pure, no Monaco DOM) |
| `apps/desktop/src/renderer/src/components/Url4MonacoEditor.tsx` | **New** — thin `@monaco-editor/react` `<Editor language="url4">` wrapper that registers the language `onMount`, wires the debounced `/ensemble/highlight` validation→markers, exposes `value`/`onChange`. Lazy-loaded like `CodeEditorPopup`. |
| `apps/desktop/src/renderer/src/components/Url4Editor.tsx` | Swap the `<textarea>` for `Url4MonacoEditor` (keep the `initial`/`onRun` contract) |
| SF-248 "+ add url4" popup (`AddEvalRunDialog`) | Use `Url4MonacoEditor` for the expression field instead of a plain input |

Reuse from SF-247: `lib/monaco-setup.ts` (loader+worker), lazy-import pattern, `@monaco-editor/react`.

## Validation marker mapping
- Reuse the existing debounced fetch shape from `Url4Viewer.tsx`.
- `200` → `setModelMarkers(model, 'url4', [])`.
- `400` → one Error marker; map the TatSu line/col from the message to a range if parseable, else underline the whole line. Keep the parsing defensive (TatSu message format may vary) — fall back to a full-expression marker.

## Verification
- **Unit (vitest):** `url4-language.test.ts` — tokenizer classifies a representative expression (urls, intents, vars, weights, modifiers, parens); completion provider returns the expected static items incl. spec names from a mocked `/plugins/url4-specs/settings`. `Url4MonacoEditor` test mounts with a mocked `@monaco-editor/react` Editor (jsdom can't run Monaco) and asserts: language registered once, a `400` highlight response produces a marker, a `200` clears it.
- **Build:** `npm run build` succeeds (Monaco already chunked from SF-247; the new language adds negligible size).
- **Manual e2e:** open the "+ add url4" popup / RunView edit; type a valid expression → highlighted, no squiggle; introduce a syntax error → red squiggle with the TatSu message; type `/`, `$`, `foreach.` → completion suggestions appear; pick a spec name from the list.

## Build sequence
1. `url4-language.ts` Monarch tokenizer + tests (pure, fastest).
2. `Url4MonacoEditor.tsx` (Editor wrapper + `onMount` registration), lazy.
3. Wire debounced `/ensemble/highlight` → markers.
4. Add Pass-2 completion provider (backends/vars/specs/modifiers/weights) + tests.
5. Swap into `Url4Editor` and the SF-248 popup.
6. Gates + manual e2e.

## Notes / risks
- **Marker range parsing** from TatSu text is best-effort; never block editing on it (degrade to a whole-line marker).
- **Highlight source choice:** start Monarch-only (no latency); only add server-token decorations if Monarch visibly drifts from the grammar.
- Keep the editor lazy so the ~7 MB Monaco chunk only loads when an editor is actually opened (matches SF-247).
