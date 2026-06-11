# Design Spec — Private Storage plugin (`/private/{uuid7}`) + Private Data UI

- **Ticket:** SF-269 — https://app.asana.com/1/1185126988600652/project/1213628819033917/task/1215643830854867
- **Date:** 2026-06-11
- **Status:** Design (awaiting review) → implementation plan to follow
- **Branch:** `SF-269-private-storage-plugin`

## Context

During the demo period we need user-editable content entities that url4 can pull in as a context/content source — the same role `/data/*` plays today, but **editable from the app UI and persisted in a database** (the `/data` store is ephemeral and in-memory). This is a **temporary demo-period entity**, not a permanent subsystem.

The feature has two halves: a **server plugin** `private-storage` serving `/private/{uuid7}` (CRUD, DB-backed, returns raw markdown for url4), and a **desktop UI** view "Private Data" — same look as Code Studio (SF-262) but editing plain markdown. Each entity's primary key is a **uuid7**; an optional human **label** is used only for navigation. The uuid7 is what gets referenced in url4 as `/private/{uuid7}`, exactly like `/data/*`.

## Scope

**In scope:**
- Server plugin `private-storage` (DB-backed CRUD at `/private`).
- Desktop "Private Data" view mirroring Code Studio, Monaco markdown editor.
- Sidebar nav entry + route.
- url4 consumption works with **zero url4 changes** (relative-URL fetch already covers any `/path`).

**Out of scope:**
- A bespoke markdown editor (use Monaco `language="markdown"` — decided).
- Auth/sharing/multi-user; access control beyond what `/data` already has.
- Permanence guarantees / migrations strategy beyond a single Tortoise model (this is a demo entity).
- Web portal / cloud surfaces.

## Reference points (verified)

- **`/data` plugin:** `apps/server/src/screamingface/plugins/data_store/` — `plugin.py` (`DataStorePlugin(Plugin)`, `setup()` attaches `app.state.blob_store`, `routes.add_router(self.name, router, prefix="")`), `routes.py` (`POST /data`, `GET /data/{key}` returning raw bytes with stored content-type), `storage.py` (in-memory `BlobStore`). Registered in `apps/server/sf.json` `plugins`.
- **url4 consumption:** `plugins/url4_executor/url4_resolve.py::_fetch_relative` resolves any `Url4RelUrl` (`/…`) via in-process `httpx.ASGITransport` GET against the app. `/data/{key}` and `/private/{uuid7}` are handled identically — no node type or grammar change.
- **Durable persistence pattern:** Tortoise ORM via the `state` plugin (as `plugins/eval_runs/models/`). New plugin declares `depends: ["state"]` and registers its models.
- **Code Studio UI:** `apps/desktop/src/renderer/src/views/CodeStudioView.tsx` (resizable list+detail, header with "New" + panel-collapse toggles), `components/code/{CodeScriptsList,CodeScriptDetail,AddCodeScriptDialog}.tsx`, `hooks/use-code-scripts.ts`, full-screen `components/CodeEditorPopup.tsx` (Monaco via `@monaco-editor/react`, accepts `language`). Nav: `View` union + `coreItems` in `components/layout/Sidebar.tsx`; view switch in `App.tsx`. Uses shared `components/ui/` primitives (so brand styling is inherited).
- **uuid7:** no stdlib support (Py 3.12); add the `uuid6` package → `from uuid6 import uuid7`.

## Server plugin — `private-storage`

Directory `apps/server/src/screamingface/plugins/private_storage/`:

```
__init__.py
plugin.py     # PrivateStoragePlugin(Plugin), depends=["state"], tags=["product:system","lifecycle:demo"]
routes.py     # create_router(): the /private endpoints
models.py     # Tortoise model PrivateEntity
store.py      # thin async data-access helpers over the model (keeps routes slim)
tests/test_private_storage.py
```

**Model** (`models.py`):
```python
class PrivateEntity(Model):
    uuid7 = fields.CharField(max_length=36, pk=True)
    label = fields.CharField(max_length=200, null=True)
    content = fields.TextField(default="")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
```
SQLite locally / Postgres hosted via the existing `state` Tortoise setup (no new DB wiring).

**Routes** (`/private`):

| Method · path | Body | Returns | Purpose |
| --- | --- | --- | --- |
| `POST /private` | `{label?, content}` (JSON) | `{uuid, url:"/private/<uuid7>", label}` | create; server mints uuid7 |
| `GET /private/{uuid7}` | — | **raw markdown**, `Content-Type: text/markdown` | **url4 + editor content load** (mirrors `/data` raw GET) |
| `PUT /private/{uuid7}` | `{label?, content?}` (JSON) | `{uuid, label}` | update content and/or label |
| `DELETE /private/{uuid7}` | — | `204` | delete |
| `GET /private` | — | `[{uuid, label, updated_at}]` (JSON) | list for the UI nav (the one endpoint `/data` lacks) |

