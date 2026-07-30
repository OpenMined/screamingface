---
ticket: OME-625
stack: url4-cloud
status: in_progress
started: 2026-07-26
finished:
---

# OME-625 — Cached aigateway model-catalog endpoint on url4-cloud

> **Path note (added 2026-07-28).** Paths below are as of this unit. The url4-cloud tree has since
> been flattened: the `backend/`, `runner/` and `shared/` distributions merged into one
> (`apps/url4-cloud`, package `url4_cloud`, one image, two CLI modes), and the leftover `backend/`
> directory was removed. Read `backend/src/url4_cloud/X` as `apps/url4-cloud/src/url4_cloud/X`,
> and the former `shared/protocol` + `shared/bus` as `packages/url4`'s `url4.streaming` and
> `url4_cloud.adapters.jetstream`.


## Intent

`apps/url4-cloud` exposes no way to discover which models a run can address: the HTTP surface
is `POST /token`, `GET /?q=`, `DELETE /`, `WS /ws`, `/healthz` and the ops/docs routes. The
aigateway catalog is read in exactly one place today — `_list_models` inside the **Runner's**
connector — where it is consumed inside a Job Pod and never surfaced, so no user, UI, or SDK can
learn the addressable model set before composing an expression.

This unit adds a read-only, cached `GET /v1/models` to the url4-cloud **backend**, proxied from
aigateway. It is a **user-facing** discovery primitive; the Runner is deliberately not a consumer
and keeps its own `_list_models` (owner, 2026-07-26).

## Decisions

- **r1 (superseded):** unauthenticated · single shared cache entry · service credential.
- **r2 (superseded):** credential-optional · identity-keyed cache — after the owner required
  correctness under both aigateway credential modes.
- **r3 (current):** as r2, but the anonymous path and the service credential are **removed** —
  the owner confirmed callers are already authenticated when they reach url4-cloud, so the
  anonymous path bought nothing and cost a standing privileged secret.

**r3 in full:**

- **A credential is required.** Accepts the same headers `start_run` accepts
  (`Authorization: Bearer`, `X-Profile`) and forwards them upstream.
  No credential ⇒ 401 + `WWW-Authenticate: Bearer`, no upstream call. url4-cloud verifies
  nothing; aigateway remains the sole verifier.
- **No service credential — no new secret.** url4-cloud holds no aigateway credential, needs no
  chart Secret reference, and gains no rotation story. This is r3's main prize.
- **Identity-keyed cache** (SHA-256 of credential+profile). Correct under `byok` (answer is per
  account) and `shared` (answer is per active pool set).
- **No mode awareness.** url4-cloud never reads `AIGATEWAY_CREDENTIAL_MODE`; mode-agnosticism is
  structural, not conditional. Coupling two independently deployable apps through one app's
  setting is not on the table.
- **Backend endpoint only.** The Runner's `_list_models` is untouched.

Verified 2026-07-26: `credential_mode` is read only in aigateway's `routes/chat_credentials.py`
(lines 128, 356) and never reaches `routes/models.py` — so the catalog is caller-invariant
*today*. r2 deliberately does not depend on that, which is why r1's source-inspection guard test
is deleted rather than kept.

## Planned changes

Create:

- `backend/src/url4_cloud/catalog/{__init__,port,aigateway,cache}.py`
- `backend/src/url4_cloud/rest/catalog.py` — the route
- `backend/src/url4_cloud/rest/_credentials.py` — credential resolution extracted from
  `routes.py` so `start_run` and this endpoint cannot drift
- `tests/unit/test_catalog_port.py`, `test_catalog_cache.py`, `test_catalog_aigateway.py`,
  `test_rest_models.py`

Modify:

- `config.py` — `models_cache_ttl_s`, `models_cache_stale_max_s`,
  `models_cache_error_backoff_s`, `models_cache_max_entries`, `models_upstream_concurrency`
  (**no credential setting** — r3 introduces no secret)
- `app.py` — build/wire the catalog service (both `create_app` and `make_local_app`), include
  the router, close the httpx client on shutdown
- `rest/routes.py` — import the extracted credential helper (no behaviour change)
- `rest/__init__.py`, `metrics.py`

## Test plan

RED first, per batch. Headline cases:

1. **Port** — protocol conformance · ETag stability · distinct tokens ⇒ distinct keys ·
   `repr` leaks no token.
2. **Cache** (counting fake + injected clock, no I/O) — hit/miss/expiry · **20 concurrent
   misses on one key ⇒ 1 fetch** · **N distinct keys run in parallel, not serialised** ·
   **two credentials never observe each other's body** · stale-on-error, bounded ·
   **cold failure creates no entry** · failure backoff · LRU eviction at `max_entries` ·
   **bulkhead high-water mark never exceeds `upstream_concurrency`** · hot path takes no lock.
