# SF-168: Eval Studio History View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Asana:** https://app.asana.com/1/1185126988600652/task/1214568344074292
**Ticket:** SF-168 / DEMO-021 — Eval Studio history view
**Branch:** `SF-168-eval-studio-history-view` (from fresh `origin/main`)

**Goal:** Add a new top-level "Eval Studio" view to the desktop app that lists persisted evaluation runs (from `eval_runs` plugin) and shows a detail pane with per-question results and live progress for in-flight runs.

**Architecture:** State-based list/detail split inside a single top-level view (no router). Two data hooks (`useEvalRunsList`, `useEvalRunDetail`) mirror the `use-sessions.ts` pattern: each owns its fetch, returns `{ data, loading, error, refresh }`. Detail hook polls every 2s while the loaded run is `running`. Sidebar gains one more `coreItems` entry; `View` type widens with `'eval-studio'`. Status badge colors live in a small shared helper so list and detail render the same chip. Server-side routes (`GET /eval_runs`, `GET /eval_runs/{id}`) already exist — no backend work required.

**Tech Stack:** React 19 + TypeScript, lucide-react icons, Tailwind, shadcn `Button` primitives, existing `Url4Viewer`, `window.electronAPI.server.fetch` for renderer → server HTTP.

**Pre-flight (manual checklist before Task 1)**

Run these one-shot — they're not implementation steps and don't get committed:

```bash
git fetch origin && git checkout -b SF-168-eval-studio-history-view origin/main
cd apps/desktop && pnpm install   # or whatever the repo uses; check package manager
```

**API shape note (correcting the ticket draft):** the ticket's hook sketch reads `j.runs`. The actual `GET /eval_runs` returns a bare JSON array (`list[EvalRunSummaryOut]`), not `{runs: [...]}`. The plan below uses the real shape.

---

## File Structure

**Create:**
- `apps/desktop/src/renderer/src/views/EvalStudioView.tsx` — top-level view, owns `selectedRunId` state, mounts list + detail
- `apps/desktop/src/renderer/src/hooks/use-eval-runs.ts` — `useEvalRunsList` + `useEvalRunDetail` hooks; one file, two named exports
- `apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx` — left-pane runs table
- `apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx` — right-pane run header + questions table host
- `apps/desktop/src/renderer/src/components/eval/EvalQuestionsTable.tsx` — questions table for detail
- `apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx` — shared status pill (running / done / failed)
- `apps/desktop/src/renderer/src/components/eval/types.ts` — `EvalRunSummary`, `EvalRunDetail`, `EvalQuestion` shapes; mirrors `apps/server/src/screamingface/plugins/eval_runs/schemas.py`

**Modify:**
- `apps/desktop/src/renderer/src/App.tsx` — add `eval-studio` branch to `renderView()`; import `EvalStudioView`
- `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx` — widen `View` union with `'eval-studio'`; add nav entry between `'sessions'` and `'settings'`

Component boundaries are deliberately fine-grained because the questions table will grow (truncation, hover tooltip, status icon) and the runs list will gain sorting later — keep them separable now to avoid a 400-line `EvalStudioView.tsx` next quarter.

---

## Task 1: Type shapes

**Files:**
- Create: `apps/desktop/src/renderer/src/components/eval/types.ts`

- [ ] **Step 1: Write the types file**

```typescript
// apps/desktop/src/renderer/src/components/eval/types.ts
//
// Mirrors apps/server/src/screamingface/plugins/eval_runs/schemas.py.
// If the server schema changes, update both.

export type EvalRunStatus = 'running' | 'done' | 'failed';

export interface EvalRunSummary {
  id: string;
  spec_name: string;
  url4_expression: string;
  started_at: string;          // ISO 8601
  finished_at: string | null;
  status: EvalRunStatus;
  accuracy: number | null;     // 0..1
  total_questions: number | null;
  correct_questions: number | null;
  error: string | null;
}

export interface EvalQuestion {
  id: string;
  idx: number;
  question: string;
  expected: string;
  predicted: string | null;
  correct: boolean | null;
  raw_output: string | null;
  error: string | null;
}

export interface EvalRunDetail extends EvalRunSummary {
  questions: EvalQuestion[];
}
```

- [ ] **Step 2: Type-check**

Run: `cd apps/desktop && pnpm typecheck` (or `npx tsc --noEmit -p .` if no script)
Expected: PASS — no other files reference these yet, so just a compile sanity check.

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/renderer/src/components/eval/types.ts
git commit -m "SF-168: add eval-runs type shapes mirroring server schemas"
```

---

## Task 2: Data hooks

**Files:**
- Create: `apps/desktop/src/renderer/src/hooks/use-eval-runs.ts`

- [ ] **Step 1: Write the hooks**

```typescript
// apps/desktop/src/renderer/src/hooks/use-eval-runs.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import type { EvalRunDetail, EvalRunSummary } from '@/components/eval/types';

