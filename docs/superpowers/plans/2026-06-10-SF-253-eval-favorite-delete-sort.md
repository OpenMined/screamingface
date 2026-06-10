# SF-253 — Eval Studio: favorite + delete runs, sort favorites to top

**Ticket:** SF-253 · https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215573724473294
**Branch:** `SF-253-eval-favorite-delete-sort` (off latest `main`)
**Confidence:** ~96%

## Goal

In Eval Studio:
1. **Favorite** toggle (star) per run — persisted server-side.
2. **Delete** per run — hard-removes the run + its cascaded questions, behind a confirm dialog.
3. **Sort favorites to the top** of the runs list (then by recency, as today).

## Decisions (confirmed with user)

- **Favorite is server-side** — a `favorite` column on the `eval_run` record, a toggle endpoint, and DB-layer ordering. (Source of truth; the local server is per-machine anyway.)
- **Delete is a hard server `DELETE`** behind a **confirm dialog**.

## Architecture context

- Runs are owned by the server `eval_runs` plugin (`apps/server/src/screamingface/plugins/eval_runs/`):
  model `EvalRun` (`models/eval_run.py`), `EvalRunStore(BaseStore)` (`store.py`), GET-only routes (`routes.py`),
  Pydantic DTOs (`schemas.py`). `BaseStore` already provides `update(id, **fields)` and `delete(id) -> bool` (`plugins/state/store.py`).
