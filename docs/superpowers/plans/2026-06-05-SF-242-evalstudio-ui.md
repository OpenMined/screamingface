# SF-242 — Eval Studio: compact run row + draggable/collapsible splitter

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Redesign the desktop Eval Studio: (#2) a compact run row — spec name → date/time → status + accuracy → a no-wrap "Run Locally" control; and (#3) a draggable, collapsible split between the runs list and the detail pane so the user can see left-only, right-only, or both.

**Architecture:** `EvalRunsList.tsx`'s 6-column `<table>` becomes a flex column of compact rows (Correct/Total drops from the row — it stays in `EvalRunDetail`). `EvalStudioView.tsx`'s fixed `w-1/2` aside + `flex-1` main becomes a `react-resizable-panels` horizontal group with two `collapsible` panels (`collapsedSize=0`, `minSize=20`), a draggable handle, layout persisted via `autoSaveId`, plus header toggle buttons wired to the panels' imperative handles. A thin `components/ui/resizable.tsx` wrapper (shadcn-style, framework-neutral) styles the primitives.

**Tech Stack:** React 19, TypeScript, Tailwind, `@base-ui/react` (existing `Button`), `lucide-react` (icons), **`react-resizable-panels@^2.1.7`** (NEW), electron-vite, vitest 4 + @testing-library/react (jsdom per-file).

> **Dependency note (verified):** use the **2.x** lineage `react-resizable-panels@^2.1.7` (latest 2.x = 2.1.9; peer `react ^19` ✓). 2.x exports `PanelGroup`/`Panel`/`PanelResizeHandle`/`ImperativePanelHandle` and props `direction`/`autoSaveId`/`order`/`collapsible`/`collapsedSize`/`onCollapse`/`onExpand`, and emits `data-panel-group-direction` / `data-resize-handle-state` — exactly what the code below uses. (Do NOT install 4.x: its `Group`/`Separator`/`orientation` API is different and would break `npm run build` + tests.)

**Worktree / branch:** `/private/tmp/SF-242-evalstudio-ui` on `SF-242-evalstudio-ui` (cut from `origin/main` `1f1ef24`, which includes the merged SF-241).

**Gate (no desktop CI — local only; per project memory).** Run all from `apps/desktop`:
- `npx vitest run` — unit tests (renderer tests opt into jsdom via `// @vitest-environment jsdom`)
- `npm run build` — electron-vite/rollup build; **catches the import/link errors** (e.g. a wrong resizable API) but does NOT run `tsc`
- `npm run lint` (eslint flat, runs `--fix`) and `npm run format` (prettier)

---

## File Structure

| File | Responsibility |
|---|---|
| `apps/desktop/package.json` (Modify) | add `react-resizable-panels@^2.1.7` to `dependencies` |
| `apps/desktop/src/renderer/src/components/ui/resizable.tsx` (Create) | shadcn-style wrapper: `ResizablePanelGroup`/`ResizablePanel`/`ResizableHandle` |
| `apps/desktop/src/test-setup.ts` (Modify) | add a `ResizeObserver` polyfill for jsdom (react-resizable-panels needs it) |
| `apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx` (Modify) | table → compact rows; Correct/Total dropped |
| `apps/desktop/src/renderer/src/components/eval/EvalRunsList.test.tsx` (Modify) | keep run-locally test; add compact-row + no-table + row-select tests |
| `apps/desktop/src/renderer/src/views/EvalStudioView.tsx` (Modify) | resizable, collapsible split + header toggles |
| `apps/desktop/src/renderer/src/views/EvalStudioView.test.tsx` (Create) | smoke test: header, empty state, both pane toggles |

---

## Task 1: Dependency + resizable primitive + jsdom polyfill

**Files:** `package.json`, `components/ui/resizable.tsx` (create), `src/test-setup.ts` (modify).

- [ ] **Step 1: Install the dependency** (from `apps/desktop`)

```bash
cd /private/tmp/SF-242-evalstudio-ui/apps/desktop && npm install react-resizable-panels@^2.1.7
```
Expected: `package.json` gains `"react-resizable-panels": "^2.1.7"` and `package-lock.json` resolves 2.1.x (≈2.1.9). No `@types/*` needed (ships its own types).

- [ ] **Step 2: Create the wrapper** `src/renderer/src/components/ui/resizable.tsx`:

```tsx
import { GripVertical } from 'lucide-react';
import type { ComponentProps } from 'react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';

import { cn } from '@/lib/utils';

function ResizablePanelGroup({ className, ...props }: ComponentProps<typeof PanelGroup>) {
  return (
    <PanelGroup
      data-slot="resizable-panel-group"
      className={cn('flex h-full w-full data-[panel-group-direction=vertical]:flex-col', className)}
      {...props}
    />
  );
}

function ResizablePanel({ className, ...props }: ComponentProps<typeof Panel>) {
  return <Panel data-slot="resizable-panel" className={cn('min-h-0 min-w-0', className)} {...props} />;
}

function ResizableHandle({
  withHandle,
  className,
  ...props
}: ComponentProps<typeof PanelResizeHandle> & { withHandle?: boolean }) {
  return (
    <PanelResizeHandle
      data-slot="resizable-handle"
      className={cn(
        'relative flex w-px items-center justify-center bg-border outline-none transition-colors',
        'focus-visible:ring-3 focus-visible:ring-ring/50',
        'after:absolute after:inset-y-0 after:left-1/2 after:w-2 after:-translate-x-1/2',
        'hover:bg-ring data-[resize-handle-state=drag]:bg-ring',
        'data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full',
        'data-[panel-group-direction=vertical]:after:inset-x-0 data-[panel-group-direction=vertical]:after:h-2 data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:translate-x-0 data-[panel-group-direction=vertical]:after:-translate-y-1/2',
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className="z-10 flex h-5 w-3 items-center justify-center rounded-xs border border-border bg-border">
          <GripVertical className="size-2.5 text-muted-foreground" />
        </div>
      )}
    </PanelResizeHandle>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
```

- [ ] **Step 3: Add the ResizeObserver polyfill** — append to `src/test-setup.ts` (read it first; it currently only aliases `jest`→`vi`):

```ts
// Polyfill ResizeObserver for jsdom (required by react-resizable-panels).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).ResizeObserver =
  (globalThis as any).ResizeObserver ||
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
```

- [ ] **Step 4: Verify the dep + wrapper resolve** (this is the check that catches a wrong API/version)

Run: `cd /private/tmp/SF-242-evalstudio-ui/apps/desktop && npm run build`
Expected: build succeeds. (If it fails with `"PanelGroup" is not exported by …react-resizable-panels`, the wrong major was installed — reinstall `@^2.1.7`.)

Run: `npx vitest run` → existing tests still pass (no behavior changed yet).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/package.json apps/desktop/package-lock.json apps/desktop/src/renderer/src/components/ui/resizable.tsx apps/desktop/src/test-setup.ts
git commit -m "feat(desktop): add react-resizable-panels + ui/resizable wrapper + jsdom polyfill (SF-242)"
```

---

## Task 2: EvalRunsList — compact rows

**Files:** `components/eval/EvalRunsList.tsx`, `components/eval/EvalRunsList.test.tsx`.

- [ ] **Step 1: Add the failing test** — append to `EvalRunsList.test.tsx` (keep the existing `it(...)` run-locally test unchanged):

```tsx
it('renders compact rows (not a table) with spec name, date, status, accuracy', () => {
  render(<EvalRunsList selectedId={null} onSelect={vi.fn()} onRunLocally={vi.fn()} />);
  expect(screen.queryByRole('table')).toBeNull();
  expect(screen.getByText('HLE')).toBeTruthy();
  expect(screen.getByText(/done/i)).toBeTruthy();
  expect(screen.getByText('90.0%')).toBeTruthy();
});

it('selects the run when the row is clicked', () => {
  const onSelect = vi.fn();
  render(<EvalRunsList selectedId={null} onSelect={onSelect} onRunLocally={vi.fn()} />);
  fireEvent.click(screen.getByText('HLE'));
  expect(onSelect).toHaveBeenCalledWith('r1');
});
```

- [ ] **Step 2: Run and confirm FAIL**

Run: `npx vitest run src/renderer/src/components/eval/EvalRunsList.test.tsx`
Expected: the new `not a table` test FAILS — the current implementation renders a `<table>`, so `queryByRole('table')` is non-null. (`90.0%`/`HLE`/`done` happen to be present in the table too; the `table` assertion is the red.)

- [ ] **Step 3: Replace the table with compact rows** — overwrite `EvalRunsList.tsx` with:

```tsx
import { cn } from '@/lib/utils';
import { useEvalRunsList } from '@/hooks/use-eval-runs';
import { EvalStatusBadge } from './EvalStatusBadge';
import type { EvalRunSummary } from './types';
import type { RunPayload } from '@/components/run/types';

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRunLocally?: (payload: RunPayload) => void;
}

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function EvalRunsList({ selectedId, onSelect, onRunLocally }: Props) {
  const { data, loading, error } = useEvalRunsList();

  if (loading && data.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">Failed to load runs: {error.message}</div>;
  }
  if (data.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No evaluation runs yet.</p>
        <p className="text-xs">Click a leaderboard entry's "Run Locally" link to start one.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {data.map((run: EvalRunSummary) => {
        const active = run.id === selectedId;
        return (
          <div
            key={run.id}
            onClick={() => onSelect(run.id)}
            className={cn(
              'cursor-pointer border-b border-border/50 px-3 py-3 transition-colors hover:bg-accent/40',
              active && 'bg-accent/60',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium text-foreground">{run.spec_name}</div>
                <div className="text-xs text-muted-foreground">{formatTime(run.started_at)}</div>
              </div>
              <div className="flex items-center gap-2 whitespace-nowrap">
                <EvalStatusBadge status={run.status} />
                <div className="text-right text-sm tabular-nums">{formatPercent(run.accuracy)}</div>
                {onRunLocally && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRunLocally({ spec: run.spec_name, expression: run.url4_expression });
                    }}
                    className="whitespace-nowrap text-xs text-primary underline"
                  >
                    Run Locally
                  </button>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run and confirm PASS**

Run: `npx vitest run src/renderer/src/components/eval/EvalRunsList.test.tsx`
Expected: all pass — existing run-locally test (the `<button>Run Locally</button>` + `stopPropagation` + payload are preserved), the no-table compact-row test, and row-select.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx apps/desktop/src/renderer/src/components/eval/EvalRunsList.test.tsx
git commit -m "feat(desktop): compact Eval Studio run rows, drop Correct/Total from list (SF-242)"
```

---

## Task 3: EvalStudioView — draggable/collapsible split

**Files:** `views/EvalStudioView.tsx`, `views/EvalStudioView.test.tsx` (create).

- [ ] **Step 1: Add the failing test** — create `src/renderer/src/views/EvalStudioView.test.tsx`:

```tsx
// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { it, expect, vi, afterEach } from 'vitest';

vi.mock('@/hooks/use-eval-runs', () => ({
  useEvalRunsList: () => ({ data: [], loading: false, error: null }),
}));
vi.mock('@/components/eval/EvalRunDetail', () => ({ EvalRunDetail: () => null }));

afterEach(cleanup);

import { EvalStudioView } from './EvalStudioView';

it('renders header, empty state, and both pane toggles', () => {
  render(<EvalStudioView />);
  expect(screen.getByText('Eval Studio')).toBeTruthy();
  expect(screen.getByText('Select a run to see details')).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide runs list/i })).toBeTruthy();
  expect(screen.getByRole('button', { name: /hide run details/i })).toBeTruthy();
});
```

- [ ] **Step 2: Run and confirm FAIL**

Run: `npx vitest run src/renderer/src/views/EvalStudioView.test.tsx`
Expected: FAIL — the current `EvalStudioView` has no pane-toggle buttons, so `getByRole('button', { name: /hide runs list/i })` throws.

- [ ] **Step 3: Rewrite `EvalStudioView.tsx`** with:

```tsx
import { useRef, useState } from 'react';
import type { ImperativePanelHandle } from 'react-resizable-panels';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { Button } from '@/components/ui/button';
import { EvalRunsList } from '@/components/eval/EvalRunsList';
import { EvalRunDetail } from '@/components/eval/EvalRunDetail';
import type { RunPayload } from '@/components/run/types';

interface EvalStudioViewProps {
  onRunLocally?: (payload: RunPayload) => void;
}

export function EvalStudioView({ onRunLocally }: EvalStudioViewProps = {}) {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const leftPanelRef = useRef<ImperativePanelHandle>(null);
  const rightPanelRef = useRef<ImperativePanelHandle>(null);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const toggleLeft = () => {
    const panel = leftPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };

  const toggleRight = () => {
    const panel = rightPanelRef.current;
    if (!panel) return;
    if (panel.isCollapsed()) panel.expand();
    else panel.collapse();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Eval Studio</h1>
          <p className="text-xs text-muted-foreground">
            History of evaluation runs across leaderboard entries
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={leftCollapsed ? 'Show runs list' : 'Hide runs list'}
            aria-pressed={leftCollapsed}
            onClick={toggleLeft}
          >
            {leftCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={rightCollapsed ? 'Show run details' : 'Hide run details'}
            aria-pressed={rightCollapsed}
            onClick={toggleRight}
          >
            {rightCollapsed ? <PanelRightOpen /> : <PanelRightClose />}
          </Button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" autoSaveId="eval-studio-split" className="min-h-0 flex-1">
        <ResizablePanel
          ref={leftPanelRef}
          id="eval-runs-list"
          order={1}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setLeftCollapsed(true)}
          onExpand={() => setLeftCollapsed(false)}
          className="overflow-auto"
        >
          <EvalRunsList selectedId={selectedRunId} onSelect={setSelectedRunId} onRunLocally={onRunLocally} />
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          ref={rightPanelRef}
          id="eval-run-detail"
          order={2}
          collapsible
          collapsedSize={0}
          minSize={20}
          defaultSize={50}
          onCollapse={() => setRightCollapsed(true)}
          onExpand={() => setRightCollapsed(false)}
          className="flex overflow-hidden"
        >
          {selectedRunId ? (
            <EvalRunDetail runId={selectedRunId} />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a run to see details
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
```

- [ ] **Step 4: Run and confirm PASS**

Run: `npx vitest run src/renderer/src/views/EvalStudioView.test.tsx`
Expected: PASS (the ResizeObserver polyfill from Task 1 covers the panels).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/views/EvalStudioView.tsx apps/desktop/src/renderer/src/views/EvalStudioView.test.tsx
git commit -m "feat(desktop): draggable/collapsible Eval Studio split with pane toggles (SF-242)"
```

---

## Task 4: Full gate + PR

**Files:** none (verification).

- [ ] **Step 1: Full test run** — `cd apps/desktop && npx vitest run` → all pass.
- [ ] **Step 2: Build** — `npm run build` → succeeds (confirms the resizable import surface + the whole renderer bundle).
- [ ] **Step 3: Lint + format** — `npm run lint` then `npm run format`. If either modifies files, re-stage and amend the relevant commit. (eslint flat config gates: `sonarjs/no-identical-functions`, `sonarjs/cognitive-complexity` — the two toggle fns differ textually so they won't trip it; no import-order plugin.)
- [ ] **Step 4: Open PR** via superpowers:finishing-a-development-branch. Body references SF-242, summarizes #2 compact row + #3 draggable/collapsible split, notes "no desktop CI — validated locally (vitest + build + lint)". **Do NOT merge.**

---

## Self-Review

**Spec coverage:** #2 compact row (name → date/time → status + accuracy → no-wrap Run Locally; Correct/Total dropped from row, retained in `EvalRunDetail.tsx:50-55`) → Task 2. #3 draggable + collapsible (left/right/both via `collapsible collapsedSize={0}` drag-to-edge + header toggles + `autoSaveId` persistence) → Tasks 1+3. ✓

**Placeholder scan:** full file contents + exact commands; dependency pinned to the correct major (`^2.1.7`) with the API-mismatch failure mode called out. ✓

**Type/name consistency:** `ResizablePanelGroup`/`ResizablePanel`/`ResizableHandle` exported by `ui/resizable.tsx` and imported by `EvalStudioView.tsx`; `ImperativePanelHandle` (2.x) typed on both refs; the run-locally `<button>` text + `stopPropagation` + `{spec, expression}` payload are byte-for-byte the existing contract so `EvalRunsList.test.tsx`'s accessible-name assertion still passes. ✓

**Known robustness note:** the optional EvalStudioView toggle-*interaction* assertion (clicking a toggle and re-reading the label) can be flaky under jsdom (no real layout for `onCollapse`); the plan ships only the render smoke test to stay deterministic.
