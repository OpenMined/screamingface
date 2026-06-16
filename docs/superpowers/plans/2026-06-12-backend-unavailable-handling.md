# Backend-Unavailable Handling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Stop eval runs from silently producing zero records when a model backend is down — warn the user before the run (preflight) and persist a `degraded` status + reason after it.

**Architecture:** Server reads the already-computed `interpreter._collected_errors` and threads it into `HOOK_RUN_FINISHED`; `eval_runs` records `status="degraded"` + a reason when errors were collected. Desktop preflights the run by matching the backends the expression references against `/backends/status` health, and renders the new `degraded` status.

**Tech Stack:** FastAPI, Tortoise, pytest; React 19 + TS, vitest.

**Ticket:** SF-270 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215654793910878
**Branch:** `SF-270-backend-unavailable-handling`. Spec: `docs/superpowers/specs/2026-06-12-backend-unavailable-handling-design.md`.

---

## Task 1: Server — persist `degraded` from collected errors

**Files:**
- Modify: `apps/server/src/screamingface/plugins/eval_runs/_hook_payloads.py`
- Modify: `apps/server/src/screamingface/plugins/eval_runs/plugin.py` (`_on_run_finished`)
- Modify: `apps/server/src/screamingface/plugins/url4_executor/routes.py` (`HOOK_RUN_FINISHED` emit)
- Test: `apps/server/src/screamingface/plugins/eval_runs/tests/test_degraded_status.py`

- [ ] **Step 1: Failing test for the handler**

Create `apps/server/src/screamingface/plugins/eval_runs/tests/test_degraded_status.py`:
```python
"""eval run goes 'degraded' (not 'done') when rows were collected as errors."""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from screamingface.core.config import AppConfig
from screamingface.core.app import create_app
from screamingface.plugins.state.testing import temp_state_path  # noqa: F401  (fixture)


@pytest.fixture
def client(temp_state_path):
    app = create_app(AppConfig(plugins=["state", "eval-runs"], plugin_config={}))
    with TestClient(app) as c:
        yield app, c


@pytest.mark.asyncio
async def test_finished_with_collected_errors_is_degraded(client):
    app, _ = client
    from screamingface.plugins.eval_runs.models import EvalRun
    from screamingface.plugins.eval_runs._hook_payloads import (
        HOOK_RUN_STARTED, HOOK_RUN_FINISHED,
    )
    from datetime import datetime, UTC

    rid = str(uuid.uuid4())
    await app.state.hooks.emit_async(
        HOOK_RUN_STARTED, run_id=rid, spec_name="ScoredLiveTruth",
        url4_expression="(...)", started_at=datetime.now(UTC),
    )
    await app.state.hooks.emit_async(
        HOOK_RUN_FINISHED, run_id=rid, finished_at=datetime.now(UTC), collected_errors=5,
    )
    run = await EvalRun.get(id=uuid.UUID(rid))
    assert run.status == "degraded"
    assert run.error and "errored" in run.error


@pytest.mark.asyncio
async def test_finished_clean_is_done(client):
    app, _ = client
    from screamingface.plugins.eval_runs.models import EvalRun
    from screamingface.plugins.eval_runs._hook_payloads import HOOK_RUN_STARTED, HOOK_RUN_FINISHED
    from datetime import datetime, UTC

    rid = str(uuid.uuid4())
    await app.state.hooks.emit_async(HOOK_RUN_STARTED, run_id=rid, spec_name="x",
                                     url4_expression="x", started_at=datetime.now(UTC))
    await app.state.hooks.emit_async(HOOK_RUN_FINISHED, run_id=rid, finished_at=datetime.now(UTC),
                                     collected_errors=0)
    run = await EvalRun.get(id=uuid.UUID(rid))
    assert run.status == "done"
    assert run.error is None
```

- [ ] **Step 2: Run it — expect failure**

