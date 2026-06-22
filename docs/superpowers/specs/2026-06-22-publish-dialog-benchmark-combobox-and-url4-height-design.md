# Design Spec — Publish dialog: manual benchmark combobox + full-height URL4 field

- **Date:** 2026-06-22
- **Status:** Design (decisions locked with the user) → implementation plan next
- **Scope:** `apps/desktop` only. No scoreboard / IPC / server changes.

## Context

Two independent UX changes to the "Publish to Leaderboard" dialog
(`apps/desktop/src/renderer/src/components/eval/PublishToLeaderboardDialog.tsx`),
raised together because they touch the same dialog:

**A. Manual, filterable benchmark picker.** SF-300 made the benchmark
**auto-derived and read-only** — `deriveBenchmarkIdentity(run)` slugifies an `id`
from the run's dataset filename and pins it with a SHA-256 content signature; the
field cannot be edited. The user wants to **replace auto-derive with a manual,
filterable combobox** so they choose the benchmark themselves (decision locked).
The benchmark-list data layer already exists: `useKnownBenchmarks()` →
`publish:listBenchmarks` IPC → `list-benchmarks.ts` fetches `GET /v1/benchmarks`
(main-process, CORS-exempt). It is currently used only for an advisory
"registered ✓ / not registered ⚠ did-you-mean" hint.

**B. Full-height URL4 field (single scrollbar).** The read-only URL4 expression in
the dialog renders through `Url4Field` → `Url4MonacoEditor`, which auto-grows to
content height **but caps at 360px** (`Math.min(Math.max(getContentHeight(),28),360)`
in `Url4MonacoEditor.tsx:39`). Above the cap Monaco shows its own vertical
scrollbar, so a long expression produces a nested scrollbar inside the dialog's
scroll area. The user wants the URL4 field to **grow to full content height** in
this dialog so Monaco never scrolls internally and the popup has a single
scrollbar (the dialog body).

## Decisions (locked with the user)

- Replace auto-derive with a **manual benchmark combobox** (not browse-only, not override-only).
- **Combobox = registered list + free text:** filterable dropdown of registered
  benchmarks, but the user may also type a custom id. Re-allows a 404 on an
  unregistered id — accepted; mitigated by the advisory hint (below) and by
  SF-274 surfacing the real scoreboard error.
- **Default value: blank** (`Select a benchmark` placeholder). No inherited
  derivation pre-filled — fully manual each time.
- The content **signature is still computed and sent** as `metadata.benchmark_signature`
  (honest record of what ran; forward-compatible with the pending server-side
  verification). The user picking the id does not change what the signature attests.

## Key facts (from code research)

- **No combobox primitive exists** in `components/ui/` (no command/combobox/select/
  popover). A small one must be built; the repo hand-rolls its `ui/` primitives.
- `useKnownBenchmarks(): { benchmarks: KnownBenchmark[] | null; loading }` —
  `benchmarks` is null while loading **and** when the registry is unreachable;
  callers must gate on `loading`. `KnownBenchmark` is `{ id: string; displayName: string }`.
- `checkBenchmarkRegistration(id, knownIds | null)` (in `lib/benchmark-identity.ts`)
  already returns `registered | unknown | unavailable` plus a closest-match
  `suggestion` (edit-distance). Reused as-is for the advisory hint on the current
  combobox value.
- Publish payload: `benchmark_id` is a plain string; `benchmarkSignature` rides in
  **`metadata`** only (`publish-score.ts:113`) and the scoreboard's `ScoreSubmission`
  schema does **not** validate it. The only server-side benchmark check is
  `Benchmark.exists(id=...)` → 404. So manual-pick is desktop-only.
- `Url4MonacoEditor` already auto-grows via `editor.onDidContentSizeChange` →
  `applyHeight`; the only thing forcing the inner scrollbar is the hardcoded
  `360` cap and Monaco's default wheel-capture.

## Design

### Part A — Manual benchmark combobox

**A1. New reusable primitive `components/ui/combobox.tsx`.**
A controlled, keyboard-accessible filterable input + listbox, no new deps,
brand-styled (square corners, hairline border, IBM Plex Mono for ids).

```
interface ComboboxOption { value: string; label: string }
interface ComboboxProps {
  value: string;
  onChange: (value: string) => void;       // fires on both typing and selecting
  options: ComboboxOption[];
  placeholder?: string;
  disabled?: boolean;
  'aria-label'?: string;
}
```

- Free text: the input value IS `value`; typing calls `onChange` directly (custom
  ids allowed).
- Filtering: case-insensitive substring over `option.value` **and** `option.label`.
- Open the listbox on focus/typing; close on blur, Esc, or selection.
- Keyboard: ↑/↓ move the highlighted option, Enter selects it, Esc closes.
- Selecting a row sets `value = option.value` (the id).
- Empty filtered list → no dropdown (free text still works).

**A2. Dialog wiring (`PublishToLeaderboardDialog.tsx`).**
- New state `const [benchmarkId, setBenchmarkId] = useState('')` (blank default).
- Replace the read-only identity `<div>` (lines ~247–313) with:
  ```
  <Combobox
    value={benchmarkId}
    onChange={setBenchmarkId}
    options={(knownBenchmarks ?? []).map(b => ({ value: b.id, label: b.displayName }))}
    placeholder="Select a benchmark"
    aria-label="Benchmark"
  />
  ```
