# SF-167 / DEMO-020 — "Run Locally" wiring + RunView Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `RunView` in the desktop renderer that takes a URL4 expression + spec, fires a tracked eval run against the live server, and polls it to completion — unblocking SF-182 (URL4 editor) which mounts inside this view.

**Architecture:** A `useEvalRun` hook owns the run lifecycle: it fires a fire-and-forget `GET /ensemble?q=<expr>` with `X-SF-Run-Id`/`X-SF-Run-Spec` headers (which drives server-side run creation via the `HOOK_RUN_STARTED` hook), then polls `GET /eval_runs/{id}` every 2s as the source of truth until `done`/`failed`. `RunView` renders the expression (existing `Url4Viewer`), a `RunButton`, and progress/result/error UI. `App.tsx` holds a `runPayload` state and renders `RunView` when set; the interim entry point is a "Run Locally" button on each Eval Studio run row (the real leaderboard deep-link arrives later in DEMO-018).

**Tech Stack:** React + TypeScript, Vite renderer, `window.electronAPI.server.fetch`, vitest + @testing-library/react.

---

## Context the implementer must know

- **Run creation is implicit, server-side.** There is **no** `POST /eval_runs`. A run row is created when `GET /ensemble` is called with header `X-SF-Run-Id` (and optional `X-SF-Run-Spec`). See `apps/server/src/screamingface/plugins/url4_executor/routes.py:104-116` — it emits `HOOK_RUN_STARTED` immediately on request arrival, and `eval_runs/plugin.py` writes the row. So the row exists almost immediately; polling tracks it.
- **All renderer→server calls go through `window.electronAPI.server.fetch(url, init?)`**, NOT plain `fetch`. Signature (`apps/desktop/src/preload/types.ts:196-199`):
  ```ts
  fetch: (url: string, init?: { method?: string; body?: string; headers?: Record<string, string> })
    => Promise<{ ok: boolean; status: number; body: string }>
  ```
  The main process injects the Desktop secret and runs an allow-list check; same-origin `/ensemble` and `/eval_runs` are allowed (same host:port as the working `/eval_runs` calls today).
- **The main-side fetch times out at 5s** (`server-process.ipc.ts:27`). The `/ensemble` call usually outlives that, so it will reject/`ok:false` client-side. **This is expected** — uvicorn does not cancel the handler on client disconnect, so the run completes server-side. **Never** turn an `/ensemble` fetch rejection into a `failed` run state; only the polled `status` decides.
- **Exact run statuses** (`eval_runs/schemas.py:11`): `'running' | 'done' | 'failed'`. Already mirrored in `apps/desktop/src/renderer/src/components/eval/types.ts:6`.
- **Run fields for progress/result** (`components/eval/types.ts:8-19`): `accuracy` (0..1 | null), `total_questions`, `correct_questions`, `error`.
- **Server base URL** is derived from `useServerStatus().info` as `${scheme}://${host==='0.0.0.0'?'localhost':host}:${port}`. There is a private `serverBase(info)` helper in `use-eval-runs.ts:8`.
- **`Url4Viewer` props** (`components/Url4Viewer.tsx:9-15`): `{ expression, serverUrl, fetchFn?, mode?, className? }`. It degrades to plain text on invalid/failed highlight — no extra validation needed.
- **`View` union** lives in `components/layout/Sidebar.tsx:14` and is re-exported/imported by `App.tsx:3`.
- **`startRun` takes an optional expression override** (`startRun(expression?: string)`). This is a deliberate, zero-cost forward design so SF-182's editor can call `startRun(editedExpression)` without changing the hook. SF-167 itself only uses the no-arg form.

## Scope & non-goals

- **In scope:** `useEvalRun` hook, `RunView`, `RunButton`, `RunProgress`, App wiring + payload state, a guarded deep-link listener stub, and the interim "Run Locally" entry on Eval Studio rows.
- **Out of scope (deferred):** DEMO-018 custom-protocol deep-link registration (the production trigger — only a guarded stub here), any URL4 editing (that is SF-182), saving expressions to `url4_specs`, sidebar nav entry for RunView.
- **Deferred acceptance criterion:** "Deep-link arriving via DEMO-018 routes into RunView" cannot be satisfied until DEMO-018 lands. The hook/view are built deep-link-ready (App consumes a `RunPayload`); the interim Eval Studio entry covers manual testing now.