const POLL_MS = 2000;

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await window.electronAPI.server.fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}: ${res.body || res.statusText}`);
  }
  return JSON.parse(res.body) as T;
}

export function useEvalRunsList(limit = 50, offset = 0) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [data, setData] = useState<EvalRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    if (!base) return;
    setLoading(true);
    try {
      const runs = await fetchJson<EvalRunSummary[]>(
        `${base}/eval_runs?limit=${limit}&offset=${offset}`,
      );
      setData(runs);
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [base, limit, offset]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}

export function useEvalRunDetail(runId: string | null) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [data, setData] = useState<EvalRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchOnce = useCallback(async () => {
    if (!base || !runId) return null;
    const run = await fetchJson<EvalRunDetail>(`${base}/eval_runs/${runId}`);
    setData(run);
    setError(null);
    return run;
  }, [base, runId]);

  useEffect(() => {
    setData(null);
    setError(null);
    if (!runId || !base) return;

    let cancelled = false;
    setLoading(true);

    void (async () => {
      try {
        const first = await fetchOnce();
        if (cancelled) return;
        // Start polling only if the run is still in flight.
        if (first && first.status === 'running') {
          pollRef.current = setInterval(async () => {
            try {
              const next = await fetchOnce();
              if (next && next.status !== 'running' && pollRef.current) {
                clearInterval(pollRef.current);
                pollRef.current = null;
              }
            } catch (e) {
              setError(e as Error);
            }
          }, POLL_MS);
        }
      } catch (e) {
        if (!cancelled) setError(e as Error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [runId, base, fetchOnce]);

  return { data, loading, error };
}
```

- [ ] **Step 2: Type-check**

Run: `cd apps/desktop && pnpm typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/renderer/src/hooks/use-eval-runs.ts
git commit -m "SF-168: add useEvalRunsList + useEvalRunDetail hooks with live polling"
```

---

## Task 3: Status badge

**Files:**
- Create: `apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx`

- [ ] **Step 1: Write the badge**

```tsx
// apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx
import { cn } from '@/lib/utils';
import type { EvalRunStatus } from './types';

const STATUS_STYLES: Record<EvalRunStatus, string> = {
  running: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  done: 'bg-green-500/15 text-green-300 border-green-500/30',
  failed: 'bg-red-500/15 text-red-300 border-red-500/30',
};

export function EvalStatusBadge({
  status,
  className,
}: {
  status: EvalRunStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize',
        STATUS_STYLES[status],
        className,
      )}
    >
      {status}
    </span>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd apps/desktop && pnpm typecheck
git add apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx
git commit -m "SF-168: add shared EvalStatusBadge (running/done/failed)"
```

---

## Task 4: Runs list component

**Files:**
- Create: `apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx`

- [ ] **Step 1: Write the list**

```tsx
// apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx
import { cn } from '@/lib/utils';
import { useEvalRunsList } from '@/hooks/use-eval-runs';
import { EvalStatusBadge } from './EvalStatusBadge';
import type { EvalRunSummary } from './types';

interface Props {
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

export function EvalRunsList({ selectedId, onSelect }: Props) {
  const { data, loading, error } = useEvalRunsList();

  if (loading && data.length === 0) {
    return <div className="p-6 text-sm text-muted-foreground">Loading runs…</div>;
  }
  if (error) {
    return (
      <div className="p-6 text-sm text-destructive">
        Failed to load runs: {error.message}
      </div>
    );
  }
  if (data.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-8 text-center text-sm text-muted-foreground">
        <p className="mb-2 font-medium">No evaluation runs yet.</p>
        <p className="text-xs">
          Click a leaderboard entry's "Run Locally" link to start one.
        </p>
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="sticky top-0 bg-background text-xs text-muted-foreground">
        <tr className="border-b border-border">
          <th className="px-3 py-2 text-left font-medium">Started</th>
          <th className="px-3 py-2 text-left font-medium">Spec</th>
          <th className="px-3 py-2 text-left font-medium">Status</th>
          <th className="px-3 py-2 text-right font-medium">Accuracy</th>
          <th className="px-3 py-2 text-right font-medium">Correct / Total</th>
        </tr>
      </thead>
      <tbody>
        {data.map((run: EvalRunSummary) => {
          const active = run.id === selectedId;
          return (
            <tr
              key={run.id}
              onClick={() => onSelect(run.id)}
              className={cn(
                'cursor-pointer border-b border-border/50 transition-colors hover:bg-accent/40',
                active && 'bg-accent/60',
              )}
            >
              <td className="px-3 py-2 text-xs">{formatTime(run.started_at)}</td>
              <td className="px-3 py-2">{run.spec_name}</td>
              <td className="px-3 py-2">
                <EvalStatusBadge status={run.status} />
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatPercent(run.accuracy)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground">
                {run.correct_questions ?? 0} / {run.total_questions ?? 0}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd apps/desktop && pnpm typecheck
git add apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx
git commit -m "SF-168: add EvalRunsList with empty/loading/error states"
```

