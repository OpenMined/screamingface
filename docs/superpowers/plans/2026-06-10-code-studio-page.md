# Plan: "Code Studio" page (python-runner scripts)

Date: 2026-06-10
Status: PLAN ONLY — no implementation. Awaiting explicit approval before any code change.

## 1. Overview

Add a new top-level desktop page, **Code Studio**, that lists the python-runner
plugin's named scripts and lets the user CRUD them, mirroring the just-merged
**URL4 Studio** page almost 1:1.

- Left pane: searchable list of scripts (by name, with a code-snippet subtitle).
- Right pane: a view form with an inline-editable name + a read-only code
  preview + an **"Edit code"** button that opens the shared `CodeEditorPopup`
  with `language="python"` (no `onFormat` — Format is url4-only).
- CRUD: add (name-only dialog), inline rename, delete-with-confirm.
- A new sidebar nav entry "Code Studio", placed directly after "URL4 Studio".

The data source is the difference that matters: scripts live in the
**`python-runner`** plugin settings as `scripts: dict[str, str]` (name → Python
source), not as `{ expression }` objects. Persistence is otherwise identical to
URL4 Studio (durable `sf.json` write + best-effort in-memory POST to the running
server). The existing RJSF `CodeDictField` in Settings is **left in place**.

### Verified facts (file:line)

- Plugin name is `python-runner`; settings field is `scripts: dict[str, str]`,
  default `load_vendored_defaults`, with `json_schema_extra={"x-code-editor": {"language": "python"}}`
  — `apps/server/src/screamingface/plugins/python_runner/plugin.py:64-73`.
- Name rule is `VALID_SCRIPT_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")` (a Python
  identifier), enforced by a `field_validator` on `scripts` —
  `apps/server/src/screamingface/plugins/python_runner/plugin.py:48`, `:75-83`.
- The desktop already mirrors that rule: `VALID_NAME = /^[a-zA-Z_][a-zA-Z0-9_]*$/`
  with the comment "Mirrors the python-runner backend rule (VALID_SCRIPT_NAME)" —
  `apps/desktop/src/renderer/src/components/rjsf-CodeDictField.tsx:14-15`.
- Generic per-plugin settings endpoints exist (so no new server route is needed):
  `POST /plugins/{name}/settings/validate` and `POST /plugins/{name}/settings` —
  `apps/server/src/screamingface/core/admin_router.py:192-214`. Validate returns
  `{"valid": true}` or HTTP 422 with `detail=str(exc)`.
- Both `url4-specs` and `python-runner` are active in `apps/server/sf.json`
  (lines 14 and 20; settings blocks at 246 and 268).
- `CodeEditorPopup` already supports a Copy button (always) and a Format button
  (only when `onFormat` is passed) — `apps/desktop/src/renderer/src/components/CodeEditorPopup.tsx:31,47,95-104`.
  Omitting `onFormat` hides Format, which is what we want for Python.

## 2. Mapping onto URL4 Studio

| URL4 Studio (exists) | Code Studio (new) | Change |
|---|---|---|
| `views/Url4StudioView.tsx` | `views/CodeStudioView.tsx` | Title "Code Studio"; "New script" button; subtitle copy; `autoSaveId="code-studio-split"`; panel ids `code-scripts-list` / `code-script-detail`; aria labels "scripts list" / "script details". |
| `hooks/use-url4-specs.ts` | `hooks/use-code-scripts.ts` | `PLUGIN='python-runner'`; value type `string` (source) instead of `{ expression }`; field `scripts` instead of `specs`; methods `createScript/renameScript/deleteScript/saveSource`; add Python-identifier name validation on create+rename. |
| `components/url4/Url4SpecsList.tsx` | `components/code/CodeScriptsList.tsx` | Filter on name + source; subtitle shows first line of source or "(empty)"; empty-state copy. Row shows `name.py`. |
| `components/url4/Url4SpecDetail.tsx` | `components/code/CodeScriptDetail.tsx` | Read-only preview is a `<pre>` code block (not `Url4Field`); "Edit code" button; `CodeEditorPopup` with `language="python"`, **no** `onEditorMount`, **no** `onFormat`; title `${name}.py`. Inline rename validates Python identifier before calling `onRename`. |
| `components/url4/AddUrl4SpecDialog.tsx` | `components/code/AddCodeScriptDialog.tsx` | Name placeholder `script_name`; add Python-identifier validation + hint; "The code starts empty…" copy. |
| `components/layout/Sidebar.tsx` (`url4-studio` nav) | same file | Add `code-studio` to `View` union + `coreItems` entry after URL4 Studio. |
| `App.tsx` (`url4-studio` branch) | same file | Add `code-studio` route branch after the url4 branch. |