3. **Adapter** (`httpx.MockTransport`) — parse · non-JSON · malformed shape · 401 ⇒
   `CatalogRejected` · 5xx ⇒ `CatalogBadResponse` · timeout ⇒ `CatalogUnavailable` · header
   forwarding · no token in logs.
4. **Route** (`TestClient`) — 200 shape · **two credentials ⇒ different bodies** ·
   **no credential ⇒ 401 +
   `WWW-Authenticate`, upstream never called** · `Vary` always present · `Cache-Control` always
   `private` · ETag / `If-None-Match` ⇒ 304 · `max-age` decays · 503 unconfigured · 401/502/504
   mapping · never 500 · in `app.openapi()`.
5. **Wiring** — factory contract · injectable in both app factories · shutdown closes client ·
   **no metric label contains a credential or cache key** · **no `Settings` field holds an
   aigateway credential**.

Existing `test_rest.py` must pass **unchanged** across the credential-helper extraction, which
ships as its own commit ahead of the feature so the refactor is bisectable on its own.

## Acceptance

- `GET /v1/models` returns aigateway's catalog verbatim, in the served OpenAPI/Scalar reference.
- No credential ⇒ 401 + `WWW-Authenticate: Bearer`, and no upstream call.
- Same credential inside the TTL ⇒ no upstream call; different credentials ⇒ independent entries.
- Concurrent misses on one key ⇒ one upstream call; distinct keys not serialised.
- Concurrent upstream fetches never exceed `models_upstream_concurrency`.
- aigateway down + warm ⇒ stale; + cold ⇒ RFC 9457 problem, never a 500.
- Rejected credential ⇒ 401 and no cache entry.
- `Vary` on every response; `Cache-Control` always `private`.
- **No new secret:** no setting holds an aigateway credential.
- `run_gates.py` green for `url4-cloud`; no test performs network I/O.

## Outcome

- **Actual files:** as planned, plus `backend/src/url4_cloud/rest/_credentials.py` (the Batch 4a
  extraction) and `tests/unit/test_catalog_wiring.py`. Also touched: `metrics.py` (catalog
  collector), `schemas/openapi.py` (Catalog tag), `rest/__init__.py`, `README.md`,
  `deploy/helm/templates/configmap.yaml` (comment only).
- **Gates:** `run_gates.py url4-cloud` — ALL GREEN (append-only check · ruff check · ruff format
  · pyright · pytest+coverage). **367 passed, 3 skipped**, up from 333 at branch point — 71 new
  tests. Coverage: `catalog/port.py` 100%, `catalog/aigateway.py` 100%, `catalog/__init__.py`
  100%, `rest/catalog.py` 100%, `rest/_credentials.py` 100%, `catalog/cache.py` 98%; total 99%.
- **Commits:** see below.

### Deviations

1. **Failure backoff records state only for keys with a prior success.** The plan implied
   per-key backoff for every key. Recording it for unknown keys would have re-opened the
   cache-key flooding vector the same section closes, so `_Entry` (which holds the failure
   state) only ever exists for a key that has succeeded at least once — making "a cold failure
   caches nothing" true *by construction* rather than by convention. Unknown keys are bounded by
   the semaphore bulkhead instead. Documented on `_Entry` and `_on_failure`.
2. **Chart tunables for the five `models_cache_*` settings were NOT added.** They have sound code
   defaults and no known need to vary per deployment; five knobs × (values.yaml + values.schema.json
   + configmap) is surface for nothing (YAGNI). `config.aigatewayBaseUrl` already flows to
   `URL4_CLOUD_AIGATEWAY_BASE_URL`, so the feature works on the existing chart with no value
   change — the configmap comment now says so.
3. **A second protocol, `CatalogService` (`fetch` + `max_age_s`), was introduced** alongside the
   spec's `CatalogSource`. `max_age_s` is a property of a *cache entry*, not of a catalog, so it
   has no meaning on a bare adapter; the route types against the wider protocol and tests inject a
   fake without subclassing the cache.
4. **The extracted helpers were renamed** `_bearer` → `bearer_token` and `_forwarded_credential` →
   `forwarded_credential`, since they are no longer private to `routes.py`. No behaviour change;
   `test_rest.py` and `test_credential_forwarding.py` (25 tests) passed unchanged across the
   extraction commit.

### Bugs the gates/tests caught (worth recording)

- `make_local_app` initially registered `aclose` on an **injected** catalog it did not own — and
  `CatalogService` has no `aclose`. Fixed by the "close only what you built" rule, matching
  `build_aigateway_world`'s treatment of an injected httpx client.
- A `str.replace` during wiring edited **two** call sites, leaving `create_app_from_env`
  referencing an undefined `owned_catalog`. Invisible to tests (that function is
  `# pragma: no cover` — env/NATS wiring), caught by ruff `F821`.