---

## Task 5: Questions table

**Files:**
- Create: `apps/desktop/src/renderer/src/components/eval/EvalQuestionsTable.tsx`

- [ ] **Step 1: Write the table**

```tsx
// apps/desktop/src/renderer/src/components/eval/EvalQuestionsTable.tsx
import { Check, X } from 'lucide-react';
import type { EvalQuestion } from './types';

const TRUNC = 80;

function truncate(s: string): string {
  return s.length > TRUNC ? s.slice(0, TRUNC) + '…' : s;
}

function CorrectIcon({ correct }: { correct: boolean | null }) {
  if (correct === null) return <span className="text-muted-foreground">—</span>;
  return correct ? (
    <Check className="h-4 w-4 text-green-400" />
  ) : (
    <X className="h-4 w-4 text-red-400" />
  );
}

export function EvalQuestionsTable({ questions }: { questions: EvalQuestion[] }) {
  if (questions.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        No questions recorded for this run yet.
      </div>
    );
  }
  return (
    <table className="w-full text-sm">
      <thead className="bg-muted/30 text-xs text-muted-foreground">
        <tr className="border-b border-border">
          <th className="w-10 px-3 py-2 text-right font-medium">#</th>
          <th className="px-3 py-2 text-left font-medium">Question</th>
          <th className="px-3 py-2 text-left font-medium">Expected</th>
          <th className="px-3 py-2 text-left font-medium">Predicted</th>
          <th className="w-12 px-3 py-2 text-center font-medium">✓</th>
        </tr>
      </thead>
      <tbody>
        {questions.map((q) => (
          <tr key={q.id} className="border-b border-border/50">
            <td className="px-3 py-2 text-right tabular-nums text-xs text-muted-foreground">
              {q.idx}
            </td>
            <td className="px-3 py-2" title={q.question}>
              {truncate(q.question)}
            </td>
            <td className="px-3 py-2 font-mono text-xs">{q.expected}</td>
            <td className="px-3 py-2 font-mono text-xs">
              {q.error ? (
                <span className="text-destructive" title={q.error}>error</span>
              ) : (
                q.predicted ?? <span className="text-muted-foreground">—</span>
              )}
            </td>
            <td className="px-3 py-2 text-center">
              <div className="inline-flex">
                <CorrectIcon correct={q.correct} />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd apps/desktop && pnpm typecheck
git add apps/desktop/src/renderer/src/components/eval/EvalQuestionsTable.tsx
git commit -m "SF-168: add EvalQuestionsTable with truncation + correct/error icons"
```

---

## Task 6: Detail pane

**Files:**
- Create: `apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx`

- [ ] **Step 1: Write the detail pane**

```tsx
// apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx
import { useServerStatus } from '@/hooks/use-server-status';
import { useEvalRunDetail } from '@/hooks/use-eval-runs';
import { Url4Viewer } from '@/components/Url4Viewer';
import { EvalStatusBadge } from './EvalStatusBadge';
import { EvalQuestionsTable } from './EvalQuestionsTable';

function formatPercent(accuracy: number | null): string {
  if (accuracy === null) return '—';
  return `${(accuracy * 100).toFixed(1)}%`;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`;
}