Design notes:
- `GET /private/{uuid7}` returns **raw markdown** (not JSON) so url4's `_fetch_relative` gets content directly, byte-for-byte like `/data/{key}`. 404 when missing.
- The UI loads the **list** (`GET /private`) for navigation and the **raw single** GET for editor content; create/update use JSON bodies carrying `label`+`content`.
- `plugin.py` registers the router (`routes.add_router(self.name, router, prefix="")`) and the Tortoise models with the `state` plugin in `setup()`. Add `"private-storage"` to `apps/server/sf.json` `plugins`.

**url4** — no changes. `/private/{uuid7}` is a `Url4RelUrl`; resolution fetches it in-process and feeds the raw markdown into the chain, identical to `/data/*`. (Validated by a plugin test that resolves a url4 expression referencing a stored entity.)

## Desktop UI — "Private Data"

Mirror Code Studio structure; swap python→markdown and name-key→uuid7+label.

- **`views/PrivateDataView.tsx`** — clone of `CodeStudioView` layout: header (`h1` "Private Data", "New" button, panel-collapse toggles) + `ResizablePanelGroup` (list | detail).
- **`components/private-data/PrivateDataList.tsx`** — searchable list; each row shows `label` (fallback: `private/<short-uuid7>`), subtitle = updated_at. Filter matches label + uuid substring.
- **`components/private-data/PrivateDataDetail.tsx`** — editable **label** field (optional; blank allowed), the immutable **uuid7** shown as mono with a copy button (this is the url4 handle), a content preview (`<pre>` raw markdown — consistent with Code Studio's read-only preview), **"Edit content"** → existing `CodeEditorPopup` with `language="markdown"`, and Delete (with confirm).
- **`components/private-data/AddPrivateDataDialog.tsx`** — optional label input only; on confirm → `POST /private` (server mints uuid7), select the new item.
- **`hooks/use-private-data.ts`** — talks to the **local server over HTTP** (`GET/POST/PUT/DELETE /private`), reusing the app's existing local-server fetch client (the same base used by `use-code-scripts`' `POST /plugins/python-runner/settings` and the backend-status hooks). Returns `{ items, loading, error, create(label?), update(uuid,{label?,content?}), remove(uuid), getContent(uuid) }`. Item shape `{ uuid: string; label: string | null; updated_at: string }`.
- **Navigation** — add `'private-data'` to the `View` union and a `coreItems` entry (icon `FileText` or `Lock`) in `Sidebar.tsx`; add the route branch in `App.tsx`. Styling is inherited from the shared `ui/` primitives.

> Identity rule, made explicit: the **uuid7 is the primary key and the url4 handle**; `label` is cosmetic/navigation only and never used for addressing. Editing a label never changes the uuid7.

## Data flow

1. **Create:** UI `AddPrivateDataDialog` → `POST /private {label?, content:""}` → server `uuid7()` + DB insert → returns `{uuid,…}` → list refreshes, item selected.
2. **Edit content:** "Edit content" opens Monaco (markdown) preloaded via `GET /private/{uuid7}` (raw) → save → `PUT /private/{uuid7} {content}` → preview refreshes.
3. **Use in url4:** user copies the uuid7, writes `/private/{uuid7}` in a url4 expression → executor `_fetch_relative` GETs it in-process → raw markdown enters the chain (same as `/data/*`).

## Error handling

- Server: 404 on unknown uuid7 (GET/PUT/DELETE); 400 on malformed body; label length capped (200). DB errors surface as 500 (logged).
- UI: hook surfaces errors as toasts (reuse `use-toast`); optimistic-free (refetch list after mutations) to stay simple; disable Save while in-flight.

## Testing

- **Plugin pytest** (`tests/test_private_storage.py`, TestClient + app fixture like `data_store` tests): create→get raw→update→list→delete; 404 paths; **url4 resolution test** — store an entity, resolve a url4 expression containing `/private/{uuid7}`, assert the markdown is returned.
- **UI smoke** (manual, dark theme): create with/without label, edit markdown in Monaco, copy uuid7, delete; confirm the view matches Code Studio's look and the brand styling.

## Risks / open questions

- **Local-server base URL in the renderer:** confirm the exact existing fetch client/base the UI uses for `/plugins/...` calls and reuse it (don't introduce a second client). Verified to exist via `use-code-scripts` settings POST; pin the precise helper during planning.
- **uuid7 dependency:** adding `uuid6` to `apps/server/pyproject.toml` (+ `uv sync`). If undesirable, fall back to `uuid4().hex` — but the ticket explicitly says uuid7, so `uuid6` is the plan.
- **Demo lifecycle:** tagged `lifecycle:demo`; teardown/removal after the demo is a separate concern, noted not built.
- **Content size:** markdown is `TextField` (unbounded); fine for demo. No pagination on `GET /private` (demo-scale list).

## Summary

A DB-backed `private-storage` plugin exposing `/private/{uuid7}` (raw-markdown GET for url4 parity, plus list/create/update/delete for the UI), and a "Private Data" desktop view mirroring Code Studio with a Monaco markdown editor. uuid7 is the primary key and url4 handle; label is navigation-only. url4 needs no changes. Temporary demo entity.