## 3. Data model & persistence

### Shapes

```ts
// use-code-scripts.ts
export interface CodeScript { name: string; source: string }
type ScriptMap = Record<string, string>;   // name -> python source
const PLUGIN = 'python-runner';
```

Read from `config.plugin_config['python-runner'].scripts` (a flat
`dict[str,str]`), unlike url4's `specs` (`{[name]: {expression}}`). The
`specMapOf`-equivalent (`scriptMapOf`) normalizes each value to a string:
`Object.fromEntries(Object.entries(raw).map(([n,v]) => [n, typeof v === 'string' ? v : '']))`.

### Persist path (identical to `use-url4-specs.ts:84-134`)

For every mutation, build `settings = { ...config.plugin_config['python-runner'], scripts: nextScripts }`,
then:

1. If a server base URL is known, `POST ${base}/plugins/python-runner/settings/validate`
   with the settings body. On non-OK, parse `detail` and `toast` an error, return
   `false` (block the write). On network failure, fall through and save anyway.
2. Best-effort (fire-and-forget) `POST ${base}/plugins/python-runner/settings`
   with the same body, so the running server's in-memory `settings.scripts`
   updates without a disk re-read (keeps `GET /data/code/<name>.py` current).
3. `await window.electronAPI.config.write(next)` — durable write to `sf.json`.
4. `setConfig(next)` optimistically; the `config:changed` broadcast reconciles
   with the Settings page (and vice-versa).

`serverBase()` is copied verbatim (`0.0.0.0` → `localhost`).

### scripts-dict transforms

- **create(name)**: trim; reject empty; **reject non-Python-identifier** (new vs
  url4); reject duplicate (`name in scriptMap`). `persist({ ...scriptMap, [name]: '' }, 'Could not create script')`.
- **rename(oldName, newName)**: trim; no-op if empty or unchanged;
  **reject non-Python-identifier**; reject duplicate. Rebuild preserving order by
  swapping the key in place (same `Object.entries(...).map` trick as
  `use-url4-specs.ts:166-168`), value carried over. `persist(next, 'Could not rename script')`.
- **delete(name)**: `{ ...scriptMap }; delete next[name]; persist(next, 'Could not delete script')`.
- **saveSource(name, source)**: guard `name in scriptMap`;
  `persist({ ...scriptMap, [name]: source }, 'Could not save code')`. (url4 stores
  `{ ...specMap[name], expression }`; here the value is just the string.)

The server's `field_validator` is the backstop: an invalid name slips past the
client only if the server is unreachable, in which case it will be rejected on
the next reachable validate. Client-side identifier checking matches
`rjsf-CodeDictField.tsx:14,33-40`.

## 4. Components to create / files to modify

### Create
- `apps/desktop/src/renderer/src/views/CodeStudioView.tsx`
- `apps/desktop/src/renderer/src/hooks/use-code-scripts.ts`
- `apps/desktop/src/renderer/src/components/code/CodeScriptsList.tsx`
- `apps/desktop/src/renderer/src/components/code/CodeScriptDetail.tsx`
- `apps/desktop/src/renderer/src/components/code/AddCodeScriptDialog.tsx`
- Tests (see §6):
  - `apps/desktop/src/renderer/src/hooks/__tests__/use-code-scripts.test.ts`
  - `apps/desktop/src/renderer/src/views/CodeStudioView.test.tsx`
  - `apps/desktop/src/renderer/src/components/code/__tests__/CodeScriptDetail.test.tsx`
  - `apps/desktop/src/renderer/src/components/code/__tests__/AddCodeScriptDialog.test.tsx`
  - `apps/desktop/src/renderer/src/components/code/__tests__/CodeScriptsList.test.tsx` (optional, mirrors `Url4SpecsList.test.tsx` if that file is expanded)