## File Structure

- **Create** `apps/desktop/src/renderer/src/components/run/types.ts` — `RunPayload`, `RunState`.
- **Create** `apps/desktop/src/renderer/src/hooks/use-eval-run.ts` — run lifecycle hook.
- **Create** `apps/desktop/src/renderer/src/components/run/RunButton.tsx` — run trigger button.
- **Create** `apps/desktop/src/renderer/src/components/run/RunProgress.tsx` — in-flight progress line.
- **Create** `apps/desktop/src/renderer/src/views/RunView.tsx` — the view (result/error rendered inline).
- **Modify** `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx:14` — add `'run'` to `View`.
- **Modify** `apps/desktop/src/renderer/src/App.tsx` — `runPayload` state, render `RunView`, guarded deep-link stub, pass `onRunLocally` to Eval Studio.
- **Modify** `apps/desktop/src/renderer/src/views/EvalStudioView.tsx` + `components/eval/EvalRunsList.tsx` — interim "Run Locally" row button.
- **Tests:** co-located `*.test.ts(x)` for hook, RunButton, RunProgress, RunView.

---

### Task 1: RunPayload + RunState types

**Files:**
- Create: `apps/desktop/src/renderer/src/components/run/types.ts`

- [ ] **Step 1: Create the types file**

```ts
// apps/desktop/src/renderer/src/components/run/types.ts
// Payload that drives RunView. Today it is constructed from an existing
// eval run row (interim entry); DEMO-018 will deliver it via deep link.
export interface RunPayload {
  spec: string;
  expression: string;
  runId?: string;
}

export type RunState = 'idle' | 'running' | 'done' | 'failed';
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/desktop && npx tsc --noEmit`
Expected: PASS (no references yet).

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/renderer/src/components/run/types.ts
git commit -m "feat(desktop): add RunPayload/RunState types for RunView"
```

---

### Task 2: useEvalRun hook

**Files:**
- Create: `apps/desktop/src/renderer/src/hooks/use-eval-run.ts`
- Test: `apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts
// @vitest-environment jsdom
import { renderHook, act, waitFor, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const fetchMock = vi.fn();

vi.mock('@/hooks/use-server-status', () => ({
  useServerStatus: () => ({
    status: 'ready',
    info: { scheme: 'http', host: '127.0.0.1', port: 8001 },
  }),
}));

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  (window as unknown as { electronAPI: unknown }).electronAPI = {
    server: { fetch: fetchMock },
  };
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  cleanup();
});

import { useEvalRun } from './use-eval-run';

const payload = { spec: 'HLE', expression: 'transform(url, intent)' };

it('fires /ensemble with run headers and polls /eval_runs to done', async () => {
  // 1st call: /ensemble (fire-and-forget). Subsequent: /eval_runs/{id}.
  fetchMock
    .mockResolvedValueOnce({ ok: false, status: 0, body: '' }) // ensemble (times out, ignored)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: JSON.stringify({ status: 'running', correct_questions: 1, total_questions: 4 }),
    })
    .mockResolvedValue({
      ok: true,
      status: 200,
      body: JSON.stringify({
        status: 'done',
        accuracy: 0.75,
        correct_questions: 3,
        total_questions: 4,
      }),
    });

  const { result } = renderHook(() => useEvalRun(payload));
  expect(result.current.runState).toBe('idle');

  act(() => result.current.startRun());
  expect(result.current.runState).toBe('running');

  // ensemble call carried the tracking headers
  const ensembleCall = fetchMock.mock.calls[0];
  expect(ensembleCall[0]).toContain('/ensemble?q=');
  expect(ensembleCall[1].headers['X-SF-Run-Spec']).toBe('HLE');
  expect(ensembleCall[1].headers['X-SF-Run-Id']).toBeTruthy();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  await waitFor(() => expect(result.current.runState).toBe('done'));
  expect(result.current.run?.accuracy).toBe(0.75);
});