Run: `cd apps/server && uv run pytest src/screamingface/plugins/eval_runs/tests/test_degraded_status.py -v`
Expected: FAIL (handler ignores `collected_errors`; status is `done`). If the test-fixture import path differs, mirror the existing `eval_runs/tests/` files' fixture usage (they already use `temp_state_path`).

- [ ] **Step 3: Extend the payload type**

In `_hook_payloads.py`, add the field to `RunFinishedPayload`:
```python
class RunFinishedPayload(TypedDict):
    run_id: str
    finished_at: datetime
    collected_errors: int
```

- [ ] **Step 4: Handle it in `_on_run_finished`**

In `eval_runs/plugin.py`, replace the body of `_on_run_finished` with:
```python
        async def _on_run_finished(**payload) -> None:
            run_id = payload["run_id"]
            run_uuid = UUID(run_id)
            total = await EvalQuestion.filter(run_id=run_uuid).count()
            correct = await EvalQuestion.filter(run_id=run_uuid, correct=True).count()
            accuracy = (correct / total) if total else 0.0
            collected_errors = int(payload.get("collected_errors", 0) or 0)
            update: dict = {
                "status": "done",
                "finished_at": payload["finished_at"],
                "accuracy": accuracy,
                "total_questions": total,
                "correct_questions": correct,
            }
            if collected_errors > 0:
                update["status"] = "degraded"
                update["error"] = (
                    f"{collected_errors} row(s) errored (e.g. a model backend was "
                    f"unavailable); {total} graded."
                )
            await EvalRun.filter(id=run_uuid).update(**update)
            self._question_idx_by_run.pop(run_id, None)
```

- [ ] **Step 5: Thread `collected_errors` from the route**

In `url4_executor/routes.py`, the `HOOK_RUN_FINISHED` emit (the `if run_id:` block after a successful `evaluate`) becomes:
```python
        collected_errors = getattr(interpreter, "_collected_errors", 0)
        if run_id:
            await request.app.state.hooks.emit_async(
                HOOK_RUN_FINISHED,
                run_id=run_id,
                finished_at=datetime.now(UTC),
                collected_errors=collected_errors,
            )
```
Leave the later SF-236 header block as-is (it re-reads `collected_errors`; reuse the variable if already defined above — remove the duplicate `collected_errors = getattr(...)` line there to avoid shadowing, keeping the `if collected_errors:` header set).

- [ ] **Step 6: Run tests — expect pass**

Run: `cd apps/server && uv run pytest src/screamingface/plugins/eval_runs -v`
Expected: PASS (new degraded tests + existing eval_runs tests).

- [ ] **Step 7: Commit**
```bash
git add apps/server/src/screamingface/plugins/eval_runs apps/server/src/screamingface/plugins/url4_executor/routes.py
git commit -m "SF-270: persist degraded eval-run status from collected errors"
```

---

## Task 2: Desktop — referenced-backends helper

**Files:**
- Create: `apps/desktop/src/renderer/src/lib/referenced-backends.ts`
- Test: `apps/desktop/src/renderer/src/lib/__tests__/referenced-backends.test.ts`

- [ ] **Step 1: Failing test**

Create `apps/desktop/src/renderer/src/lib/__tests__/referenced-backends.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { referencedBackends } from '../referenced-backends';

describe('referencedBackends', () => {
  it('finds the single backend in ScoredLiveTruth (claude only)', () => {
    expect(referencedBackends('(...consensus=/claude($item.q)!\'x\'...)')).toEqual(['claude']);
  });
  it('finds all three in a 3-way ensemble', () => {
    const e = '(claude:/claude($q)!a, codex:/codex($q)!b, gemini:/gemini($q)!c)!reduce';
    expect(referencedBackends(e).sort()).toEqual(['claude', 'codex', 'gemini']);
  });
  it('excludes /python and /data (non-auth, not model backends)', () => {
    expect(referencedBackends('/python(/data/code/check_correct.py)!{}')).toEqual([]);
  });
});
```