### Modify
- `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx`
  - Import a distinct lucide icon — **`FileCode2`** (Code Studio is files-of-code; `Workflow` is taken by URL4, `FileCode` is used inside `rjsf-CodeDictField`).
  - Add `'code-studio'` to the `View` union (after `'url4-studio'`).
  - Add `{ id: 'code-studio', label: 'Code Studio', icon: FileCode2 }` to `coreItems` after the URL4 Studio entry.
- `apps/desktop/src/renderer/src/App.tsx`
  - `import { CodeStudioView } from '@/views/CodeStudioView';`
  - Add `if (currentView === 'code-studio') return <CodeStudioView />;` after the `url4-studio` branch.

## 5. The edit flow

`CodeScriptDetail` renders:
- inline-editable `<h2>`/input header (copy `Url4SpecDetail.tsx:39-114`), but
  `commitName` first checks `VALID_SCRIPT_NAME` (a shared `const` re-declared in
  the detail + dialog + hook, matching `rjsf-CodeDictField.tsx:15`); on invalid,
  it does not call `onRename` (the hook also re-validates as a backstop).
- a **read-only code preview**: a `<pre><code>` monospace block showing
  `script.source` (or "(empty)"), with a `CopyButton`. We do **not** reuse
  `Url4Field` (it is url4-specific and Monaco-backed); a plain `<pre>` is enough
  for a preview and avoids loading Monaco until "Edit code" is clicked.
- an **"Edit code"** button that sets `editingCode = true`, lazily rendering:

```tsx
<CodeEditorPopup
  title={`${script.name}.py`}
  language="python"
  value={script.source}
  confirmLabel="Save"
  confirmIcon={<Save className="h-4 w-4" />}
  onSave={(src) => onSaveSource(script.name, src)}
  onClose={() => setEditingCode(false)}
  // NOTE: no onEditorMount, no onFormat → Format button stays hidden (url4-only).
/>
```

Monaco ships Python highlighting out of the box, so no `onEditorMount`/language
registration is needed (url4 needs it; Python does not). `CodeEditorPopup` sets
`tabSize: 4` for non-url4 languages already (`CodeEditorPopup.tsx:88`), which
suits Python.

Delete uses the same `ConfirmDialog` pattern as `Url4SpecDetail.tsx:128-140`,
with script-flavored copy.

## 6. Name validation

- Shared regex `const VALID_SCRIPT_NAME = /^[a-zA-Z_][a-zA-Z0-9_]*$/;` — identical
  to the server's `VALID_SCRIPT_NAME` (`plugin.py:48`) and the existing client copy
  (`rjsf-CodeDictField.tsx:15`). To stay DRY, **export it from a small shared module**
  (e.g. `apps/desktop/src/renderer/src/lib/script-name.ts`) and have both the new
  Code Studio components and `rjsf-CodeDictField.tsx` import it. (If reviewers prefer
  minimal blast radius, re-declare it locally and leave `rjsf-CodeDictField` untouched
  — call this out as an open question, §10.)
- Validation points: AddCodeScriptDialog (disable Create + show hint),
  CodeScriptDetail inline rename (block commit + show hint), and the hook
  (`createScript`/`renameScript` return `false` + `toast` on invalid). Error copy
  matches `rjsf-CodeDictField.tsx:36-38`: "Use a Python identifier: start with a
  letter/underscore; letters, digits, underscores only."
- This is the one behavioral departure from URL4 Studio, whose names are permissive
  (no regex in `AddUrl4SpecDialog`/`use-url4-specs`).

## 7. Leave the RJSF CodeDictField in Settings? — Yes, recommend LEAVE

- The `x-code-editor` → `CodeDictField` mapping (`rjsf-utils.ts:15-19`,
  `rjsf-theme.tsx:578`) is generic for any `x-code-editor` dict field, not
  python-runner-specific; removing it could regress other/future plugins.
- URL4 Studio set the precedent: it added a dedicated page while leaving Settings
  editing intact. Code Studio should match.
- Both surfaces write the same `sf.json` key and listen to `config:changed`, so
  they stay in sync. No change to Settings is in scope.

## 8. Test plan (vitest, mirrors url4-studio tests)

Mirror the four existing url4 test files, adapting fixtures to the flat
`scripts: dict[str,str]` shape and adding identifier-validation cases.

