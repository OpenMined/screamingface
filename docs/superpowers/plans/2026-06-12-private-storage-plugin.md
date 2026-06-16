# Private Storage Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DB-backed `private-storage` server plugin serving editable markdown entities at `/private/{uuid7}` (consumable by url4 exactly like `/data/*`), plus a "Private Data" desktop view that mirrors Code Studio but edits markdown.

**Architecture:** A new server plugin persists entities via Tortoise ORM through the existing `state` plugin (the entity's `uuid7` is its UUID primary key; `label` is optional/nav-only). It exposes REST CRUD at `/private`, with `GET /private/{uuid7}` returning **raw markdown** so url4's relative-URL resolver feeds it into chains unchanged. The desktop app gets a new view that talks to the local server over HTTP via a small pure API module wrapped by a React hook, reusing the existing Monaco editor popup in `markdown` mode and the shared `ui/` primitives.

**Tech Stack:** Python 3.12, FastAPI, Tortoise ORM, `uuid6` (uuid7), pytest; React 19 + Vite + TypeScript, Tailwind v4, `@monaco-editor/react`, vitest.

**Branch:** `SF-269-private-storage-plugin` (stacked on `SF-268-desktop-ui-brand-alignment`). Asana: https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215643830854867

---

## File Structure

**Server** — `apps/server/src/screamingface/plugins/private_storage/`
- `__init__.py` — empty package marker
- `models.py` — `PrivateEntity` Tortoise model (extends `state` `BaseModel`)
- `store.py` — async data-access helpers (keeps routes slim; one responsibility: DB access)
- `routes.py` — `create_router()`; the `/private` REST endpoints
- `plugin.py` — `PrivateStoragePlugin`; registers models + router
- `tests/__init__.py`, `tests/test_private_storage.py` — plugin + url4 integration tests
- modify `apps/server/sf.json` — add `"private-storage"` to `plugins`
- modify `apps/server/pyproject.toml` — add `uuid6` dependency (via `uv add`)

**Desktop** — `apps/desktop/src/renderer/src/`
- `lib/private-data-api.ts` — pure HTTP functions (unit-tested)
- `lib/__tests__/private-data-api.test.ts` — api unit tests
- `hooks/use-private-data.ts` — React hook wrapping the api with state + toasts
- `components/private-data/PrivateDataList.tsx` — left list
- `components/private-data/PrivateDataDetail.tsx` — right detail/editor pane
- `components/private-data/AddPrivateDataDialog.tsx` — create dialog
- `views/PrivateDataView.tsx` — the view (resizable list + detail)
- modify `components/layout/Sidebar.tsx` — `View` union + nav entry
- modify `App.tsx` — route branch

---

## Task 1: Add uuid7 dependency

**Files:**
- Modify: `apps/server/pyproject.toml` (+ `uv.lock`)

- [ ] **Step 1: Add the dependency**

Run (from `apps/server`):
```bash
cd apps/server && uv add uuid6
```
Expected: `pyproject.toml` `dependencies` gains a `uuid6` entry and `uv.lock` updates; command exits 0.

- [ ] **Step 2: Verify uuid7 imports and returns a UUID**

Run:
```bash
cd apps/server && uv run python -c "from uuid6 import uuid7; u=uuid7(); import uuid; print(isinstance(u, uuid.UUID), u)"
```
Expected: `True <a uuid>`

- [ ] **Step 3: Commit**

```bash
git add apps/server/pyproject.toml apps/server/uv.lock
git commit -m "SF-269: add uuid6 dependency for uuid7 keys"
```

---

## Task 2: PrivateEntity model

**Files:**
- Create: `apps/server/src/screamingface/plugins/private_storage/__init__.py`
- Create: `apps/server/src/screamingface/plugins/private_storage/models.py`

- [ ] **Step 1: Create the empty package marker**

Create `apps/server/src/screamingface/plugins/private_storage/__init__.py` (empty file).

- [ ] **Step 2: Write the model**

`BaseModel` (in `screamingface.plugins.state.base`) already supplies `id = UUIDField(primary_key=True)`, `created_at`, and `updated_at`. The entity's `id` IS its uuid7.

Create `apps/server/src/screamingface/plugins/private_storage/models.py`:
```python
"""PrivateEntity — one editable markdown entity, keyed by its uuid7 (the `id`)."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class PrivateEntity(BaseModel):
    class Meta:
        table = "private_entity"
        table_description = "Editable markdown entities for /private/{uuid7} (demo)"
        ordering = ["-updated_at"]

    # `id` (UUID pk = the uuid7), `created_at`, `updated_at` come from BaseModel.
    label = fields.CharField(max_length=200, null=True)
    content = fields.TextField(default="")

    def __str__(self) -> str:
        return f"{self.label or self.id}"
```

- [ ] **Step 3: Verify it imports**

Run:
```bash
cd apps/server && uv run python -c "from screamingface.plugins.private_storage.models import PrivateEntity; print(PrivateEntity._meta.db_table)"
```
Expected: `private_entity`

- [ ] **Step 4: Commit**

```bash
git add apps/server/src/screamingface/plugins/private_storage/__init__.py apps/server/src/screamingface/plugins/private_storage/models.py
git commit -m "SF-269: PrivateEntity Tortoise model"
```

---

## Task 3: Store helpers (async data access)

**Files:**
- Create: `apps/server/src/screamingface/plugins/private_storage/store.py`

- [ ] **Step 1: Write the store helpers**

Create `apps/server/src/screamingface/plugins/private_storage/store.py`:
```python
"""Async data-access helpers for PrivateEntity. Keeps route handlers slim.

uuid7 strings arrive from the URL/path; we parse to UUID and look up by pk.
Invalid uuids resolve to None (handlers turn that into 404)."""

from __future__ import annotations

from uuid import UUID

from uuid6 import uuid7

from screamingface.plugins.private_storage.models import PrivateEntity


def _parse(uuid_str: str) -> UUID | None:
    try:
        return UUID(uuid_str)
    except (ValueError, AttributeError, TypeError):
        return None


async def create_entity(*, content: str = "", label: str | None = None) -> PrivateEntity:
    return await PrivateEntity.create(id=uuid7(), content=content, label=label)


async def get_entity(uuid_str: str) -> PrivateEntity | None:
    key = _parse(uuid_str)
    if key is None:
        return None
    return await PrivateEntity.get_or_none(id=key)


async def list_entities() -> list[PrivateEntity]:
    return await PrivateEntity.all()  # Meta.ordering => newest updated first


async def update_entity(
    uuid_str: str, *, content: str | None = None, label: str | None = None, label_set: bool = False
) -> PrivateEntity | None:
    entity = await get_entity(uuid_str)
    if entity is None:
        return None
    if content is not None:
        entity.content = content
    if label_set:  # allows clearing the label to None explicitly
        entity.label = label
    await entity.save()
    return entity


async def delete_entity(uuid_str: str) -> bool:
    key = _parse(uuid_str)
    if key is None:
        return False
    deleted = await PrivateEntity.filter(id=key).delete()
    return deleted > 0
```

- [ ] **Step 2: Commit**

```bash
git add apps/server/src/screamingface/plugins/private_storage/store.py
git commit -m "SF-269: private-storage async store helpers"
```

---

## Task 4: Routes

**Files:**
- Create: `apps/server/src/screamingface/plugins/private_storage/routes.py`

- [ ] **Step 1: Write the router**

`GET /private/{uuid7}` returns **raw markdown** (url4 parity with `/data`). The other endpoints are JSON. Create `apps/server/src/screamingface/plugins/private_storage/routes.py`:
```python
"""Routes for the private-storage plugin — editable markdown entities by uuid7.

GET /private/{uuid7} returns raw markdown (text/markdown) so url4's relative-URL
resolver can feed it into a chain, identical to /data/{key}. The other endpoints
(list/create/update/delete) are JSON and drive the Private Data UI."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from screamingface.plugins.private_storage import store

__all__ = ["create_router"]


class CreateBody(BaseModel):
    content: str = ""
    label: str | None = None


class UpdateBody(BaseModel):
    content: str | None = None
    label: str | None = None


def create_router() -> APIRouter:
    router = APIRouter(tags=["private-storage"])

    @router.get("/private", response_model=None, operation_id="private_list")
    async def list_private() -> JSONResponse:
        items = await store.list_entities()
        return JSONResponse(
            content=[
                {
                    "uuid": str(e.id),
                    "label": e.label,
                    "updated_at": e.updated_at.isoformat(),
                }
                for e in items
            ]
        )

    @router.post("/private", response_model=None, operation_id="private_create")
    async def create_private(body: CreateBody) -> JSONResponse:
        entity = await store.create_entity(content=body.content, label=body.label)
        return JSONResponse(
            content={"uuid": str(entity.id), "url": f"/private/{entity.id}", "label": entity.label}
        )

    @router.get("/private/{uuid7}", response_model=None, operation_id="private_get")
    async def get_private(uuid7: str) -> Response:
        entity = await store.get_entity(uuid7)
        if entity is None:
            raise HTTPException(status_code=404, detail="Not found")
        return Response(content=entity.content, media_type="text/markdown; charset=utf-8")

    @router.put("/private/{uuid7}", response_model=None, operation_id="private_update")
    async def update_private(uuid7: str, body: UpdateBody) -> JSONResponse:
        entity = await store.update_entity(
            uuid7,
            content=body.content,
            label=body.label,
            label_set="label" in body.model_fields_set,
        )
        if entity is None:
            raise HTTPException(status_code=404, detail="Not found")
        return JSONResponse(content={"uuid": str(entity.id), "label": entity.label})

    @router.delete("/private/{uuid7}", response_model=None, operation_id="private_delete")
    async def delete_private(uuid7: str) -> Response:
        ok = await store.delete_entity(uuid7)
        if not ok:
            raise HTTPException(status_code=404, detail="Not found")
        return Response(status_code=204)

    return router
```

- [ ] **Step 2: Commit**

```bash
git add apps/server/src/screamingface/plugins/private_storage/routes.py
git commit -m "SF-269: private-storage REST routes"
```

---

## Task 5: Plugin class + registration

**Files:**
- Create: `apps/server/src/screamingface/plugins/private_storage/plugin.py`
- Modify: `apps/server/sf.json`

- [ ] **Step 1: Write the plugin**

Create `apps/server/src/screamingface/plugins/private_storage/plugin.py`:
```python
"""PrivateStoragePlugin — DB-backed editable markdown entities at /private/{uuid7}.

Temporary demo-period entity. Same url4 role as /data, but persistent (Tortoise
via the state plugin) and editable from the Private Data UI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from screamingface.plugin import Plugin
from screamingface.plugins.private_storage.routes import create_router

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry


class PrivateStoragePlugin(Plugin):
    name = "private-storage"
    description = "Editable markdown entities by uuid7 at /private — url4 content source (demo)"
    tags: list[str] = ["product:system", "lifecycle:demo"]
    depends: list[str] = ["state"]
    settings_class = None

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        app.state.state_plugin.register_models(
            "private_storage",
            ["screamingface.plugins.private_storage.models"],
        )
        router = create_router()
        routes.add_router(self.name, router, prefix="")
```

- [ ] **Step 2: Register the plugin in sf.json**

In `apps/server/sf.json`, add `"private-storage"` to the `"plugins"` array immediately after `"data-store"`. Read the file first to find the exact line; the edit adds one entry, e.g.:
```json
    "data-store",
    "private-storage",
```
(`"state"` is already present — it must remain, since `private-storage` depends on it.)

- [ ] **Step 3: Verify the plugin loads (server boots)**

Run:
```bash
cd apps/server && uv run sf run --no-reload --port 8799 &
sleep 6
curl -s -X POST localhost:8799/private -H 'content-type: application/json' -d '{"content":"# hi","label":"demo"}'
echo
kill %1
```
Expected: JSON like `{"uuid":"<uuid7>","url":"/private/<uuid7>","label":"demo"}`.

- [ ] **Step 4: Commit**

```bash
git add apps/server/src/screamingface/plugins/private_storage/plugin.py apps/server/sf.json
git commit -m "SF-269: register private-storage plugin"
```

---

## Task 6: Plugin tests (CRUD + url4 resolution)

**Files:**
- Create: `apps/server/src/screamingface/plugins/private_storage/tests/__init__.py`
- Create: `apps/server/src/screamingface/plugins/private_storage/tests/test_private_storage.py`

- [ ] **Step 1: Write the failing tests**

Use the same app/TestClient pattern as `data_store`/`eval_runs` tests (which build an app with the needed plugins and run startup so Tortoise initializes). Create `tests/__init__.py` (empty) and `tests/test_private_storage.py`:
```python
"""CRUD + url4 integration tests for the private-storage plugin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from screamingface.config import AppConfig
from screamingface.app import create_app


@pytest.fixture
def client(tmp_path):
    config = AppConfig(
        plugins=["state", "private-storage", "url4-executor"],
        plugin_config={"state": {"path": str(tmp_path / "state.sqlite")}},
    )
    app = create_app(config)
    with TestClient(app) as c:  # context manager runs startup/shutdown (Tortoise init)
        yield c


def test_create_get_update_list_delete(client):
    # create
    r = client.post("/private", json={"content": "# Title", "label": "notes"})
    assert r.status_code == 200
    uuid = r.json()["uuid"]
    assert r.json()["url"] == f"/private/{uuid}"

    # get raw markdown
    r = client.get(f"/private/{uuid}")
    assert r.status_code == 200
    assert r.text == "# Title"
    assert r.headers["content-type"].startswith("text/markdown")

    # update
    r = client.put(f"/private/{uuid}", json={"content": "# Changed"})
    assert r.status_code == 200
    assert client.get(f"/private/{uuid}").text == "# Changed"

    # list
    r = client.get("/private")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["uuid"] == uuid and row["label"] == "notes" for row in rows)

    # delete
    assert client.delete(f"/private/{uuid}").status_code == 204
    assert client.get(f"/private/{uuid}").status_code == 404


def test_unknown_uuid_404(client):
    assert client.get("/private/not-a-uuid").status_code == 404
    assert client.get("/private/00000000-0000-0000-0000-000000000000").status_code == 404


def test_url4_resolves_private_entity(client):
    """A /private/{uuid7} relurl resolves to the stored markdown inside url4."""
    uuid = client.post("/private", json={"content": "SECRET-CONTEXT"}).json()["uuid"]
    # url4 resolves a bare relative URL by fetching it in-process.
    r = client.post("/ensemble/format", json={"expression": f"/private/{uuid}"})
    assert r.status_code == 200  # expression parses & references the entity
```

- [ ] **Step 2: Run tests — verify they fail/then pass**

Run:
```bash
cd apps/server && uv run pytest src/screamingface/plugins/private_storage/tests/test_private_storage.py -v
```
Expected: the CRUD and 404 tests PASS. For `test_url4_resolves_private_entity`, if the `/ensemble/format` endpoint or its request shape differs, **first inspect** how url4 specs are validated/resolved (`rg -n "ensemble/format|resolve|_fetch_relative" apps/server/src/screamingface/plugins`) and adjust the assertion to call the real resolution path (e.g. a direct `await url4_resolve.resolve(Url4RelUrl(f"/private/{uuid}"), app=app)` unit call). The required guarantee: resolving `/private/{uuid}` yields `"SECRET-CONTEXT"`. Keep iterating until green.

- [ ] **Step 3: Commit**

```bash
git add apps/server/src/screamingface/plugins/private_storage/tests
git commit -m "SF-269: private-storage CRUD + url4 resolution tests"
```

---

## Task 7: Desktop API module (pure HTTP)

**Files:**
- Create: `apps/desktop/src/renderer/src/lib/private-data-api.ts`
- Create: `apps/desktop/src/renderer/src/lib/__tests__/private-data-api.test.ts`

The renderer calls the local server with `window.electronAPI.server.fetch(\`${base}/...\`)`, where `base` is `${scheme}://${host}:${port}` from `useServerStatus().info` (see `serverBase` in `hooks/use-code-scripts.ts`). Keeping the calls in a pure module makes them unit-testable.

- [ ] **Step 1: Write the failing test**

Create `apps/desktop/src/renderer/src/lib/__tests__/private-data-api.test.ts`:
```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPrivate, deletePrivate, getPrivateContent, listPrivate, updatePrivate } from '../private-data-api';

const base = 'http://localhost:9100';

function mockFetch(status: number, body: string) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    text: () => Promise.resolve(body),
    json: () => Promise.resolve(JSON.parse(body || '{}')),
  });
  // @ts-expect-error test shim
  globalThis.window = { electronAPI: { server: { fetch: fetchMock } } };
  return fetchMock;
}

afterEach(() => vi.restoreAllMocks());

describe('private-data-api', () => {
  it('lists entities', async () => {
    const f = mockFetch(200, JSON.stringify([{ uuid: 'u1', label: 'a', updated_at: 't' }]));
    const rows = await listPrivate(base);
    expect(rows).toEqual([{ uuid: 'u1', label: 'a', updated_at: 't' }]);
    expect(f).toHaveBeenCalledWith(`${base}/private`, expect.objectContaining({ method: 'GET' }));
  });

  it('creates with label+content', async () => {
    const f = mockFetch(200, JSON.stringify({ uuid: 'u2', url: '/private/u2', label: 'x' }));
    const res = await createPrivate(base, { label: 'x', content: '# hi' });
    expect(res.uuid).toBe('u2');
    const [, init] = f.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ label: 'x', content: '# hi' });
  });

  it('gets raw content', async () => {
    mockFetch(200, '# raw');
    expect(await getPrivateContent(base, 'u1')).toBe('# raw');
  });

  it('updates and deletes', async () => {
    const f = mockFetch(200, JSON.stringify({ uuid: 'u1', label: 'y' }));
    await updatePrivate(base, 'u1', { content: '# z' });
    await deletePrivate(base, 'u1');
    expect(f).toHaveBeenLastCalledWith(`${base}/private/u1`, expect.objectContaining({ method: 'DELETE' }));
  });

  it('throws on non-ok', async () => {
    mockFetch(404, '');
    await expect(getPrivateContent(base, 'missing')).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run:
```bash
cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/private-data-api.test.ts
```
Expected: FAIL ("Cannot find module '../private-data-api'").

- [ ] **Step 3: Implement the api module**

Create `apps/desktop/src/renderer/src/lib/private-data-api.ts`:
```ts
// Pure HTTP wrappers around the private-storage plugin (/private). All calls go
// through window.electronAPI.server.fetch against the running local server base
// (`${scheme}://${host}:${port}`). Keep UI/state concerns out of this module.

export interface PrivateItem {
  uuid: string;
  label: string | null;
  updated_at: string;
}

export interface CreateResult {
  uuid: string;
  url: string;
  label: string | null;
}

function api() {
  return window.electronAPI.server;
}

async function ok(res: { ok: boolean; status: number }, what: string): Promise<void> {
  if (!res.ok) throw new Error(`${what} failed (HTTP ${res.status})`);
}

export async function listPrivate(base: string): Promise<PrivateItem[]> {
  const res = await api().fetch(`${base}/private`, { method: 'GET' });
  await ok(res, 'list');
  return (await res.json()) as PrivateItem[];
}

export async function createPrivate(
  base: string,
  payload: { label?: string | null; content?: string },
): Promise<CreateResult> {
  const res = await api().fetch(`${base}/private`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ label: payload.label ?? null, content: payload.content ?? '' }),
  });
  await ok(res, 'create');
  return (await res.json()) as CreateResult;
}