it('does not mark failed when the ensemble fetch rejects (run drives state via poll)', async () => {
  fetchMock
    .mockRejectedValueOnce(new Error('timeout')) // ensemble
    .mockResolvedValue({
      ok: true,
      status: 200,
      body: JSON.stringify({ status: 'running', total_questions: 4, correct_questions: 0 }),
    });

  const { result } = renderHook(() => useEvalRun(payload));
  await act(async () => {
    result.current.startRun();
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(result.current.runState).toBe('running');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/hooks/use-eval-run.test.ts`
Expected: FAIL — `useEvalRun` not defined.

- [ ] **Step 3: Implement the hook**

```ts
// apps/desktop/src/renderer/src/hooks/use-eval-run.ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import type { EvalRunDetail } from '@/components/eval/types';
import type { RunPayload, RunState } from '@/components/run/types';

const POLL_MS = 2000;

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function useEvalRun(payload: RunPayload) {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const [run, setRun] = useState<EvalRunDetail | null>(null);
  const [runState, setRunState] = useState<RunState>('idle');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (runId: string) => {
      if (!base) return;
      const res = await window.electronAPI.server.fetch(`${base}/eval_runs/${runId}`);
      if (!res.ok) return; // 404 before row is created -> keep polling
      const fresh = JSON.parse(res.body) as EvalRunDetail;
      setRun(fresh);
      if (fresh.status === 'done') {
        setRunState('done');
        stop();
      } else if (fresh.status === 'failed') {
        setRunState('failed');
        stop();
      }
    },
    [base, stop],
  );

  const startRun = useCallback(
    (expressionOverride?: string) => {
      if (!base) return;
      const expression = expressionOverride ?? payload.expression;
      const runId = payload.runId ?? crypto.randomUUID();
      setRun(null);
      setRunState('running');
      // Fire-and-forget: this drives server-side run creation. The main-side
      // fetch times out at 5s but the run continues; polling is the truth.
      void window.electronAPI.server.fetch(
        `${base}/ensemble?q=${encodeURIComponent(expression)}`,
        { headers: { 'X-SF-Run-Id': runId, 'X-SF-Run-Spec': payload.spec } },
      );
      stop();
      pollRef.current = setInterval(() => void poll(runId), POLL_MS);
      void poll(runId);
    },
    [base, payload, poll, stop],
  );

  useEffect(() => stop, [stop]);

  return { run, runState, startRun };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/hooks/use-eval-run.test.ts`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/hooks/use-eval-run.ts apps/desktop/src/renderer/src/hooks/use-eval-run.test.ts
git commit -m "feat(desktop): add useEvalRun hook (fire /ensemble + poll /eval_runs)"
```

---

### Task 3: RunButton component

**Files:**
- Create: `apps/desktop/src/renderer/src/components/run/RunButton.tsx`
- Test: `apps/desktop/src/renderer/src/components/run/RunButton.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/desktop/src/renderer/src/components/run/RunButton.test.tsx
// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { RunButton } from './RunButton';

afterEach(cleanup);

it('is enabled when idle and calls onRun', () => {
  const onRun = vi.fn();
  render(<RunButton state="idle" onRun={onRun} />);
  const btn = screen.getByRole('button', { name: /run locally/i });
  expect(btn).not.toBeDisabled();
  fireEvent.click(btn);
  expect(onRun).toHaveBeenCalledTimes(1);
});

it('is disabled while running', () => {
  render(<RunButton state="running" onRun={vi.fn()} />);
  expect(screen.getByRole('button')).toBeDisabled();
});

it('shows "Run again" label when done', () => {
  render(<RunButton state="done" onRun={vi.fn()} />);
  expect(screen.getByRole('button', { name: /run again/i })).not.toBeDisabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/run/RunButton.test.tsx`
Expected: FAIL — `RunButton` not defined.

- [ ] **Step 3: Implement RunButton**

```tsx
// apps/desktop/src/renderer/src/components/run/RunButton.tsx
import type { RunState } from './types';

export function RunButton({ state, onRun }: { state: RunState; onRun: () => void }) {
  const running = state === 'running';
  const label = state === 'done' || state === 'failed' ? 'Run again' : 'Run Locally';
  return (
    <button
      type="button"
      onClick={onRun}
      disabled={running}
      className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
    >
      {running ? 'Running…' : label}
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/run/RunButton.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/run/RunButton.tsx apps/desktop/src/renderer/src/components/run/RunButton.test.tsx
git commit -m "feat(desktop): add RunButton component"
```

---

### Task 4: RunProgress component

**Files:**
- Create: `apps/desktop/src/renderer/src/components/run/RunProgress.tsx`
- Test: `apps/desktop/src/renderer/src/components/run/RunProgress.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/desktop/src/renderer/src/components/run/RunProgress.test.tsx
// @vitest-environment jsdom
import { render, screen, cleanup } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';
import { RunProgress } from './RunProgress';
import type { EvalRunDetail } from '@/components/eval/types';

afterEach(cleanup);

const base: EvalRunDetail = {
  id: 'r1',
  spec_name: 'HLE',
  url4_expression: 'x',
  started_at: '',
  finished_at: null,
  status: 'running',
  accuracy: null,
  total_questions: 4,
  correct_questions: 2,
  error: null,
  questions: [],
};

it('renders correct/total progress', () => {
  render(<RunProgress run={base} />);
  expect(screen.getByText(/2\s*\/\s*4/)).toBeTruthy();
});

it('renders a placeholder when counts are not yet known', () => {
  render(<RunProgress run={{ ...base, total_questions: null, correct_questions: null }} />);
  expect(screen.getByText(/starting/i)).toBeTruthy();
});

it('renders nothing when run is null', () => {
  const { container } = render(<RunProgress run={null} />);
  expect(container.textContent).toBe('');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/run/RunProgress.test.tsx`
Expected: FAIL — `RunProgress` not defined.

- [ ] **Step 3: Implement RunProgress**

```tsx
// apps/desktop/src/renderer/src/components/run/RunProgress.tsx
import type { EvalRunDetail } from '@/components/eval/types';

export function RunProgress({ run }: { run: EvalRunDetail | null }) {
  if (!run) return null;
  if (run.total_questions == null || run.correct_questions == null) {
    return <div className="text-sm text-muted-foreground">Starting run…</div>;
  }
  const pct =
    run.accuracy != null
      ? ` · accuracy ${(run.accuracy * 100).toFixed(1)}%`
      : '';
  return (
    <div className="text-sm text-muted-foreground" role="status">
      {run.correct_questions} / {run.total_questions}
      {pct}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/run/RunProgress.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/run/RunProgress.tsx apps/desktop/src/renderer/src/components/run/RunProgress.test.tsx
git commit -m "feat(desktop): add RunProgress component"
```

---

### Task 5: RunView (assembles hook + components + Url4Viewer)

**Files:**
- Create: `apps/desktop/src/renderer/src/views/RunView.tsx`
- Test: `apps/desktop/src/renderer/src/views/RunView.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/desktop/src/renderer/src/views/RunView.test.tsx
// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';

const startRun = vi.fn();
let mockHook = { run: null as unknown, runState: 'idle' as string, startRun };

vi.mock('@/hooks/use-eval-run', () => ({ useEvalRun: () => mockHook }));
// Url4Viewer hits the server; stub it to a simple marker.
vi.mock('@/components/Url4Viewer', () => ({
  Url4Viewer: ({ expression }: { expression: string }) => <code>{expression}</code>,
}));

afterEach(() => {
  cleanup();
  startRun.mockReset();
  mockHook = { run: null, runState: 'idle', startRun };
});

import { RunView } from './RunView';

const payload = { spec: 'HLE', expression: 'transform(url, intent)' };

it('shows spec, expression, and a Run button that triggers startRun', () => {
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={vi.fn()} />);
  expect(screen.getByText('HLE')).toBeTruthy();
  expect(screen.getByText('transform(url, intent)')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /run locally/i }));
  expect(startRun).toHaveBeenCalledTimes(1);
});

it('shows result + eval studio link when done', () => {
  mockHook = {
    run: { status: 'done', accuracy: 0.5, correct_questions: 2, total_questions: 4 },
    runState: 'done',
    startRun,
  };
  const onViewEvalStudio = vi.fn();
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={onViewEvalStudio} />);
  expect(screen.getByText(/50(\.0)?%/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /view in eval studio/i }));
  expect(onViewEvalStudio).toHaveBeenCalled();
});

it('shows error + try again when failed', () => {
  mockHook = {
    run: { status: 'failed', error: 'boom', accuracy: null, correct_questions: null, total_questions: null },
    runState: 'failed',
    startRun,
  };
  render(<RunView payload={payload} serverUrl="http://x" onViewEvalStudio={vi.fn()} />);
  expect(screen.getByText(/boom/)).toBeTruthy();
  expect(screen.getByRole('button', { name: /run again/i })).toBeTruthy();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/views/RunView.test.tsx`
Expected: FAIL — `RunView` not defined.

- [ ] **Step 3: Implement RunView**

```tsx
// apps/desktop/src/renderer/src/views/RunView.tsx
import { useEvalRun } from '@/hooks/use-eval-run';
import { Url4Viewer } from '@/components/Url4Viewer';
import { RunButton } from '@/components/run/RunButton';
import { RunProgress } from '@/components/run/RunProgress';
import type { RunPayload } from '@/components/run/types';

interface RunViewProps {
  payload: RunPayload;
  serverUrl: string;
  onViewEvalStudio: () => void;
}

export function RunView({ payload, serverUrl, onViewEvalStudio }: RunViewProps) {
  const { run, runState, startRun } = useEvalRun(payload);

  return (
    <div className="flex max-w-3xl flex-col gap-6 p-6">
      <header>
        <div className="text-xs text-muted-foreground">Spec</div>
        <h1 className="text-xl font-semibold">{payload.spec || 'Ad-hoc run'}</h1>
      </header>

      <section>
        <div className="mb-2 text-xs text-muted-foreground">URL4 expression</div>
        <Url4Viewer expression={payload.expression} serverUrl={serverUrl} mode="expanded" />
      </section>

      <section className="flex flex-col gap-3">
        <RunButton state={runState} onRun={() => startRun()} />
        {runState === 'running' && <RunProgress run={run} />}
        {runState === 'done' && run && (
          <div className="flex flex-col gap-2">
            <div className="text-sm">
              Final accuracy:{' '}
              <span className="font-semibold">
                {run.accuracy != null ? `${(run.accuracy * 100).toFixed(1)}%` : 'n/a'}
              </span>{' '}
              ({run.correct_questions ?? 0}/{run.total_questions ?? 0})
            </div>
            <button
              type="button"
              onClick={onViewEvalStudio}
              className="self-start text-sm text-primary underline"
            >
              View in Eval Studio →
            </button>
          </div>
        )}
        {runState === 'failed' && (
          <div className="text-sm text-destructive">Run failed: {run?.error ?? 'unknown error'}</div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/desktop && npx vitest run src/renderer/src/views/RunView.test.tsx`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/views/RunView.tsx apps/desktop/src/renderer/src/views/RunView.test.tsx
git commit -m "feat(desktop): add RunView assembling run hook + progress/result UI"
```

---

### Task 6: Wire RunView into App + add 'run' to View union

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx:14`
- Modify: `apps/desktop/src/renderer/src/App.tsx`

- [ ] **Step 1: Add 'run' to the View union**

In `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx`, change line 14 from:

```ts
export type View = 'dashboard' | 'sessions' | 'eval-studio' | 'settings' | `plugin:${string}`;
```

to:

```ts
export type View = 'dashboard' | 'sessions' | 'eval-studio' | 'run' | 'settings' | `plugin:${string}`;
```

- [ ] **Step 2: Add runPayload state, render RunView, guarded deep-link stub, and onRunLocally**

In `apps/desktop/src/renderer/src/App.tsx`, add the import near the other view imports (after line 6):

```tsx
import { RunView } from '@/views/RunView';
import type { RunPayload } from '@/components/run/types';
```

Add state + the run-open callback inside `App`, right after line 16 (`const { activePlugins } = usePlugins();`):

```tsx
  const [runPayload, setRunPayload] = useState<RunPayload | null>(null);

  const openRun = useCallback((payload: RunPayload) => {
    setRunPayload(payload);
    setCurrentView('run');
  }, []);

  // DEMO-018 will deliver run payloads via a custom-protocol deep link.
  // Guarded so this is a no-op until that preload API exists.
  useEffect(() => {
    const onPayload = (window.electronAPI as { deepLink?: { onPayload?: (cb: (p: RunPayload) => void) => () => void } })
      .deepLink?.onPayload;
    return onPayload?.(openRun);
  }, [openRun]);
```

In `renderView()`, add this branch before the `plugin:` check (after line 39, the settings line):

```tsx
    if (currentView === 'run') {
      if (!runPayload) return <EvalStudioView onRunLocally={openRun} />;
      return (
        <RunView
          payload={runPayload}
          serverUrl={serverUrl}
          onViewEvalStudio={() => setCurrentView('eval-studio')}
        />
      );
    }
```

Change the existing eval-studio branch (line 38) to pass the callback:

```tsx
    if (currentView === 'eval-studio') return <EvalStudioView onRunLocally={openRun} />;
```

- [ ] **Step 3: Typecheck**

Run: `cd apps/desktop && npx tsc --noEmit`
Expected: FAIL — `EvalStudioView` does not yet accept `onRunLocally` (added in Task 7). This is expected; proceed to Task 7 before committing. (If you prefer green-between-tasks, do Task 7 first; the two are coupled.)

- [ ] **Step 4: Commit (after Task 7 makes it typecheck)**

```bash
git add apps/desktop/src/renderer/src/App.tsx apps/desktop/src/renderer/src/components/layout/Sidebar.tsx
git commit -m "feat(desktop): wire RunView into App with run payload + deep-link stub"
```

---

### Task 7: Interim "Run Locally" entry on Eval Studio rows

**Files:**
- Modify: `apps/desktop/src/renderer/src/views/EvalStudioView.tsx`
- Modify: `apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx`
- Test: `apps/desktop/src/renderer/src/components/eval/EvalRunsList.test.tsx` (extend if exists, else create)

> Read both files first; mirror their existing prop and rendering patterns. The goal: each run row gets a small "Run Locally" button that calls `onRunLocally({ spec: row.spec_name, expression: row.url4_expression })`. Replace the dead placeholder text at `EvalRunsList.tsx:35` ("Click a leaderboard entry's 'Run Locally' link to start one.") since this is now the actual entry.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/desktop/src/renderer/src/components/eval/EvalRunsList.test.tsx
// @vitest-environment jsdom
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { EvalRunsList } from './EvalRunsList';
import type { EvalRunSummary } from './types';

afterEach(cleanup);

const rows: EvalRunSummary[] = [
  {
    id: 'r1',
    spec_name: 'HLE',
    url4_expression: 'transform(url, intent)',
    started_at: '2026-01-01T00:00:00Z',
    finished_at: null,
    status: 'done',
    accuracy: 0.9,
    total_questions: 10,
    correct_questions: 9,
    error: null,
  },
];

it('calls onRunLocally with the row spec + expression', () => {
  const onRunLocally = vi.fn();
  render(
    <EvalRunsList
      runs={rows}
      selectedId={null}
      onSelect={vi.fn()}
      onRunLocally={onRunLocally}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /run locally/i }));
  expect(onRunLocally).toHaveBeenCalledWith({ spec: 'HLE', expression: 'transform(url, intent)' });
});
```

> **Note:** match the real `EvalRunsList` prop names when you read the file. The test above assumes props `{ runs, selectedId, onSelect, onRunLocally }`. If the current component derives runs from the hook internally instead of via props, adapt the test to the real signature — the only firm requirement is that clicking the row's "Run Locally" button invokes `onRunLocally({ spec, expression })`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/eval/EvalRunsList.test.tsx`
Expected: FAIL — no "Run Locally" button / `onRunLocally` not wired.

- [ ] **Step 3: Implement**

In `EvalRunsList.tsx`: add an optional `onRunLocally?: (p: { spec: string; expression: string }) => void` to its props. For each rendered run row, add a small button:

```tsx
{onRunLocally && (
  <button
    type="button"
    onClick={(e) => {
      e.stopPropagation();
      onRunLocally({ spec: run.spec_name, expression: run.url4_expression });
    }}
    className="text-xs text-primary underline"
  >
    Run Locally
  </button>
)}
```

In `EvalStudioView.tsx`: add `onRunLocally?: (p: RunPayload) => void` to its props and thread it down to `EvalRunsList`. Import `RunPayload` from `@/components/run/types`.

- [ ] **Step 4: Run test + typecheck**

Run: `cd apps/desktop && npx vitest run src/renderer/src/components/eval/EvalRunsList.test.tsx && npx tsc --noEmit`
Expected: PASS and clean typecheck (Task 6's App wiring now compiles).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/views/EvalStudioView.tsx apps/desktop/src/renderer/src/components/eval/EvalRunsList.tsx apps/desktop/src/renderer/src/components/eval/EvalRunsList.test.tsx
git commit -m "feat(desktop): interim Run Locally entry from Eval Studio rows"
```

---

### Task 8: Full gate + manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full desktop test suite + lint + typecheck**

Run:
```bash
cd apps/desktop && npx vitest run && npx tsc --noEmit && npm run lint
```
Expected: all green. Fix any failures before proceeding.

- [ ] **Step 2: Manual end-to-end (golden path)**

```bash
cd apps/desktop && npm run dev
```
1. Ensure the local server is running with at least one existing eval run (or create one).
2. Open Eval Studio → click "Run Locally" on a row.
3. Confirm the app switches to RunView showing the spec + highlighted expression.
4. Click "Run Locally" → observe `running` state, then progress `<correct>/<total>`, then final accuracy on `done`.
5. Click "View in Eval Studio →" → confirm it returns to Eval Studio and the new run appears as a separate row with the same `url4_expression`.

- [ ] **Step 3: Verify config is untouched**

Snapshot `~/.screamingface/config.json` (or the platform-equivalent path the app uses) before the run and after completion; expect **zero diff**. RunView passes the expression through props only — no write to `Url4Specs.specs`. Record the result.

- [ ] **Step 4: Push branch and open PR (do NOT merge)**

```bash
git push -u origin SF-167-run-locally-runview
gh pr create --title "SF-167: Run Locally wiring + RunView" --body "$(cat <<'EOF'
## Summary
- Adds `RunView` + `useEvalRun` hook: fires a tracked `GET /ensemble` run and polls `/eval_runs/{id}` to completion.
- Adds `RunButton` / `RunProgress` and wires a 'run' view into `App.tsx`.
- Interim entry: "Run Locally" button on Eval Studio rows (real leaderboard deep-link is DEMO-018).

## Deferred
- DEMO-018 custom-protocol deep-link routing into RunView (guarded stub present; acceptance criterion for deep-link entry deferred to that ticket).

## Test plan
- [ ] `npx vitest run` green (hook, RunButton, RunProgress, RunView, EvalRunsList)
- [ ] `npx tsc --noEmit` + `npm run lint` clean
- [ ] Manual: Eval Studio → Run Locally → progress → result → back to Eval Studio; config.json unchanged
EOF
)"
```

---

## Self-Review (author's check against the spec)

- **Spec coverage:**
  - "Build RunView, consumes payload, shows Url4Viewer, Run button, progress, final accuracy, View in Eval Studio link" → Task 5 ✅
  - "useEvalRun fires /ensemble with X-SF-Run-Id/X-SF-Run-Spec, polls /eval_runs/{id} every 2s" → Task 2 ✅
  - "Run button enabled when idle/done, disabled while running" → Task 3 ✅
  - "Progress <correct>/<total>" → Task 4 ✅; "on failed, error + Try again" → Task 5 ✅ (Run again)
  - "Add 'run' to View type; switch to it on payload" → Task 6 ✅
  - "No sidebar entry" → respected (interim entry is in Eval Studio, not the sidebar) ✅
  - "sf.json not mutated" → Task 8 Step 3 verifies ✅
  - "Spec id may not match a local spec; render as display-only" → RunView renders `payload.spec` as text only ✅
  - "Deep-link arrival routes into RunView" → **deferred to DEMO-018** (guarded stub in Task 6); documented in Scope.
- **Status/field names** verified against `eval_runs/schemas.py` (`running`/`done`/`failed`, `accuracy`/`correct_questions`/`total_questions`) — consistent across all tasks.
- **`startRun` signature** `(expression?: string)` is consistent in Task 2 (definition), Task 5 (no-arg call), and is the forward hook SF-182 will use.
- **Placeholder scan:** Task 7 intentionally instructs reading the real `EvalRunsList`/`EvalStudioView` signatures because those files may diverge from assumed prop names; the firm contract (button → `onRunLocally({spec, expression})`) is fully specified.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/SF-167-run-locally-runview.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, spec + code-quality review between tasks.
2. **Inline Execution** — execute tasks in this session with checkpoints.

Which approach?
