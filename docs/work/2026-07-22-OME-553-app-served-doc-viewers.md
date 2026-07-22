---
ticket: OME-553
stack: url4-cloud
status: in_progress
started: 2026-07-22
finished: 2026-07-22
---

# OME-553 — App-served API doc viewers (fix `/scalar`, add `/asyncapi`)

## Intent

Two doc-viewer gaps found while viewing the specs in a browser: `/scalar` renders "Not Found" (the
Scalar CDN embed in `ops.py` uses the stale `<script id="api-reference" data-url>` form the current
standalone build no longer auto-mounts), and AsyncAPI has no rendered page (only raw
`/asyncapi.json`). Fix: render **both** viewers in the app, same-origin — so `docker compose`
(which already runs the `app` service on :9108) serves them, no extra containers / no CORS.

## Planned changes

- `src/url4_cloud/ops.py` — rewrite `_SCALAR_HTML` to the current
  `Scalar.createApiReference('#app', {url:'/openapi.json'})` form; add `_ASYNCAPI_HTML` + a
  `GET /asyncapi` HTML endpoint using the AsyncAPI web-component (`<asyncapi-component
  schemaUrl="/asyncapi.json">`). Raw JSON stays at `/asyncapi.json`.
- `tests/unit/test_docs_ops.py` — AUTHORIZED edit: `test_scalar_returns_html_referencing_openapi`
  asserts the new `createApiReference` init (not the old `api-reference` id). NEW `/asyncapi` page
  test (append).
- `apps/url4-cloud/docs/protocol.md §9` — note the two app-served reference pages.

## Test plan

- RED: `/scalar` HTML contains `createApiReference` + `/openapi.json` (fails against the old
  `data-url` embed). `GET /asyncapi` → 200 `text/html` containing `asyncapi-component` +
  `/asyncapi.json` (fails — route doesn't exist yet, 404).
- Render is **browser-verified** (unit tests lock the endpoint contract; a screenshot confirms the
  CDN components actually mount).

## Acceptance

- `GET /scalar` renders the OpenAPI reference; `GET /asyncapi` renders the AsyncAPI channel (both
  browser-verified via `docker compose` on :9108); `run_gates.py url4-cloud` green.

## Outcome

- **Actual files:** `src/url4_cloud/ops.py` (rewrote `_SCALAR_HTML` to the current
  `Scalar.createApiReference('#app', {url})` init; added `_ASYNCAPI_HTML` + a `GET /asyncapi`
  HTML endpoint via the AsyncAPI web-component; docstring notes both app-served viewers) ·
  `tests/unit/test_docs_ops.py` (AUTHORIZED edit: `test_scalar_returns_html_referencing_openapi`
  now asserts `createApiReference`; NEW `test_asyncapi_reference_page_renders_the_ws_schema`).
- **Commits:** see the OME-553 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud --skip-append-only` GREEN (append-only skipped — the
  `test_docs_ops.py` assertion change is the authorized contract edit for this ticket; ruff ·
  format · pyright · pytest · cov ≥ 80).
- **Deviations:** the browser (docker-compose) *visual* render check of `/scalar` + `/asyncapi`
  is folded into the owner's test pass — the unit tests lock the endpoint contract, but the CDN
  components mounting is confirmed by eye, not by CI. **Owner-verify:** open `/scalar` and
  `/asyncapi` on the running app and confirm both render.

## Follow-up (2026-07-22) — AsyncAPI viewer rendered unstyled

Owner-verify (compose `:9108`, real browser) found `/scalar` fully styled but **`/asyncapi`
rendered UNSTYLED**: `@asyncapi/web-component` renders into a **shadow DOM**, so the
`<link rel="stylesheet">` in `<head>` never crosses the shadow boundary (no console/network error —
the CSS loads, it just can't reach the component). **Fix:** drop the head `<link>` and hand the
stylesheet to the component via its **`cssImportPath`** attribute (loaded into the shadow root).
New test `test_asyncapi_page_imports_component_css_into_shadow_root`; re-verified styled in-browser
after `docker compose up --build`. Gates GREEN; commit `Refs: OME-553`.