- [ ] **Step 2: Run — expect fail**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/referenced-backends.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `apps/desktop/src/renderer/src/lib/referenced-backends.ts`:
```ts
// Which auth-requiring model backends a url4 expression dispatches to, by
// scanning for their call-paths (/claude, /codex, /gemini, /ollama). /python,
// /data and /private are intentionally excluded — no credentials / not models.
// Mirrors the server's backend keying (backend_call_paths[0].lstrip('/')).
const AUTH_BACKENDS = ['claude', 'codex', 'gemini', 'ollama'] as const;
export type BackendName = (typeof AUTH_BACKENDS)[number];

export function referencedBackends(expression: string): BackendName[] {
  const found: BackendName[] = [];
  for (const name of AUTH_BACKENDS) {
    if (new RegExp(`/${name}\\b`).test(expression)) found.push(name);
  }
  return found;
}
```

- [ ] **Step 4: Run — expect pass**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/referenced-backends.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**
```bash
git add apps/desktop/src/renderer/src/lib/referenced-backends.ts apps/desktop/src/renderer/src/lib/__tests__/referenced-backends.test.ts
git commit -m "SF-270: referenced-backends helper + tests"
```

---

## Task 3: Desktop — `degraded` status type, badge, and refresh-returns-value

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/eval/types.ts`
- Modify: `apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx`
- Modify: `apps/desktop/src/renderer/src/hooks/use-backend-status.ts`

- [ ] **Step 1: Add `degraded` to the status union**

In `components/eval/types.ts`, change:
```ts
export type EvalRunStatus = 'running' | 'done' | 'failed' | 'degraded';
```

- [ ] **Step 2: Style the `degraded` badge (amber = warning, not hard fail)**

In `EvalStatusBadge.tsx`, add to `STATUS_STYLES`:
```ts
  degraded: 'bg-primary/15 text-primary border-primary/30',
```
(Keep `running`/`done`/`failed` as-is.)

- [ ] **Step 3: Make `refresh()` return the fresh statuses**

In `use-backend-status.ts`, the `refresh` callback currently sets state and returns void; have it also return the value so a preflight can read it without a stale-closure re-render:
```ts
  const refresh = async (): Promise<BackendStatusResponse> => {
    const next = await window.electronAPI.backends.refresh();
    setStatuses(next);
    return next;
  };
```
(Keep the rest of the return object; `refresh` is already exported.)

- [ ] **Step 4: Typecheck**

Run: `cd apps/desktop && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "EvalStatusBadge|use-backend-status|eval/types" || echo "clean"`
Expected: `clean`.

- [ ] **Step 5: Commit**
```bash
git add apps/desktop/src/renderer/src/components/eval/types.ts apps/desktop/src/renderer/src/components/eval/EvalStatusBadge.tsx apps/desktop/src/renderer/src/hooks/use-backend-status.ts
git commit -m "SF-270: degraded eval status type+badge; refresh returns statuses"
```

---

## Task 4: Desktop — preflight warning before a run

**Files:**
- Modify: `apps/desktop/src/renderer/src/views/EvalStudioView.tsx`

Preflight gates `runAndSelect`: extract referenced backends, refresh status, and if any is unavailable, show a `ConfirmDialog` ("Start anyway?"). Confirm proceeds; Cancel aborts.

- [ ] **Step 1: Add imports + preflight state**

At the top of `EvalStudioView.tsx`, add imports:
```ts
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useBackendStatus, isBackendStatusV2 } from '@/hooks/use-backend-status';
import { referencedBackends } from '@/lib/referenced-backends';
```
Inside the component, add:
```ts
  const { refresh: refreshBackends } = useBackendStatus();
  const [preflight, setPreflight] = useState<{ payload: RunPayload; unavailable: string[] } | null>(null);