1. **`use-code-scripts.test.ts`** (from `__tests__/use-url4-specs.test.ts`):
   - mock `use-toast`, `use-server-status`; stub `window.electronAPI.config` +
     `server.fetch`; `baseConfig` = `{ plugin_config: { 'python-runner': { scripts: { greet: "print('hi')" } } } }`.
   - loads scripts from local config → `[{ name:'greet', source:"print('hi')" }]`.
   - `createScript('hello')` writes `{...}` preserving order, new key `''`.
   - `createScript('greet')` rejected (duplicate) — no write, toast.
   - **`createScript('1bad')` rejected (invalid identifier)** — no write, toast (NEW).
   - `renameScript('greet','hello')` swaps key in place, source preserved.
   - **`renameScript('greet','1bad')` rejected (invalid identifier)** (NEW).
   - `deleteScript('greet')` → `{}`.
   - `saveSource('greet', 'x=1')` updates only that value.
   - server validate 422 → aborts write, toast with parsed `detail`.

2. **`CodeStudioView.test.tsx`** (from `Url4StudioView.test.tsx`): mock
   `use-code-scripts` (empty) and stub `CodeScriptDetail`; assert header "Code
   Studio", "New script" button, both pane toggles, and empty-state text.

3. **`CodeScriptDetail.test.tsx`** (from `Url4SpecDetail.test.tsx`): stub
   `CodeEditorPopup` to a button emitting a source string; assert name + read-only
   preview render; inline rename on Enter calls `onRename`; **inline rename with an
   invalid identifier does NOT call `onRename`** (NEW); delete only after confirm;
   "Edit code" → save calls `onSaveSource(name, src)`. (No `Url4Field` mock needed
   since the preview is a plain `<pre>`.)

4. **`AddCodeScriptDialog.test.tsx`** (from `AddUrl4SpecDialog.test.tsx`): creates
   with a valid name; blocks empty; blocks duplicate with hint; **blocks an invalid
   identifier with a hint** (NEW).

Run: `pnpm --filter <desktop-pkg> test` (or the repo's configured vitest command;
confirm during build).

## 9. Build sequence

1. (If chosen) add `lib/script-name.ts` exporting `VALID_SCRIPT_NAME`; refactor
   `rjsf-CodeDictField.tsx` to import it. Run existing CodeDictField/Settings tests.
2. `hooks/use-code-scripts.ts` + its test → green.
3. `components/code/AddCodeScriptDialog.tsx` + test → green.
4. `components/code/CodeScriptsList.tsx` (+ optional test) → green.
5. `components/code/CodeScriptDetail.tsx` + test → green.
6. `views/CodeStudioView.tsx` + test → green.
7. Wire `Sidebar.tsx` (`View` union + `coreItems` + `FileCode2` import) and
   `App.tsx` (import + route branch).
8. Run full desktop unit suite + typecheck/lint; manually verify in the running
   app (create/rename/delete/edit a script; confirm `GET /data/code/<name>.py`
   reflects edits and the Settings CodeDictField stays in sync via `config:changed`).

## 10. Out of scope

- Running/executing scripts from Code Studio (no run button; execution is the
  server's `/python` backend path).
- Any change to Settings beyond the optional `VALID_SCRIPT_NAME` import refactor.
- Server-side changes (the generic admin endpoints already cover validate/update).
- url4-specific features: language registration, `formatUrl4`/Format button,
  `Url4Field` Monaco preview.
- Sharing/export of scripts, vendored-default management UI.

## 11. Confidence

**~95%.** The URL4 Studio architecture, the python-runner settings shape, the name
rule, and the generic admin endpoints are all confirmed in-repo at the cited
lines. The shared-regex extraction (§6, step 1) is the only design choice with a
reviewer-preference fork; both branches are spelled out.

## 12. Open questions

1. **Shared `VALID_SCRIPT_NAME`**: extract to `lib/script-name.ts` (DRY, touches
   `rjsf-CodeDictField.tsx`) vs. re-declare locally (smaller blast radius)?
   Recommendation: extract, per the repo's DRY mandate.
2. **Read-only preview**: plain `<pre>` (recommended, no Monaco until "Edit code")
   vs. a read-only Monaco view for Python syntax highlighting in the preview pane.
   Recommendation: `<pre>` for parity-of-effort and bundle weight.
3. **Subtitle in the list row**: show the first non-blank line of source
   (recommended) or a script byte/line count?
4. **Asana/branch**: this is plan-only; on approval, get the SF ticket and a
   `SF-{n}-code-studio-page` branch before any code (per CLAUDE.md git workflow).
