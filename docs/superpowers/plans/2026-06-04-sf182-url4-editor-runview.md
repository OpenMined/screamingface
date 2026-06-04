# SF-182 — URL4 Editor in RunView (textarea baseline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user edit a leaderboard entry's URL4 expression in a textarea and re-run it as a fresh eval run, leaving the original entry untouched.

**Architecture:** A new leaf component `Url4Editor` (controlled `<textarea>` + live `Url4Viewer` preview + Reset/Re-run buttons). `RunView` gains an "Edit URL4" toggle that swaps the read-only `Url4Viewer` for `Url4Editor`; Re-run calls the existing `useEvalRun.startRun(expression)`. One defensive hook change guarantees an edited expression always starts a fresh `run_id`.

**Tech Stack:** React 19, TypeScript, Tailwind v4, Vitest + @testing-library/react (jsdom), Electron IPC (`window.electronAPI.server.fetch`).

**Branch:** `SF-182-url4-editor-runview` (already created from fresh `origin/main`).

---

## Context for the implementer

You have zero context for this codebase. Read this section before starting.

- **Desktop app** lives in `apps/desktop`. The React renderer is under `apps/desktop/src/renderer/src/`. Path alias `@/` → `apps/desktop/src/renderer/src/`.
- **RunView** (`views/RunView.tsx`) is the screen that runs a single URL4 expression. It receives a `RunPayload` (`{ spec, expression, runId? }`) and uses the `useEvalRun` hook to fire the run and poll for results. It is reached from Eval Studio's "Run Locally" button, which passes `{ spec, expression }` (NO `runId`).
- **`Url4Viewer`** (`components/Url4Viewer.tsx`) renders a URL4 expression read-only with syntax highlighting. It debounces a `GET {serverUrl}/ensemble/highlight?q=<expr>` request and **falls back to plain monospace text on any error** — so it never throws on invalid input and needs no external validation. Props: `{ expression, serverUrl, mode?, fetchFn?, className? }`.
- **`useEvalRun`** (`hooks/use-eval-run.ts`) exposes `{ run, runState, startRun }`. `startRun(expressionOverride?: string)` **already accepts an optional expression** (the "minor signature change" the ticket anticipated is already done). It fires `GET {base}/ensemble?q=<expr>` with headers `X-SF-Run-Id` and `X-SF-Run-Spec`, then polls `{base}/eval_runs/<runId>`.
- **No `test` script exists** in `apps/desktop/package.json`. Run tests with `npx vitest run <path>` from inside `apps/desktop`. Vitest config provides globals + jsdom; each test file also has a `// @vitest-environment jsdom` pragma on line 1.
- **Pre-commit / commit hooks:** husky + lint-staged run `eslint --fix` then `prettier --write` on staged `*.ts`/`*.tsx`. Just `git commit` — the hook formats staged files. If it reformats, the commit still succeeds (it amends staged content); re-run `git add` only if the hook reports it modified files and the commit aborts.

### Design decisions (deviations from the ticket's sketch — read these)

The Asana ticket includes a component sketch with two pieces of state that are **dead** and are intentionally omitted:

1. **`const [valid, setValid] = useState(true)`** in `Url4Editor` — `setValid` is never called and `Url4Viewer` exposes no validity signal to its parent. Re-run is instead gated on **non-empty trimmed text**. (YAGNI.)
2. **`const [editedExpression, setEditedExpression] = useState(...)`** in `RunView` — in the sketch it is set but never read. The editor's own internal `text` state already provides "edited state separate from the deep-link expression," and the original is always `payload.expression`. (YAGNI + "extend, don't invent.")

One **addition** beyond the sketch, to satisfy the explicit "fresh run_id" acceptance criterion robustly: `startRun` is changed so that **passing an expression override always mints a fresh `run_id`** (today it only does so when `payload.runId` is unset). See Task 2.

