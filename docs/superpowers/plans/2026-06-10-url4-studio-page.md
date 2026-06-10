# URL4 Studio — Implementation Plan

**Status:** Draft for review (planning only — no code yet)
**Author:** research agent
**Date:** 2026-06-10
**Confidence:** ~88% (one persistence-semantics gap to confirm with the user — see "Open questions")

---

## 1. Overview

Today, URL4 specs (named URL4 expressions) are edited only inside the giant RJSF
settings page, under the `url4-specs` plugin's `specs` dict field
(`apps/desktop/src/renderer/src/views/SettingsView.tsx`). That's hard to find and
clunky to edit.

This plan adds a dedicated, top-level **URL4 Studio** screen that mirrors the
**Eval Studio** two-pane layout:

- **Left pane** — a searchable list of URL4 specs with full CRUD (create / rename / delete).
- **Right pane** — a read-only "view form" for the selected spec: an **inline-editable name**
  and a **read-only URL4 expression** rendered with `Url4Field` (readonly).
- **Edit expression** — opens the *same* `CodeEditorPopup` used by Eval Studio's
  `EvalRunDetail`, with url4 syntax highlighting via the `mountUrl4Editor` `OnMount` handler.
  Editing the expression is **not** inline.
- **Nav** — a new top-level sidebar entry "URL4 Studio", alongside Dashboard / Sessions /
  Eval Studio / Settings.

The data model is the `url4-specs` plugin's settings: a dict keyed by spec name whose values
are `{ expression: string }`. CRUD = mutations on that dict, persisted exactly the way the
RJSF settings form persists plugin settings today (write the whole `sf.json` config to disk via
`window.electronAPI.config.write`).

### How it maps onto Eval Studio

| Eval Studio | URL4 Studio |
|---|---|
| `views/EvalStudioView.tsx` — `ResizablePanelGroup`, header w/ "New run" + collapse toggles, `selectedRunId` state | `views/Url4StudioView.tsx` — same shell; "New spec" button + collapse toggles; `selectedSpecName` state |
| `components/eval/EvalRunsList.tsx` (left) | `components/url4/Url4SpecsList.tsx` (left) |
| `components/eval/EvalRunDetail.tsx` (right) + `CodeEditorPopup` for expression edit | `components/url4/Url4SpecDetail.tsx` (right) + `CodeEditorPopup` for expression edit |
| `hooks/use-eval-runs.ts` (read) + `hooks/use-eval-run-actions.ts` (mutate) | `hooks/use-url4-specs.ts` (read + CRUD, single hook — see §3) |
| `components/eval/AddEvalRunDialog.tsx` (create) | reuse a small inline create flow (see §6) |

Reference: `EvalStudioView.tsx:68-156` (shell), `EvalRunDetail.tsx:19-26,173-190`
(lazy `CodeEditorPopup` + `mountUrl4Editor`), `EvalRunsList.tsx:44-107` (list rows).

---

## 2. Data model & persistence

### 2.1 The spec shape (server-side)

`apps/server/src/screamingface/plugins/url4_specs/plugin.py`:

- `Url4Spec` (`plugin.py:20-38`) — `{ expression: str }` (with examples/placeholder metadata).
- `Url4SpecsSettings` (`plugin.py:41-50`) — `specs: dict[str, Url4Spec]` (key = spec name).
- Plugin `name = "url4-specs"` (`plugin.py:54`). It registers **no routes** — it is "pure
  settings storage" (`plugin.py:77`).

So a spec is `{ name, expression }` in the UI, stored on the wire as
`specs: { [name]: { expression } }`. This matches how `SpecSelector.tsx:52-61` already parses it.

### 2.2 Read endpoint

`GET /plugins/url4-specs/settings` → `{ specs: { [name]: { expression } } }`.

- Server handler: `apps/server/src/screamingface/core/admin_router.py:176-190` (`plugin_settings`).
  It **re-reads `sf.json` from disk** (`load_config()`), merges with plugin defaults, and returns
  the validated settings dump. This is the authoritative read for current specs.
- Desktop already calls this exact URL in `SpecSelector.tsx:46` and parses the `specs` dict.

### 2.3 Write / persistence — the important nuance

There are **two** server settings endpoints, and only one matters for durable CRUD:

- `POST /plugins/{name}/settings` (`admin_router.py:192-200`) — updates **in-memory only**
  (`plugin.settings` + `app.state.config.plugin_config[name]`). It does **not** write `sf.json`.
  On the next `GET …/settings` (which re-reads disk) or a server restart, in-memory-only writes
  are lost. **Do not rely on this for persistence.**
- `POST /plugins/{name}/settings/validate` (`admin_router.py:202-214`) — dry-run validation;
  returns `{ valid: true }` or HTTP 422 with `detail`.

**How the RJSF settings page actually persists** (the pattern we must copy):
`SettingsView.tsx` writes the *entire* app config object to disk via
`window.electronAPI.config.write(config)` (`SettingsView.tsx:140`), where
`config.plugin_config['url4-specs']` holds the specs dict. The IPC handler
`config:write` (`apps/desktop/src/main/ipc/config.ipc.ts:11-14`) calls
`configService.write(...)`, which writes `sf.json` (`config-service.ts:156`, atomic write).
`configService.watch()` + the `config:changed` broadcast (`config.ipc.ts:16-22`) push the new
config back to every renderer.

Before saving, the RJSF page validates plugin settings against the server
(`SettingsView.tsx:117-145`): it POSTs each plugin's settings to
`…/settings/validate` and aborts on failure. We mirror this.

**Conclusion — the persistence contract for URL4 Studio CRUD:**

1. Read current full config via `window.electronAPI.config.read()` (shape in `SettingsView.tsx:20-25`:
   `{ version, server, plugins, plugin_config }`).
2. Compute the new `plugin_config['url4-specs'].specs` dict (create/rename/delete/update-expression
   = pure dict transforms).
3. (Optional but recommended) POST the new `url4-specs` settings to
   `…/plugins/url4-specs/settings/validate`; abort + toast on 422.
4. Persist by writing the whole config object back: `window.electronAPI.config.write(nextConfig)`.
5. Subscribe to `window.electronAPI.config.onChanged(...)` so the list reflects external edits
   (e.g. someone editing the same specs in the Settings page) — same subscription used in
   `App.tsx:24-27` and `SettingsView.tsx:202-213`.

Note: a write to `plugin_config['url4-specs']` does **not** require a server restart (unlike the
`plugins:` array, which `SettingsView.updatePlugins` restarts for — `SettingsView.tsx:254-265`).
Settings changes are picked up by the next disk-reading `GET …/settings`. We should still POST to
the in-memory `…/settings` endpoint *opportunistically* (best-effort) so the running server's
`active_spec` resolution sees the new specs without waiting on its own disk re-read — but the
durable source of truth is the `config.write` to `sf.json`. (Confirm desire for this dual-write in
Open questions.)

### 2.4 CRUD → settings-write mapping

Let `specs = plugin_config['url4-specs'].specs ?? {}` (an object).

- **Create**: `specs[newName] = { expression: '' }` (or a starter expression). Reject if `newName`
  already exists (case-sensitive key collision).
- **Rename** (`oldName` → `newName`): build a new object preserving insertion order where possible:
  `{ ...without(oldName), [newName]: specs[oldName] }`. Reject if `newName` exists. Update
  `selectedSpecName` to `newName`.
- **Delete**: `delete specs[name]` (build new object without the key). Clear selection if it was
  selected (mirror `EvalStudioView.handleRunDeleted`, `EvalStudioView.tsx:34-36`).
- **Update expression** (`name`, `expr`): `specs[name] = { ...specs[name], expression: expr }`.

Each mutation produces a new full config and persists per §2.3.

### 2.5 Gaps (server changes needed?)

- **No new server endpoint is required.** Read (`GET …/settings`), validate
  (`POST …/settings/validate`), and disk persistence (`config:write` IPC) all already exist.
- **Minor gap:** persistence is renderer-driven (write whole `sf.json`), not a REST PUT to the
  plugin. This is *by design* in this codebase and is exactly how Settings works — so no change.
  If the team later wants a true persisting `PUT /plugins/{name}/settings`, that's a separate,
  out-of-scope server task. Flag, don't build.

---

## 3. Components to create

All under `apps/desktop/src/renderer/src/`, TypeScript React, Tailwind, `@/` imports.