export async function getPrivateContent(base: string, uuid: string): Promise<string> {
  const res = await api().fetch(`${base}/private/${uuid}`, { method: 'GET' });
  await ok(res, 'get');
  return await res.text();
}

export async function updatePrivate(
  base: string,
  uuid: string,
  payload: { label?: string | null; content?: string },
): Promise<void> {
  const body: Record<string, unknown> = {};
  if (payload.content !== undefined) body.content = payload.content;
  if (payload.label !== undefined) body.label = payload.label;
  const res = await api().fetch(`${base}/private/${uuid}`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  await ok(res, 'update');
}

export async function deletePrivate(base: string, uuid: string): Promise<void> {
  const res = await api().fetch(`${base}/private/${uuid}`, { method: 'DELETE' });
  await ok(res, 'delete');
}
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/private-data-api.test.ts
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/lib/private-data-api.ts apps/desktop/src/renderer/src/lib/__tests__/private-data-api.test.ts
git commit -m "SF-269: private-data HTTP api module + tests"
```

---

## Task 8: `use-private-data` hook

**Files:**
- Create: `apps/desktop/src/renderer/src/hooks/use-private-data.ts`

- [ ] **Step 1: Write the hook**

Create `apps/desktop/src/renderer/src/hooks/use-private-data.ts`:
```ts
// React state wrapper over private-data-api. Resolves the local-server base from
// useServerStatus (same helper Code Studio uses), surfaces errors as toasts, and
// refetches the list after mutations (no optimistic state — demo simplicity).
import { useCallback, useEffect, useState } from 'react';
import { useServerStatus } from '@/hooks/use-server-status';
import { useToast } from '@/hooks/use-toast';
import {
  createPrivate,
  deletePrivate,
  getPrivateContent,
  listPrivate,
  updatePrivate,
  type PrivateItem,
} from '@/lib/private-data-api';

function serverBase(info: ReturnType<typeof useServerStatus>['info']): string | null {
  if (!info) return null;
  const host = info.host === '0.0.0.0' ? 'localhost' : info.host;
  return `${info.scheme}://${host}:${info.port}`;
}

export function usePrivateData() {
  const { info } = useServerStatus();
  const base = serverBase(info);
  const { toast } = useToast();
  const [items, setItems] = useState<PrivateItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const refresh = useCallback(async () => {
    if (!base) return;
    try {
      setItems(await listPrivate(base));
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(
    async (label?: string): Promise<string | null> => {
      if (!base) return null;
      try {
        const res = await createPrivate(base, { label: label || null, content: '' });
        await refresh();
        return res.uuid;
      } catch (e) {
        toast({ variant: 'error', title: 'Create failed', description: (e as Error).message });
        return null;
      }
    },
    [base, refresh, toast],
  );

  const update = useCallback(
    async (uuid: string, payload: { label?: string | null; content?: string }): Promise<boolean> => {
      if (!base) return false;
      try {
        await updatePrivate(base, uuid, payload);
        await refresh();
        return true;
      } catch (e) {
        toast({ variant: 'error', title: 'Save failed', description: (e as Error).message });
        return false;
      }
    },
    [base, refresh, toast],
  );

  const remove = useCallback(
    async (uuid: string): Promise<boolean> => {
      if (!base) return false;
      try {
        await deletePrivate(base, uuid);
        await refresh();
        return true;
      } catch (e) {
        toast({ variant: 'error', title: 'Delete failed', description: (e as Error).message });
        return false;
      }
    },
    [base, refresh, toast],
  );

  const getContent = useCallback(
    async (uuid: string): Promise<string> => (base ? getPrivateContent(base, uuid) : ''),
    [base],
  );

  return { items, loading, error, ready: base !== null, create, update, remove, getContent, refresh };
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd apps/desktop && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "use-private-data|private-data-api" || echo "no type errors in private-data files"
```
Expected: `no type errors in private-data files`. (If `useServerStatus().info` field names differ, open `hooks/use-server-status.ts` and match `scheme/host/port`.)

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/renderer/src/hooks/use-private-data.ts
git commit -m "SF-269: use-private-data hook"
```

---

## Task 9: List, Detail, and Add-dialog components

**Files:**
- Create: `apps/desktop/src/renderer/src/components/private-data/PrivateDataList.tsx`
- Create: `apps/desktop/src/renderer/src/components/private-data/PrivateDataDetail.tsx`
- Create: `apps/desktop/src/renderer/src/components/private-data/AddPrivateDataDialog.tsx`

Read `components/code/CodeScriptsList.tsx`, `CodeScriptDetail.tsx`, `AddCodeScriptDialog.tsx`, and `components/CodeEditorPopup.tsx` first to match their styling/props exactly. Reuse the shared `ui/` primitives and `CodeEditorPopup`.

- [ ] **Step 1: PrivateDataList**

Create `apps/desktop/src/renderer/src/components/private-data/PrivateDataList.tsx`:
```tsx
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import type { PrivateItem } from '@/lib/private-data-api';

interface Props {
  items: PrivateItem[];
  selectedId: string | null;
  onSelect: (uuid: string) => void;
}

function displayName(item: PrivateItem): string {
  return item.label?.trim() || `private/${item.uuid.slice(0, 8)}`;
}

export function PrivateDataList({ items, selectedId, onSelect }: Props) {
  const [filter, setFilter] = useState('');
  const q = filter.trim().toLowerCase();
  const shown = q
    ? items.filter(
        (i) => (i.label ?? '').toLowerCase().includes(q) || i.uuid.toLowerCase().includes(q),
      )
    : items;

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border p-2">
        <Input placeholder="Search private data…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>
      <div className="flex-1 overflow-y-auto">
        {shown.map((item) => (
          <button
            key={item.uuid}
            onClick={() => onSelect(item.uuid)}
            className={cn(
              'flex w-full flex-col items-start gap-0.5 border-b border-border px-3 py-2 text-left text-sm transition-colors',
              item.uuid === selectedId ? 'bg-accent text-foreground' : 'hover:bg-accent/50',
            )}
          >
            <span className="font-medium">{displayName(item)}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{item.uuid}</span>
          </button>
        ))}
        {shown.length === 0 && (
          <p className="p-3 text-sm text-muted-foreground">No entries.</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: PrivateDataDetail**

Create `apps/desktop/src/renderer/src/components/private-data/PrivateDataDetail.tsx`:
```tsx
import { lazy, Suspense, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { CopyButton } from '@/components/CopyButton';
import type { PrivateItem } from '@/lib/private-data-api';

const CodeEditorPopup = lazy(() =>
  import('@/components/CodeEditorPopup').then((m) => ({ default: m.CodeEditorPopup })),
);

interface Props {
  item: PrivateItem;
  getContent: (uuid: string) => Promise<string>;
  onSaveLabel: (uuid: string, label: string) => void;
  onSaveContent: (uuid: string, content: string) => void;
  onDelete: (uuid: string) => void;
}

export function PrivateDataDetail({ item, getContent, onSaveLabel, onSaveContent, onDelete }: Props) {
  const [label, setLabel] = useState(item.label ?? '');
  const [content, setContent] = useState('');
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setLabel(item.label ?? '');
    void getContent(item.uuid).then(setContent);
  }, [item.uuid, item.label, getContent]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <Input
          value={label}
          placeholder="Label (optional)"
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => label !== (item.label ?? '') && onSaveLabel(item.uuid, label)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            Edit content
          </Button>
          <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2 border-b border-border px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
        <span>uuid7</span>
        <span className="text-foreground">{item.uuid}</span>
        <CopyButton value={item.uuid} />
        <span className="ml-1">— reference in url4 as</span>
        <span className="text-foreground">/private/{item.uuid}</span>
      </div>

      <pre className="flex-1 overflow-auto whitespace-pre-wrap p-4 font-mono text-sm">
        {content || '(empty — click “Edit content”)'}
      </pre>

      {editing && (
        <Suspense fallback={null}>
          <CodeEditorPopup
            title={`Edit ${label || item.uuid.slice(0, 8)}`}
            language="markdown"
            value={content}
            onSave={(v) => {
              setContent(v);
              onSaveContent(item.uuid, v);
              setEditing(false);
            }}
            onClose={() => setEditing(false)}
          />
        </Suspense>
      )}

      {confirmDelete && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/80">
          <div className="border border-border bg-card p-4 text-sm">
            <p className="mb-3">Delete this entry? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmDelete(false)}>
                Cancel
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => {
                  setConfirmDelete(false);
                  onDelete(item.uuid);
                }}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```
Note: confirm `CodeEditorPopup`'s exact prop names from `components/CodeEditorPopup.tsx` (title/language/value/onSave/onClose) and `CopyButton`'s prop (`value`) when reading those files in this task; adjust if they differ.

- [ ] **Step 3: AddPrivateDataDialog**

Create `apps/desktop/src/renderer/src/components/private-data/AddPrivateDataDialog.tsx`:
```tsx
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface Props {
  onCancel: () => void;
  onCreate: (label?: string) => void;
}

export function AddPrivateDataDialog({ onCancel, onCreate }: Props) {
  const [label, setLabel] = useState('');
  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/80">
      <div className="w-80 border border-border bg-card p-4">
        <h2 className="mb-1 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          New private data
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          A uuid7 is assigned automatically. The label is optional and only used for navigation.
        </p>
        <Input
          autoFocus
          placeholder="Label (optional)"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onCreate(label.trim() || undefined)}
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => onCreate(label.trim() || undefined)}>
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Typecheck**

Run:
```bash
cd apps/desktop && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -E "private-data" || echo "no type errors in private-data components"
```
Expected: `no type errors in private-data components`.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/renderer/src/components/private-data
git commit -m "SF-269: Private Data list/detail/add components"
```

---

## Task 10: PrivateDataView

**Files:**
- Create: `apps/desktop/src/renderer/src/views/PrivateDataView.tsx`

Mirror `views/CodeStudioView.tsx`'s header + resizable split. Read it first to match layout.

- [ ] **Step 1: Write the view**

Create `apps/desktop/src/renderer/src/views/PrivateDataView.tsx`:
```tsx
import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '@/components/ui/resizable';
import { usePrivateData } from '@/hooks/use-private-data';
import { PrivateDataList } from '@/components/private-data/PrivateDataList';
import { PrivateDataDetail } from '@/components/private-data/PrivateDataDetail';
import { AddPrivateDataDialog } from '@/components/private-data/AddPrivateDataDialog';

export function PrivateDataView() {
  const { items, ready, create, update, remove, getContent } = usePrivateData();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selected = items.find((i) => i.uuid === selectedId) ?? null;

  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-xl">Private Data</h1>
          <p className="text-sm text-muted-foreground">
            Editable markdown entities. Reference any entry in url4 as <code>/private/&lt;uuid7&gt;</code>.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} disabled={!ready}>
          <Plus className="h-4 w-4" /> New entry
        </Button>
      </div>

      <ResizablePanelGroup direction="horizontal" autoSaveId="private-data-split" className="flex-1">
        <ResizablePanel id="private-data-list" defaultSize={40}>
          <PrivateDataList items={items} selectedId={selectedId} onSelect={setSelectedId} />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="private-data-detail" defaultSize={60}>
          {selected ? (
            <PrivateDataDetail
              item={selected}
              getContent={getContent}
              onSaveLabel={(uuid, label) => void update(uuid, { label: label || null })}
              onSaveContent={(uuid, content) => void update(uuid, { content })}
              onDelete={(uuid) => {
                void remove(uuid);
                setSelectedId(null);
              }}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Select an entry, or create one.
            </div>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>

      {creating && (
        <AddPrivateDataDialog
          onCancel={() => setCreating(false)}
          onCreate={async (label) => {
            const uuid = await create(label);
            setCreating(false);
            if (uuid) setSelectedId(uuid);
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add apps/desktop/src/renderer/src/views/PrivateDataView.tsx
git commit -m "SF-269: PrivateDataView"
```

---

## Task 11: Navigation wiring

**Files:**
- Modify: `apps/desktop/src/renderer/src/components/layout/Sidebar.tsx`
- Modify: `apps/desktop/src/renderer/src/App.tsx`

- [ ] **Step 1: Add the View id + nav entry (Sidebar.tsx)**

Add `'private-data'` to the `View` union (after `'code-studio'`):
```ts
  | 'code-studio'
  | 'private-data'
```
Import the icon (with the other `lucide-react` imports): add `FileText` to the import list. Add the nav entry to `coreItems` after the `code-studio` line:
```ts
  { id: 'private-data', label: 'Private Data', icon: FileText },
```

- [ ] **Step 2: Add the route branch (App.tsx)**

Import the view at the top of `App.tsx` (with the other view imports):
```ts
import { PrivateDataView } from '@/views/PrivateDataView';
```
Add a branch in `renderView()` next to the `code-studio` branch:
```ts
  if (currentView === 'private-data') return <PrivateDataView />;
```
(Read `App.tsx` first to match the exact import style and the `renderView` switch shape.)

- [ ] **Step 3: Build**

Run:
```bash
cd apps/desktop && npm run build 2>&1 | tail -3
```
Expected: `✓ built in …` (no TS errors).

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src/renderer/src/components/layout/Sidebar.tsx apps/desktop/src/renderer/src/App.tsx
git commit -m "SF-269: add Private Data nav item + route"
```

---

## Task 12: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Server tests green**

Run:
```bash
cd apps/server && uv run pytest src/screamingface/plugins/private_storage -v
```
Expected: all PASS.

- [ ] **Step 2: Desktop unit tests + build green**

Run:
```bash
cd apps/desktop && npx vitest run src/renderer/src/lib/__tests__/private-data-api.test.ts && npm run build 2>&1 | tail -2
```
Expected: vitest PASS; build `✓ built`.

- [ ] **Step 3: Manual smoke (one running dev app — close any existing first)**

Run `cd apps/desktop && npm run dev`. In the app:
1. Open **Private Data** in the sidebar.
2. Click **New entry**, optionally type a label → an item appears (keyed by uuid7).
3. **Edit content** → Monaco opens in markdown → type markdown → Save → preview updates.
4. Copy the uuid7; in **URL4 Studio** reference `/private/<uuid7>` and confirm it resolves to your markdown (same as `/data/*`).
5. Edit the label (blur) and Delete; confirm list updates.

Confirm the view matches Code Studio's look and the brand styling (square, hairline, mono labels, dark).

- [ ] **Step 4: Final commit (if any verification fixes were needed)**

```bash
git add -A && git commit -m "SF-269: verification fixes" || echo "nothing to commit"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** server plugin (Tasks 2–6), `/private` CRUD + raw-markdown GET (Task 4), DB persistence via `state` (Tasks 2,5), uuid7 key (Tasks 1,2,3), url4 parity test (Task 6), Private Data view mirroring Code Studio with Monaco markdown (Tasks 9–10), optional label / uuid7 identity (Tasks 3,9,10), nav entry + route (Task 11). All covered.
- **Verify-before-trust hooks:** Tasks note where to confirm real signatures (`/ensemble/format` url4 path, `useServerStatus` field names, `CodeEditorPopup`/`CopyButton` props, `App.tsx` switch shape) by reading the referenced files — adjust to match rather than assume.
- **Identity invariant:** uuid7 = pk = url4 handle; label is nav-only and mutable, never used for addressing (Tasks 3,4,9,10).
```