---

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `apps/desktop/src/renderer/src/components/Url4Editor.tsx` | Textarea editor + live preview + Reset/Re-run | **Create** |
| `apps/desktop/src/renderer/src/components/Url4Editor.test.tsx` | Unit tests for the editor | **Create** |
| `apps/desktop/src/renderer/src/hooks/use-eval-run.ts` | Force fresh `run_id` on expression override | **Modify** (line 51) |
| `apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts` | Test the fresh-id-on-override behavior | **Modify** (append one test) |
| `apps/desktop/src/renderer/src/views/RunView.tsx` | "Edit URL4" toggle mounting `Url4Editor` | **Modify** |
| `apps/desktop/src/renderer/src/views/RunView.test.tsx` | Test the toggle + re-run wiring | **Modify** (append one test) |

---

## Task 1: `Url4Editor` component

**Files:**
- Create: `apps/desktop/src/renderer/src/components/Url4Editor.tsx`
- Test: `apps/desktop/src/renderer/src/components/Url4Editor.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/renderer/src/components/Url4Editor.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

// Mock Url4Viewer so the editor test never hits the highlight endpoint;
// echo the expression so we can assert the preview tracks the textarea.
vi.mock('@/components/Url4Viewer', () => ({
  Url4Viewer: ({ expression }: { expression: string }) => (
    <code data-testid="preview">{expression}</code>
  ),
}));

afterEach(cleanup);

import { Url4Editor } from './Url4Editor';

const initial = '/claude(hi)!answer';

it('prefills the textarea with the initial expression', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(textarea.value).toBe(initial);
});

it('updates the live preview as the user types', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '/codex(yo)!answer' } });
  expect(screen.getByTestId('preview').textContent).toBe('/codex(yo)!answer');
});

it('Reset is disabled when unchanged and restores the original after edits', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const reset = screen.getByRole('button', { name: /reset/i }) as HTMLButtonElement;
  expect(reset.disabled).toBe(true);
  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  fireEvent.change(textarea, { target: { value: 'edited' } });
  expect(reset.disabled).toBe(false);
  fireEvent.click(reset);
  expect(textarea.value).toBe(initial);
  expect(reset.disabled).toBe(true);
});

it('Re-run calls onRun with the current text', () => {
  const onRun = vi.fn();
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={onRun} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '/gemini(q)!a' } });
  fireEvent.click(screen.getByRole('button', { name: /re-run/i }));
  expect(onRun).toHaveBeenCalledWith('/gemini(q)!a');
});

it('Re-run is disabled when the expression is blank', () => {
  render(<Url4Editor initial={initial} serverUrl="http://x" onRun={vi.fn()} />);
  const textarea = screen.getByLabelText(/url4 expression editor/i);
  fireEvent.change(textarea, { target: { value: '   ' } });
  const rerun = screen.getByRole('button', { name: /re-run/i }) as HTMLButtonElement;
  expect(rerun.disabled).toBe(true);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/components/Url4Editor.test.tsx`
Expected: FAIL — `Failed to resolve import "./Url4Editor"` / `Url4Editor is not defined`.

- [ ] **Step 3: Write the component**

Create `apps/desktop/src/renderer/src/components/Url4Editor.tsx`:

```tsx
import { useState } from 'react';
import { Url4Viewer } from '@/components/Url4Viewer';

interface Url4EditorProps {
  initial: string;
  serverUrl: string;
  onRun: (expression: string) => void;
}

export function Url4Editor({ initial, serverUrl, onRun }: Url4EditorProps) {
  const [text, setText] = useState(initial);
  const isBlank = text.trim() === '';

  return (
    <div className="flex flex-col gap-3">
      <textarea
        aria-label="URL4 expression editor"
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        className="min-h-[120px] rounded-md border border-border bg-background p-3 font-mono text-sm"
      />
      <div className="text-xs text-muted-foreground">Preview</div>
      <div className="rounded-md border border-border p-3">
        <Url4Viewer expression={text} serverUrl={serverUrl} mode="expanded" />
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => setText(initial)}
          disabled={text === initial}
          className="self-start rounded-md border border-border px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={() => onRun(text)}
          disabled={isBlank}
          className="self-start rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          Re-run
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/components/Url4Editor.test.tsx`
Expected: PASS — 5 tests.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/Url4Editor.tsx \
        apps/desktop/src/renderer/src/components/Url4Editor.test.tsx