### 3.1 `views/Url4StudioView.tsx`
**Responsibility:** screen shell — mirror `EvalStudioView.tsx:68-156` almost verbatim.
- `ResizablePanelGroup direction="horizontal" autoSaveId="url4-studio-split"`.
- Header: title "URL4 Studio", subtitle (e.g. "Named URL4 expressions you can run and share"),
  a **"New spec"** `Button` (`Plus` icon) and the two pane-collapse toggle buttons
  (`PanelLeftClose/Open`, `PanelRightClose/Open`) with the same `aria-label`/`aria-pressed`.
- State: `selectedSpecName: string | null`, `leftCollapsed`, `rightCollapsed`, `creating: boolean`.
- Left panel renders `<Url4SpecsList selectedName onSelect />`.
- Right panel renders `<Url4SpecDetail name … />` or the "Select a spec to see details" empty state.
- Uses the `use-url4-specs` hook to get specs + CRUD callbacks; passes them down.

### 3.2 `components/url4/Url4SpecsList.tsx`
**Responsibility:** left-pane list (mirror `EvalRunsList.tsx` + the search box from
`SpecSelector.tsx:86-95`).
- Props: `{ specs, selectedName, onSelect, loading?, error? }`.
- Optional filter input (reuse `SpecSelector`'s search styling) filtering by name/expression.
- Rows: spec name (truncate) + a muted, truncated mono preview of the expression
  (like `SpecSelector.tsx:140-149`); active styling like `EvalRunsList.tsx:52-55`.
- Empty state: "No specs yet. Use 'New spec' above." (mirror `EvalRunsList.tsx:35-42`).
- No per-row delete here (delete lives in the detail pane to match Eval Studio), unless we choose a
  small trailing trash button — see §6 decision.

### 3.3 `components/url4/Url4SpecDetail.tsx`
**Responsibility:** right-pane view form (mirror `EvalRunDetail.tsx`).
- Props: `{ name, expression, onRename, onDelete, onSaveExpression, serverUrl }`.
- Header row: **inline-editable name** (see §5) + a **Delete** ghost button
  (`Trash2`) like `EvalRunDetail.tsx:95-102`.
- Read-only expression block: `<Url4Field value={expression} serverUrl={serverUrl} readOnly />`
  inside a bordered `bg-muted/30` container (exactly `EvalRunDetail.tsx:105-107`).
- An **"Edit expression"** `Button` (`Pencil` icon) that opens the lazy `CodeEditorPopup`
  (see §4).
- `ConfirmDialog` for delete (see §5), `editing` boolean for the popup.

### 3.4 `hooks/use-url4-specs.ts`
**Responsibility:** single hook = read + CRUD (combines the read/mutate split of Eval Studio into
one, because the data source is the local config object, not a REST collection).
- Internally:
  - Reads full config via `window.electronAPI.config.read()` on mount and subscribes via
    `window.electronAPI.config.onChanged(...)` (cleanup on unmount) — same as `App.tsx:24-27`.
  - Derives `specs: { name, expression }[]` from `config.plugin_config['url4-specs']?.specs ?? {}`
    (object → array, like `SpecSelector.tsx:54-59`).
  - Exposes `{ specs, loading, error, createSpec, renameSpec, deleteSpec, saveExpression }`.
  - Each mutation: validate name rules (§5), optionally POST to `…/settings/validate`, then
    `config.write(nextConfig)`; surface failures via `useToast` (`hooks/use-toast.ts`).
  - Server URL derived from `useServerStatus()` exactly like `use-eval-run-actions.ts:10-14`
    (`0.0.0.0` → `localhost`).
- Returns plain promises `Promise<boolean>` like `use-eval-run-actions.ts` so callers can await and
  refresh selection.

> Design note (SOLID/DRY): the `serverBase(info)` helper is duplicated across
> `use-eval-runs.ts:8-12`, `use-eval-run-actions.ts:10-14`, and `SpecSelector.tsx:32-34`.
> Consider extracting a shared `lib/server-url.ts` and using it here (small refactor; optional —
> keep in scope only if cheap, otherwise copy the existing inline pattern to stay consistent).

### 3.5 (Optional) `views/Url4StudioView.test.tsx` and component tests
See §7.

---

## 4. Edit flow (reuse, don't reinvent)

Copy the Eval Studio pattern verbatim (`EvalRunDetail.tsx:19-26,173-190`):

```ts
// top of Url4SpecDetail.tsx
const CodeEditorPopup = lazy(() => import('@/components/CodeEditorPopup'));

const mountUrl4Editor: OnMount = (editor, monaco) => {
  registerUrl4Language(monaco);              // from '@/lib/url4-language'
  const model = editor.getModel();
  if (model) monaco.editor.setModelLanguage(model, 'url4');
};
```

Open it when `editing` is true:

```tsx
{editing && (
  <Suspense fallback={null}>
    <CodeEditorPopup
      title="Edit URL4 expression"
      language="url4"
      value={expression}
      inset="10%"
      onEditorMount={mountUrl4Editor}
      confirmLabel="Save"
      confirmIcon={<Save className="h-4 w-4" />}
      onSave={(expr) => void handleSaveExpression(expr)}
      onClose={() => setEditing(false)}
    />
  </Suspense>
)}
```

- `CodeEditorPopup` props are already generalized (`CodeEditorPopup.tsx:13-44`): `inset`,
  `onEditorMount`, `confirmLabel`, `confirmIcon`, optional secondary action. We **omit** the
  secondary "Re-run" button (URL4 Studio doesn't run specs — running lives in Eval Studio).
- `handleSaveExpression(expr)` calls `saveExpression(name, expr)` from the hook, then nothing else
  is needed (the `config:changed` subscription refreshes the list/detail automatically).
- **Inline name editing** is *not* done in the popup — only the expression. Name editing is §5.

---

## 5. Validation / UX

### Name rules
- **Required, non-empty** (trim). Mirror `AddEvalRunDialog`'s `canCreate` gate
  (`AddEvalRunDialog.tsx:29`).
- **Unique** among existing spec names (object-key collision). On collision: block + error toast
  ("A spec named '<x>' already exists").
- **Identifier-ish but permissive:** the server type is just `dict[str, Url4Spec]` — keys are
  arbitrary strings, and existing examples use names freely. Recommend a soft rule: disallow only
  empty/whitespace and leading/trailing spaces; do **not** force a strict identifier regex unless
  the user wants it (Open question). Spec names appear in url4 expressions and `active_spec`
  resolution, so very exotic characters could surprise users — surface a gentle warning rather than
  a hard block. Keep it minimal for v1.

### Inline name editing (detail pane)
- Click the name (or a small pencil) → swap to a text `<input>` seeded with current name.
- Commit on Enter / blur; cancel on Escape (revert).
- On commit with a changed, valid, unique name → `renameSpec(old, new)`; update selection.
- Use the app's input styling (border-input / focus ring) consistent with `AddEvalRunDialog.tsx:52-58`.

### Delete
- `ConfirmDialog` (`components/ConfirmDialog.tsx`) with `destructive`, `busy` while writing, and a
  message like the Eval one (`EvalRunDetail.tsx:162-171`):
  `"\"<name>\" will be permanently removed from your URL4 specs. This can't be undone."`

### Empty states
- No specs: list shows the prompt; right pane shows "Select a spec to see details" (mirrors
  `EvalStudioView.tsx:146-150`).
- Server not running: specs still load from local config (`config.read()` works offline). The
  read-only `Url4Field` gracefully falls back to plain monospace text when Monaco/validation can't
  reach the server (`Url4Field.tsx:22-26`).

### Optimistic update vs refetch
- **Source of truth is the config file + its `config:changed` broadcast.** Strategy: write config,
  let the `onChanged` subscription re-derive `specs`. This is effectively a refetch and avoids
  divergent local state. Optionally set local state optimistically before the write resolves for
  snappiness, but reconcile on the broadcast. Keep it simple: write → rely on broadcast (the write
  is local-disk fast).

### Error toasts
- All mutations use `useToast` (`hooks/use-toast.ts`); on failure show
  `{ variant: 'error', title, description }` (object form is supported — `use-toast.ts:36-43`).
  Note Eval actions use the object form (`use-eval-run-actions.ts:33-37`) while `SettingsView`
  uses the `(string, variant, duration)` form — both valid; pick the object form for consistency
  with the eval hooks we're mirroring.

---

## 6. Files to modify

### 6.1 `components/layout/Sidebar.tsx`
- Extend the `View` union (`Sidebar.tsx:14`):
  `'dashboard' | 'sessions' | 'eval-studio' | 'url4-studio' | 'settings' | \`plugin:${string}\``.
- Add a `coreItems` entry (`Sidebar.tsx:22-27`):
  `{ id: 'url4-studio', label: 'URL4 Studio', icon: Link2 }` (or `Workflow`/`Share2` from
  `lucide-react` — pick an icon distinct from Eval Studio's `FlaskConical`). Place it right after
  Eval Studio.

### 6.2 `App.tsx`
- Add to `renderView()` (`App.tsx:69-103`), after the `eval-studio` branch:
  ```tsx
  if (currentView === 'url4-studio') return <Url4StudioView />;
  ```
- Import `Url4StudioView` at top (`App.tsx:6` neighborhood).
- No deep-link plumbing needed (unlike Eval Studio's `pendingRun`).

### 6.3 Create-spec flow decision
Two options; recommend **A** for the smallest, most Eval-Studio-consistent build:

- **A (recommended):** a tiny `AddUrl4SpecDialog` (or reuse an inline name prompt) that asks only
  for a **name** (expression starts empty, edited via the popup afterward). Mirrors
  `AddEvalRunDialog` minus the url4 field. On create → `createSpec(name)` → select it → user clicks
  "Edit expression". Keeps the create modal trivial and reuses the popup for the real editing.
- **B:** full create dialog with name + url4 field (closer to `AddEvalRunDialog.tsx` verbatim).
  More code, but one-step creation. Decide with the user (Open question).

---

## 7. Test plan (vitest + jsdom)

Mirror existing eval tests (`views/EvalStudioView.test.tsx`,
`components/eval/__tests__/AddEvalRunDialog.test.tsx`).

### Conventions to copy
- File header `// @vitest-environment jsdom`; `@testing-library/react` + `vitest`.
- **Mock the hook**, not the network: `vi.mock('@/hooks/use-url4-specs', ...)` returning controlled
  `specs` + spy CRUD fns — exactly how `EvalStudioView.test.tsx:5-12` mocks `use-eval-runs` etc.
- **Mock heavy children**: stub `Url4Field` with a labelled `<textarea>`
  (`AddEvalRunDialog.test.tsx:12-20`); mock `@/components/CodeEditorPopup` to a simple stub that
  renders a textarea + Save button so we can assert open + onSave without loading Monaco
  (pattern used by `rjsf-CodeDictField.test.tsx`, `PublishToLeaderboardDialog.test.tsx`).
- `afterEach(cleanup)`.

### Cases
1. **`Url4StudioView.test.tsx`** — renders header "URL4 Studio", "New spec" button, both pane
   toggles by `aria-label`, and the "Select a spec to see details" empty state (mirror
   `EvalStudioView.test.tsx:18-24`).
2. **`Url4SpecsList`** — given mocked specs, renders a row per spec with name + expression preview;
   filtering narrows the list; clicking a row calls `onSelect`; empty array → empty state.
3. **CRUD wiring** (with mocked hook):
   - Create flow opens the dialog/prompt and calls `createSpec` with the entered name; blocks empty
     and duplicate names (assert no call + error path).
   - Rename: enter inline edit, change text, Enter → `renameSpec(old, new)`; Escape → no call.
   - Delete: click Delete → `ConfirmDialog` shows → Confirm → `deleteSpec(name)`; selection clears.
4. **Edit expression popup** — clicking "Edit expression" mounts the (mocked) `CodeEditorPopup`;
   Save calls `saveExpression(name, value)`; Cancel/close calls neither.
5. **`use-url4-specs` unit test** (jsdom) — stub `window.electronAPI.config.read/write/onChanged`;
   assert create/rename/delete/update produce the correct `plugin_config['url4-specs'].specs`
   object passed to `config.write`, and that name-collision rejects without writing. (This is the
   highest-value test — it locks the persistence contract from §2.4.)

### Mocking `window.electronAPI`
For the hook test, define a minimal `window.electronAPI = { config: { read, write, onChanged }, server: { fetch } }` in the test (return canned config; capture `write` args). For component tests, the hook is mocked so no `electronAPI` needed.

---

## 8. Step-by-step build sequence

1. **Hook first (TDD):** write `use-url4-specs.test.ts`, then `hooks/use-url4-specs.ts` (read +
   CRUD + persistence per §2). This nails the data contract before any UI.
2. **List:** `components/url4/Url4SpecsList.tsx` + test (render/filter/select/empty).
3. **Detail (view form):** `components/url4/Url4SpecDetail.tsx` — read-only `Url4Field`, inline name
   edit, Delete + `ConfirmDialog`, "Edit expression" → lazy `CodeEditorPopup` + `mountUrl4Editor`.
   Add tests with mocked `CodeEditorPopup`/`Url4Field`.
4. **Create flow:** option A `AddUrl4SpecDialog` (name only) + test.
5. **View shell:** `views/Url4StudioView.tsx` wiring list + detail + create + collapse toggles;
   add `Url4StudioView.test.tsx`.
6. **Nav:** extend `View` union + add `coreItems` entry in `Sidebar.tsx`; add the `url4-studio`
   branch + import in `App.tsx`.
7. **Manual QA:** create/rename/delete/edit a spec; confirm `sf.json` `plugin_config['url4-specs']`
   updates on disk and the change round-trips into the Settings page (and vice-versa via
   `config:changed`). Confirm a spec edited here appears in `SpecSelector`/Eval Studio's spec
   picker.
8. **Lint/typecheck/tests** for the desktop app; ensure no Monaco bundle leaks into the synchronous
   path (it's lazy via `Url4Field` and `CodeEditorPopup`).

---

## 9. Out of scope

- Running/evaluating specs (that stays in Eval Studio — no "Run" button in URL4 Studio).
- A new persisting server endpoint (`PUT /plugins/{name}/settings` that writes `sf.json`). Not
  needed; flagged in §2.5.
- Changing the `url4-specs` plugin schema, adding fields beyond `expression`, or adding server
  routes.
- url4 grammar/validation changes (Kevin owns url4 grammar).
- Removing the `specs` field from the RJSF Settings page (see §10 decision — default: **leave it**).
- Deep-linking into URL4 Studio.
- Sharing/copy-link UX (the plugin's `x-copy-link` metadata, `plugin.py:60-68`) — could be a nice
  follow-up but not in v1.

---

## 10. Where url4 specs currently appear in settings

In `SettingsView.tsx`, the `url4-specs` plugin's `specs` dict is edited via the generic RJSF
`ThemedForm` rendered for any expanded plugin with settings (`SettingsView.tsx:637-698`); there's
no url4-specs-specific code there (the `active_spec` `SpecSelectorWidget` override at
`SettingsView.tsx:693` is for the *frontend* plugins, not url4-specs).

**Recommendation:** **leave** the RJSF editing in place for v1 (both write the same
`plugin_config['url4-specs']` and stay in sync via `config:changed`). Optionally add a hint in
Settings pointing users to URL4 Studio. Removing/hiding the RJSF field is a separate, low-risk
follow-up once URL4 Studio is the established path — out of scope here.

---

## 11. Confidence & open questions

**Confidence: ~88%.** The layout, edit-popup reuse, read endpoint, list/detail patterns, and the
persistence mechanism (write whole `sf.json` via `config.write`, refresh via `config:changed`) are
all directly evidenced in the cited files. The one area to confirm is persistence semantics /
dual-write.

**Open questions for the user:**

1. **Dual-write to the running server?** Persistence is via `config.write` → `sf.json` (durable).
   Should we *also* best-effort `POST /plugins/url4-specs/settings` (in-memory) so a running server
   resolves new specs immediately without re-reading disk, or is the next disk-read good enough?
   (Confirm there isn't a need to restart the server for spec changes — I believe there isn't,
   since specs aren't in the `plugins:` array.)
2. **Create flow:** option A (name-only dialog, then edit expression via popup) — preferred — or
   option B (name + expression in one dialog like `AddEvalRunDialog`)?
3. **Name validation strictness:** soft rules (non-empty, unique, trimmed) — preferred — or enforce
   a strict identifier regex?
4. **Settings page:** leave the RJSF `specs` editor as-is (recommended), or hide/remove it once
   URL4 Studio ships?
5. **Per-row delete in the list** vs delete only in the detail pane (Eval Studio puts destructive
   delete in the detail pane — I followed that; confirm).