- `EvalQuestion` has `on_delete=CASCADE` → deleting a run drops its questions automatically.
- **Schema rollout:** the state plugin runs `Tortoise.generate_schemas(safe=True)` — `CREATE TABLE IF NOT EXISTS` only. It does **not** ALTER existing tables, so a new `favorite` column will be missing on already-created local `eval_run` tables and any query ordering by it would 500. We add a small idempotent additive migration (the README's "one-shot patch").
- Desktop: `EvalRunsList` renders rows and owns `useEvalRunsList` (polls 2 s, exposes `refresh()`); `EvalStudioView` owns `selectedId`; `window.electronAPI.server.fetch(url, { method, headers, body })` supports non-GET.

---

## Server changes (`apps/server`)

### 1. Model — add `favorite`
`plugins/eval_runs/models/eval_run.py`, on `BaseEvalRun`:
```python
favorite = fields.BooleanField(default=False)
```

### 2. Schema — expose `favorite`
`plugins/eval_runs/schemas.py`, on `EvalRunSummaryOut` (inherited by `EvalRunOut`):
```python
favorite: bool = False
```

### 3. Store — order favorites first + a toggle helper
`plugins/eval_runs/store.py`:
```python
async def list_summaries(self, *, limit=50, offset=0) -> list[EvalRun]:
    return await EvalRun.all().order_by("-favorite", "-started_at").offset(offset).limit(limit)

async def set_favorite(self, run_id: UUID, favorite: bool) -> EvalRun | None:
    run = await EvalRun.get_or_none(id=run_id)
    if run is None:
        return None
    run.favorite = favorite
    await run.save(update_fields=["favorite", "updated_at"])
    return run
```
(Delete reuses `BaseStore.delete(run_id)`.)

### 4. Routes — PATCH (toggle) + DELETE
`plugins/eval_runs/routes.py`:
- `PATCH /eval_runs/{run_id}` — body `{ "favorite": bool }` (new `EvalRunPatchIn` schema). Returns `EvalRunSummaryOut`; 404 if missing.
- `DELETE /eval_runs/{run_id}` — `204 No Content` on success; 404 if `store.delete()` returns `False`.

### 5. Additive column migration (existing local DBs)
New `plugins/eval_runs/_migrations.py` with an idempotent `ensure_favorite_column()`:
- Use the Tortoise connection to read `PRAGMA table_info('eval_run')`; if `favorite` absent, run
  `ALTER TABLE eval_run ADD COLUMN favorite INT NOT NULL DEFAULT 0`.
- SQLite-scoped (local app DB); Postgres is out of scope per state README.
Register it as an `app.startup` hook in `EvalRunsPlugin.setup()` ordered to run **after** the state plugin's
`generate_schemas` (state startup is priority 10 — register this with a priority that fires later; confirm
ordering against `core/hooks` during impl). Fresh installs get the column from `generate_schemas`; existing
installs get it from the ALTER. Idempotent on every boot.

---

## Desktop changes (`apps/desktop`)

### 6. Type — `favorite`
`components/eval/types.ts`: add `favorite: boolean` to `EvalRunSummary`.

### 7. Actions hook
New `hooks/use-eval-run-actions.ts` returning `{ toggleFavorite, deleteRun }`:
- `toggleFavorite(id, favorite)` → `server.fetch(`${base}/eval_runs/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite }) })`.
- `deleteRun(id)` → `server.fetch(`${base}/eval_runs/${id}`, { method: 'DELETE' })`.
- Both surface failures via `useToast`; callers `refresh()` the list on success.

### 8. Confirm dialog
Reuse shadcn `alert-dialog` if present; otherwise a minimal `components/ConfirmDialog.tsx` (matches the existing
`rounded-[10px]` modal style, ≤10 px radius). Copy: "Delete this run? This permanently removes the run and its
question results. This can't be undone." Buttons: Cancel / Delete (destructive).

### 9. `EvalRunsList` rows — star + trash
- **Star** button (always visible): filled `Star` when `run.favorite`, outline otherwise; `onClick` (stopPropagation)
  → `toggleFavorite(run.id, !run.favorite)` then `refresh()`.
- **Trash** button: opens the confirm dialog; on confirm → `deleteRun(run.id)` → `refresh()` and, if the deleted run
  is selected, notify parent to clear selection via a new `onRunDeleted?(id)` prop.
- Place both in the existing right-side action cluster next to the Run-locally play button. Keep row click =
  select. No client-side sort needed — the **server returns favorites first**.

### 10. `EvalRunDetail` header — delete the open run
Add a Delete button to the detail header action row (alongside Publish/Edit) using the same confirm + `deleteRun`;
on success call an `onDeleted?()` prop so `EvalStudioView` clears `selectedId`. (Favorite in the detail header is
optional/nice-to-have; primary toggle lives in the list.)

### 11. `EvalStudioView` wiring
- Pass `onRunDeleted` to `EvalRunsList` and `onDeleted` to `EvalRunDetail`; clear `selectedId` when the deleted id
  matches the selection.

---

## Tests

### Server (`plugins/eval_runs/tests/`)
- `PATCH` sets/clears `favorite`; 404 on unknown id; response reflects new value.
- `DELETE` returns 204 and the run + its `EvalQuestion` rows are gone; 404 on unknown id.
- `list_summaries` orders favorites before non-favorites, recency within each group.
- `ensure_favorite_column()` is idempotent and adds the column to a pre-existing favorite-less table.

### Desktop (vitest)
- `use-eval-run-actions` issues the correct method/URL/body and toasts on failure.
- `EvalRunsList`: star reflects `favorite` and calls `toggleFavorite`; trash opens confirm and calls `deleteRun`
  only after confirm; renders server order (no client re-sort).
- `ConfirmDialog` (if added) confirm/cancel behavior.
- Run the full desktop suite (the SF-250 CI gate) + `npm run build`.

---

## Out of scope
- Bulk select / multi-delete.
- Favorite/delete on the public leaderboard (these are local eval runs only).
- Postgres column migration (state README: deployment concern).
- Undo for delete.

## Sequencing
1. Server: model + schema + store + routes + migration + server tests (green).
2. Desktop: type + actions hook + confirm dialog + list buttons + detail delete + view wiring + desktop tests (green).
3. Manual smoke: favorite a run (jumps to top, persists across restart), delete a run (confirm, disappears, questions gone).
4. PR; wait for desktop CI (SF-250 gate) before merge.