git commit -m "feat(desktop): add Url4Editor component (SF-182)"
```

---

## Task 2: Guarantee a fresh `run_id` when an expression override is supplied

**Files:**
- Modify: `apps/desktop/src/renderer/src/hooks/use-eval-run.ts:51`
- Test: `apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts` (append one test)

**Why:** Re-run must always create a *new* eval run. Today `startRun` reuses `payload.runId` when it is set (e.g. a future deep-link payload), which would collide with the original run. When the caller passes an explicit `expressionOverride`, that signals "a different run" → mint a fresh id.

- [ ] **Step 1: Write the failing test**

Append to `apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts`:

```ts
it('mints a fresh run_id when an edited expression override is supplied', async () => {
  fetchMock.mockResolvedValue({ ok: false, status: 0, body: '' });
  const pinned = { spec: 'HLE', expression: 'a(b)', runId: 'pinned-id' };
  const { result } = renderHook(() => useEvalRun(pinned));

  // No override -> reuses the pinned deep-link run id.
  act(() => result.current.startRun());
  const plainCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('/ensemble?q='));
  expect(plainCall?.[1].headers['X-SF-Run-Id']).toBe('pinned-id');

  // Override (edited expression) -> fresh id, never the pinned one.
  act(() => result.current.startRun('edited(expr)'));
  const editedCall = fetchMock.mock.calls.find((c) => String(c[0]).includes('edited'));
  const editedId = editedCall?.[1].headers['X-SF-Run-Id'];
  expect(editedId).toBeTruthy();
  expect(editedId).not.toBe('pinned-id');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/hooks/use-eval-run.test.ts`
Expected: FAIL — the override call's `X-SF-Run-Id` equals `'pinned-id'` (current code reuses `payload.runId`).

- [ ] **Step 3: Make the change**

In `apps/desktop/src/renderer/src/hooks/use-eval-run.ts`, replace line 51:

```ts
      const runId = payload.runId ?? crypto.randomUUID();
```

with:

```ts
      // An edited expression is always a new run, so never reuse a pinned
      // (deep-link) runId for it; mint a fresh one.
      const runId =
        expressionOverride !== undefined
          ? crypto.randomUUID()
          : (payload.runId ?? crypto.randomUUID());
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/hooks/use-eval-run.test.ts`
Expected: PASS — 3 tests (the 2 existing + the new one).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/hooks/use-eval-run.ts \
        apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts
git commit -m "fix(desktop): fresh run_id for edited-expression re-runs (SF-182)"
```

---

## Task 3: Wire `Url4Editor` into `RunView` behind an "Edit URL4" toggle

**Files:**
- Modify: `apps/desktop/src/renderer/src/views/RunView.tsx`
- Test: `apps/desktop/src/renderer/src/views/RunView.test.tsx` (append one test)

- [ ] **Step 1: Write the failing test**

Append to `apps/desktop/src/renderer/src/views/RunView.test.tsx` (the file already mocks `@/components/Url4Viewer`, which transitively mocks the viewer used inside `Url4Editor`):

```tsx
it('toggles to the URL4 editor and re-runs with the edited expression', () => {
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={vi.fn()} />);

  fireEvent.click(screen.getByRole('button', { name: /edit url4/i }));

  const textarea = screen.getByLabelText(/url4 expression editor/i) as HTMLTextAreaElement;
  expect(textarea.value).toBe('transform(url, intent)');

  fireEvent.change(textarea, { target: { value: 'edited(expr)!go' } });
  fireEvent.click(screen.getByRole('button', { name: /re-run/i }));
  expect(startRun).toHaveBeenCalledWith('edited(expr)!go');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/views/RunView.test.tsx`
Expected: FAIL — no button matching `/edit url4/i`.

- [ ] **Step 3: Modify `RunView`**

Edit `apps/desktop/src/renderer/src/views/RunView.tsx`. Add the `useState` import and `Url4Editor` import at the top:

```tsx
import { useState } from 'react';
import { useEvalRun } from '@/hooks/use-eval-run';
import { Url4Viewer } from '@/components/Url4Viewer';
import { Url4Editor } from '@/components/Url4Editor';
import { RunButton } from '@/components/run/RunButton';
import { RunProgress } from '@/components/run/RunProgress';
import type { RunPayload } from '@/components/run/types';
```

Add the toggle state inside the component (after the `useEvalRun` line):

```tsx
export function RunView({ payload, serverUrl, onViewEvalStudio }: RunViewProps) {
  const { run, runState, startRun } = useEvalRun(payload);
  const [editing, setEditing] = useState(false);
```

Replace the existing expression `<section>` (lines 23–26) with:

```tsx
      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="text-xs text-muted-foreground">URL4 expression</div>
          <button
            type="button"
            onClick={() => setEditing((e) => !e)}
            className="text-sm text-primary underline"
          >
            {editing ? 'Cancel edit' : 'Edit URL4'}
          </button>
        </div>
        {editing ? (
          <Url4Editor
            initial={payload.expression}
            serverUrl={serverUrl}
            onRun={(expr) => startRun(expr)}
          />
        ) : (
          <Url4Viewer expression={payload.expression} serverUrl={serverUrl} mode="expanded" />
        )}
      </section>
```

(Leave the run/results `<section>` below it unchanged.)

- [ ] **Step 4: Run the RunView test to verify it passes**

Run (from `apps/desktop`): `npx vitest run src/renderer/src/views/RunView.test.tsx`
Expected: PASS — 4 tests (3 existing + the new one).

- [ ] **Step 5: Run the full renderer test suite + lint**

Run (from `apps/desktop`):

```bash
npx vitest run
npx eslint src/renderer/src/components/Url4Editor.tsx \
           src/renderer/src/views/RunView.tsx \
           src/renderer/src/hooks/use-eval-run.ts
```

Expected: all test files PASS; eslint reports 0 errors.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/renderer/src/views/RunView.tsx \
        apps/desktop/src/renderer/src/views/RunView.test.tsx
git commit -m "feat(desktop): Edit URL4 toggle + re-run in RunView (SF-182)"
```

---

## Acceptance criteria mapping

| Ticket criterion | Where satisfied |
| --- | --- |
| "Edit URL4" button toggles to the editor | Task 3 — header toggle button (`Edit URL4` ⇄ `Cancel edit`) |
| Editor textarea prefilled with the current expression | Task 1 `useState(initial)`; Task 3 passes `initial={payload.expression}` |
| Live preview updates as the user types | Task 1 — `Url4Viewer expression={text}` |
| Reset restores the original, disabled when unchanged | Task 1 — Reset test |
| Re-run calls `startRun` with the edited expression and a fresh `run_id` | Task 3 (`onRun={(expr) => startRun(expr)}`) + Task 2 (fresh id on override) |
| New run appears in Eval Studio as a separate entry | `startRun` fires `/ensemble?q=<edited>` with a fresh `X-SF-Run-Id` → new `eval_run` row |
| Original leaderboard run unaffected | Read-only view always shows `payload.expression`; original row keeps its own `url4_expression` |
| Manual test: edit HLE dataset path → re-run → new Eval Studio run | Manual verification below |

## Out of scope (per ticket "Notes")

Spec naming for the new run, save-as-spec, share button, expression validation messages, and `POST /url4_specs` persistence are all explicitly deferred.

## Manual verification (after merge / in `npm run dev`)

1. Open the desktop app, go to Eval Studio, click **Run Locally** on an HLE leaderboard entry → RunView opens.
2. Click **Edit URL4** → textarea appears prefilled with the expression.
3. Swap the dataset path (e.g. `https://github.com/openmined/HLE.jsonl` → `/data/private-hle/dataset.jsonl`).
4. Click **Re-run** → a run starts; progress then results appear below.
5. Open Eval Studio → a **new** run row exists with the edited `url4_expression`; the original entry is unchanged.

## Final review

After all three tasks: dispatch a code reviewer over the full diff (`git diff origin/main...HEAD`) for spec compliance + quality, then use superpowers:finishing-a-development-branch to open the PR (base `main`, title leading with `SF-182`). Do **not** auto-merge.