export function EvalRunDetail({ runId }: { runId: string }) {
  const { info } = useServerStatus();
  const { data, loading, error } = useEvalRunDetail(runId);

  const serverUrl = info
    ? `${info.scheme}://${info.host === '0.0.0.0' ? 'localhost' : info.host}:${info.port}`
    : '';

  if (loading && !data) {
    return <div className="p-6 text-sm text-muted-foreground">Loading run…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-destructive">Failed: {error.message}</div>;
  }
  if (!data) return null;

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border px-6 py-4">
        <div className="mb-2 flex items-center gap-3">
          <h2 className="text-base font-semibold">{data.spec_name}</h2>
          <EvalStatusBadge status={data.status} />
        </div>
        <div className="mb-3 rounded bg-muted/30 px-3 py-2">
          <Url4Viewer expression={data.url4_expression} serverUrl={serverUrl} />
        </div>
        <dl className="grid grid-cols-4 gap-3 text-xs">
          <div>
            <dt className="text-muted-foreground">Accuracy</dt>
            <dd className="font-medium tabular-nums">{formatPercent(data.accuracy)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Correct / Total</dt>
            <dd className="font-medium tabular-nums">
              {data.correct_questions ?? 0} / {data.total_questions ?? 0}
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Started</dt>
            <dd className="tabular-nums">{formatTime(data.started_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Finished</dt>
            <dd className="tabular-nums">{formatTime(data.finished_at)}</dd>
          </div>
        </dl>
        {data.error && (
          <div className="mt-3 rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {data.error}
          </div>
        )}
      </header>
      <div className="flex-1 overflow-auto">
        <EvalQuestionsTable questions={data.questions} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd apps/desktop && pnpm typecheck
git add apps/desktop/src/renderer/src/components/eval/EvalRunDetail.tsx
git commit -m "SF-168: add EvalRunDetail with header + Url4Viewer + questions table"
```

---

## Task 7: Top-level view

**Files:**
- Create: `apps/desktop/src/renderer/src/views/EvalStudioView.tsx`

- [ ] **Step 1: Write the view**

```tsx
// apps/desktop/src/renderer/src/views/EvalStudioView.tsx
import { useState } from 'react';
import { EvalRunsList } from '@/components/eval/EvalRunsList';
import { EvalRunDetail } from '@/components/eval/EvalRunDetail';

export function EvalStudioView() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-6 py-4">
        <h1 className="text-lg font-semibold text-foreground">Eval Studio</h1>
        <p className="text-xs text-muted-foreground">
          History of evaluation runs across leaderboard entries
        </p>
      </div>
      <div className="flex min-h-0 flex-1">
        <aside className="w-1/2 overflow-auto border-r border-border">
          <EvalRunsList selectedId={selectedRunId} onSelect={setSelectedRunId} />
        </aside>
        <main className="flex min-h-0 flex-1 overflow-hidden">
          {selectedRunId ? (
            <EvalRunDetail runId={selectedRunId} />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
              Select a run to see details
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd apps/desktop && pnpm typecheck
git add apps/desktop/src/renderer/src/views/EvalStudioView.tsx
git commit -m "SF-168: add EvalStudioView (list/detail split)"
```

---

## Task 8: Wire into App + Sidebar

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx`
- Modify: `apps/desktop/src/renderer/src/App.tsx`

- [ ] **Step 1: Update `View` type and add nav entry**

In `Sidebar.tsx`, change:

```typescript
export type View = 'dashboard' | 'sessions' | 'settings' | `plugin:${string}`;
```

to:

```typescript
export type View = 'dashboard' | 'sessions' | 'eval-studio' | 'settings' | `plugin:${string}`;
```

And in `coreItems`, change:

```typescript
const coreItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'sessions', label: 'Sessions', icon: Terminal },
  { id: 'settings', label: 'Settings', icon: Settings },
];
```

to (also widen the icon import to include `FlaskConical`):

```typescript
import { FlaskConical, LayoutDashboard, Settings, Puzzle, Terminal, type LucideIcon } from 'lucide-react';

const coreItems: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'sessions', label: 'Sessions', icon: Terminal },
  { id: 'eval-studio', label: 'Eval Studio', icon: FlaskConical },
  { id: 'settings', label: 'Settings', icon: Settings },
];
```

- [ ] **Step 2: Mount the view in `App.tsx`**

In `renderView()`, add a branch after the `sessions` line:

```typescript
if (currentView === 'sessions') return <SessionsView />;
if (currentView === 'eval-studio') return <EvalStudioView />;
if (currentView === 'settings') return <SettingsView />;
```

And add the import:

```typescript
import { EvalStudioView } from '@/views/EvalStudioView';
```

- [ ] **Step 3: Type-check + smoke test**

```bash
cd apps/desktop && pnpm typecheck
pnpm dev
```

Expected: app boots, sidebar shows "Eval Studio" between Sessions and Settings, clicking it renders the empty-state message ("No evaluation runs yet."), and switching back to Dashboard / Sessions / Settings still works.

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src/renderer/src/App.tsx apps/desktop/src/renderer/src/components/layout/Sidebar.tsx
git commit -m "SF-168: wire EvalStudioView into App + sidebar"
```

---

## Task 9: Manual acceptance pass

This task has no code — it's the gate before opening the PR. Run through every acceptance-criteria checkbox in the ticket and verify against a running app.

- [ ] **Step 1: Seed at least two real runs**

```bash
# from repo root
cd apps/server && uv run uvicorn screamingface.app:create_app --factory --port 8000 &
cd apps/desktop && pnpm dev
```

In the desktop app:
1. Navigate to the leaderboard area (Plugins → leaderboard, if present) or directly trigger a run via whatever DEMO-014 path is wired up locally.
2. Run two distinct entries so the list has more than one row.

- [ ] **Step 2: Walk the acceptance criteria**

For each, click through the UI and tick the box once verified:

- [ ] Sidebar has an "Eval Studio" entry
- [ ] Clicking the entry navigates to the view
- [ ] Empty state renders when no runs exist (test this by clearing `.sf/` and relaunching)
- [ ] After two runs, both appear in the list, ordered by `started_at` DESC
- [ ] Clicking a row populates the detail pane
- [ ] Detail shows: spec, expression (via Url4Viewer), accuracy, total/correct counts, status, started/finished timestamps
- [ ] Detail shows the per-question table for the run
- [ ] Status badge colors match between list and detail (use side-by-side check — list row + detail header should show the same chip)
- [ ] Live refresh: open the detail of a `running` run → questions visibly fill in (poll interval 2s; new rows appear without manual refresh)
- [ ] No regressions to Dashboard, Sessions, Settings (visit each, confirm previous behavior)

- [ ] **Step 3: Run all desktop gates locally (mirrors CI)**

```bash
cd apps/desktop
pnpm typecheck
pnpm lint
pnpm format:check   # or whatever the precommit invokes
```

Expected: all green. Note: SF-210 added `sonarjs/cognitive-complexity: 34` — none of these components should hit that, but verify by running lint.

---

## Task 10: Open PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin SF-168-eval-studio-history-view
```

- [ ] **Step 2: Open PR**

```bash
gh pr create --title "SF-168: Eval Studio history view" --body "$(cat <<'EOF'
## Summary
- New top-level "Eval Studio" view in the desktop app, listing persisted eval runs and rendering a detail pane with per-question results
- List/detail split inside a single view (no router); two data hooks (`useEvalRunsList`, `useEvalRunDetail`) mirror existing `use-sessions.ts` patterns
- Detail view polls `GET /eval_runs/{id}` every 2s while the run is in `running` status, stops automatically on terminal state
- Reuses existing `Url4Viewer` for expression rendering; shared `EvalStatusBadge` keeps list/detail chips consistent

## Test plan
- [x] Manual acceptance pass (see SF-168 plan, Task 9) — all ticket acceptance criteria verified locally
- [x] `pnpm typecheck` green
- [x] `pnpm lint` green (no sonarjs cognitive-complexity violations)
- [x] No regressions to Dashboard, Sessions, Settings, or Plugin views

Closes SF-168 / DEMO-021.
EOF
)"
```

**Stop here.** Per project rules, do NOT auto-merge; the user reviews and merges manually.

---

## Self-Review

**Spec coverage** (every acceptance criterion in the ticket maps to a task/step):
- Sidebar entry → Task 8 step 1
- Navigation → Task 8 step 2
- Empty state → Task 4 step 1
- Two runs in list, ordered DESC → server already orders by `-started_at` in `list_summaries` (Task 9 verifies)
- Click row → detail pane → Task 7 step 1 + Task 8 wiring
- Detail header fields → Task 6 step 1 (covers spec, expression, accuracy, totals, status, timestamps)
- Per-question table → Task 5 step 1 + Task 6 mount
- Status badge consistency → shared `EvalStatusBadge` (Task 3)
- Live refresh → Task 2 polling loop in `useEvalRunDetail`
- No regressions → Task 9 step 2 final check

**Placeholder scan:** All code blocks have full content; no "TBD", no "similar to above", no "add error handling" without showing it.

**Type consistency:** `EvalRunSummary`/`EvalRunDetail`/`EvalQuestion` defined once in `components/eval/types.ts`, used unchanged across hooks + components. `EvalRunStatus` union matches the server `Literal["running", "done", "failed"]`.

**Naming consistency:** `useEvalRunsList` (plural runs, list) and `useEvalRunDetail` (singular run, detail) — matches the ticket's hook sketch. Components `EvalRunsList` / `EvalRunDetail` parallel the hooks. `EvalStudioView` matches existing `*View.tsx` convention.

**One drift from the ticket draft, intentional:** the ticket's `useEvalRunsList` sketch reads `j.runs`. The real API returns the array directly (see `apps/server/src/screamingface/plugins/eval_runs/routes.py:21`). The plan uses the real shape and calls this out in the API-shape pre-flight note.