- Advisory hint under the combobox, driven by the existing `registryCheck` but
  computed against `benchmarkId` (the current field value) instead of the derived
  id: ✓ "Registered benchmark" when `status==='registered'`; ⚠ "Not a registered
  scoreboard benchmark — publishing will 404 until the owner registers `<id>`.
  Did you mean `<suggestion>`?" when `'unknown'`; render nothing when
  `'unavailable'` (loading / registry down).
- Keep computing the content signature: still call `deriveBenchmarkIdentity(run)`
  (or just `computeContentSignature(run)`) so `benchmarkSignature` is available for
  the payload metadata. The derived **id is no longer surfaced** and is not a default.
- `handlePublish` sends `benchmarkId: benchmarkId.trim()` and
  `benchmarkSignature: signature` (unchanged payload shape).

**A3. Publish gating.**
```
canPublish = !blockReason                       // publish-guard (zero-question etc.)
          && benchmarkId.trim().length > 0
          && specId.trim().length > 0
          && redactionResolved
```
Drop the SF-300 `verifyIdentityConsistency` gate (the user now owns the id; a
zero-content run is already blocked by `publish-guard`). The signature becomes
best-effort metadata, not a gate.

**A4. Removed / kept.**
- Removed: read-only benchmark identity display, the `identityCheck` consistency
  gate, and the "Deriving…" state.
- Kept: `lib/benchmark-identity.ts` (still computes the signature, and
  `checkBenchmarkRegistration` is reused), `useKnownBenchmarks`,
  `list-benchmarks.ts`, the IPC — all unchanged.

### Part B — Full-height URL4 field

**B1. Opt-out of the height cap.** Add an optional prop to `Url4Field` and
`Url4MonacoEditor` controlling the upper bound of the auto-grow:

```
maxContentHeight?: number | null   // default 360 (current behavior); null = no cap (full content height)
```

In `Url4MonacoEditor.applyHeight`:
```
const lower = Math.max(editor.getContentHeight(), 28);
const h = maxContentHeight == null ? lower : Math.min(lower, maxContentHeight);
```

**B2. Let wheel events bubble.** Add `scrollbar.alwaysConsumeMouseWheel: false` to
the Monaco options so that, when the editor is at full content height (nothing to
scroll internally), the wheel scrolls the dialog body instead of being captured.
At full height with `scrollBeyondLastLine:false` the vertical scrollbar does not
render, so the inner scrollbar disappears.

**B3. Dialog usage.** The publish dialog passes `maxContentHeight={null}` to its
`Url4Field`. The wrapping `<div className="rounded bg-muted/30 px-3 py-2">` keeps
the field visually bounded; the single scrollbar is the dialog body's existing
`overflow-y-auto` (`PublishToLeaderboardDialog.tsx:169`). All other `Url4Field`
usages keep the default 360 cap (unchanged).

## Data flow

1. Dialog opens → `useKnownBenchmarks()` fetches registered benchmarks (existing).
2. User types/selects in the combobox → `benchmarkId` updates → advisory hint
   recomputes via `checkBenchmarkRegistration(benchmarkId, knownIds|null)`.
3. Publish → `benchmark_id = benchmarkId.trim()`, `metadata.benchmark_signature =`
   the computed content signature → existing `publish:submitScore` path.
4. URL4 field renders at full content height; dialog body owns the only scrollbar.

## Testing

- **`combobox.test.tsx`** (new): filters by value and label; selecting a row sets
  the value; free text passes through `onChange`; keyboard ↑/↓/Enter/Esc; empty
  filter shows no dropdown but keeps the typed value.
- **`PublishToLeaderboardDialog.test.tsx`** (extend existing): blank default →
  Publish disabled until a benchmark is chosen; typing/selecting enables it and is
  sent as `benchmark_id`; ✓ hint for a registered id, ⚠ + suggestion for an
  unknown id, nothing while the registry is loading; existing zero-question guard
  + redaction tests still pass.
- **URL4 height**: a focused `Url4MonacoEditor`/`Url4Field` test asserting
  `maxContentHeight={null}` removes the cap is hard to do under jsdom (Monaco
  doesn't lay out); cover the cap logic by extracting a tiny pure helper
  `clampEditorHeight(contentHeight, maxContentHeight)` and unit-testing it, and
  verify the visual result manually in the running app.
- Full `vitest` suite + `npm run build` green.

## Risks / open questions

- **Free-text 404 (accepted):** a typed unregistered id still 404s on publish.
  Mitigated by the advisory ⚠ hint and SF-274's verbatim error surfacing. Not
  blocked, per the user's "registered + free text" choice.
- **Monaco wheel bubbling:** `alwaysConsumeMouseWheel:false` is the documented way
  to release wheel capture; verify in-app that scrolling over the URL4 field
  scrolls the dialog.
- **Combobox a11y:** keep it minimal but correct (`role="combobox"`/`listbox`/
  `option`, `aria-expanded`, `aria-activedescendant`) so it's usable and testable.
- **Trust trade-off (acknowledged):** manual pick re-opens publishing a score under
  a benchmark the run didn't execute against — the signature still records the true
  content, but the server does not yet verify it. This reverses SF-300's lock by
  explicit user choice.

## Summary

Replace the SF-300 auto-derived, read-only benchmark field with a manual,
filterable **combobox** (registered list + free text, blank default), keeping the
content signature as payload metadata and reusing the existing registry advisory
hint. Separately, let the dialog's read-only **URL4 field grow to full content
height** (opt-out of the 360px cap + release Monaco's wheel capture) so the popup
has a single scrollbar. Desktop-only; no scoreboard or IPC changes.