```

- [ ] **Step 2: Split out the actual start + make `runAndSelect` preflight**

Replace the existing `runAndSelect` with a starter + an async preflight wrapper:
```ts
  const startRun = useCallback(
    (payload: RunPayload): void => {
      const runId = startEvalRun(payload);
      if (runId) setSelectedRunId(runId);
    },
    [startEvalRun],
  );

  const runAndSelect = useCallback(
    async (payload: RunPayload): Promise<void> => {
      const needed = referencedBackends(payload.expression);
      if (needed.length > 0) {
        try {
          const status = await refreshBackends();
          const unavailable = isBackendStatusV2(status)
            ? needed.filter((n) => {
                const b = status.backends?.[n];
                return !b || !b.authenticated || b.action !== 'healthy';
              })
            : [];
          if (unavailable.length > 0) {
            setPreflight({ payload, unavailable });
            return; // wait for the user's confirm
          }
        } catch {
          // status unreachable — fall through and start (don't block on a probe failure)
        }
      }
      startRun(payload);
    },
    [refreshBackends, startRun],
  );
```
Update the `pendingRun` effect call to `void runAndSelect(pendingRun);` (it's now async).

- [ ] **Step 3: Render the confirm dialog**

Near the other modals in the returned JSX (e.g. beside `{adding && <AddEvalRunDialog … />}`), add:
```tsx
      {preflight && (
        <ConfirmDialog
          title="Backend unavailable"
          message={`${preflight.unavailable.join(', ')} ${
            preflight.unavailable.length === 1 ? 'is' : 'are'
          } unavailable. This run will likely produce no scored records. Start anyway?`}
          confirmLabel="Start anyway"
          cancelLabel="Cancel"
          onConfirm={() => {
            const p = preflight.payload;
            setPreflight(null);
            startRun(p);
          }}
          onCancel={() => setPreflight(null)}
        />
      )}
```

- [ ] **Step 4: Build**

Run: `cd apps/desktop && npm run build 2>&1 | tail -2`
Expected: `✓ built`. (If `ConfirmDialog` prop names differ, match `components/ConfirmDialog.tsx`: `title`, `message`, `confirmLabel`, `cancelLabel`, `onConfirm`, `onCancel`.)

- [ ] **Step 5: Commit**
```bash
git add apps/desktop/src/renderer/src/views/EvalStudioView.tsx
git commit -m "SF-270: preflight warn when a referenced backend is unavailable"
```

---

## Task 5: Verification

- [ ] **Step 1: Server tests**

Run: `cd apps/server && uv run pytest src/screamingface/plugins/eval_runs src/screamingface/plugins/url4_executor -q`
Expected: all PASS.

- [ ] **Step 2: Desktop tests + build**

Run: `cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/referenced-backends.test.ts && npm run build 2>&1 | tail -2`
Expected: vitest PASS; build `✓ built`.

- [ ] **Step 3: Manual smoke (one dev app; close any first)**

`cd apps/desktop && npm run dev`. With the Claude backend logged out/unavailable: start ScoredLiveTruth → expect the **preflight dialog** ("claude is unavailable… Start anyway?"). Start anyway → when it finishes, the run shows a **degraded** badge with the "N row(s) errored…" reason. With Claude healthy → no dialog, run completes `done`.

- [ ] **Step 4: Final commit (if any verification fixes)**
```bash
git add -A && git commit -m "SF-270: verification fixes" || echo "nothing to commit"
```

---

## Self-review notes (addressed)

- **Spec coverage:** preflight (Task 4, helper Task 2, refresh-returns Task 3), degraded persistence (Task 1), degraded display (Task 3 badge + existing `EvalRunDetail` error block), any-referenced-backend scope (Task 2). All covered.
- **Stale-closure pitfall** explicitly handled by having `refresh()` return the fresh statuses (Task 3) and reading them directly in preflight (Task 4) instead of the hook's `statuses` state.
- **Robustness preserved:** preflight is advisory (Start anyway), a status-probe failure does not block the run, and `on_error=collect` semantics are unchanged.
- **Signature checks flagged:** ConfirmDialog props, the eval-runs test fixture, and the `_collected_errors` attribute are called out to verify against the real files during implementation.
