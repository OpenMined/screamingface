---
title: url4-cloud model catalog endpoint — technical specification
status: implemented — shipped in `92fdf233`; live at `apps/url4-cloud/src/url4_cloud/rest/catalog.py`
created: 2026-07-26
revised: 2026-07-26 (r3 — credential required; no service secret; mode-agnostic by construction)
author: Claude (Opus 5) + Ionesio
ticket: OME-625
related:
  - https://linear.app/openmined/issue/OME-625
  - docs/spec/2026-07-21-url4-cloud.md              # the app this extends
  - docs/spec/2026-07-24-aigateway-shared-credential-pools-spec.md
  - apps/aigateway/src/aigateway/routes/models.py   # the upstream being proxied
---

# url4-cloud model catalog endpoint (v1)

## 0. Status & revision history

Proposed. Implementation starts only on explicit approval.

| Rev | Change | Why |
|---|---|---|
| r1 | Unauthenticated · one shared cache entry · service credential | Initial owner forks. |
| r2 | Credential-optional · identity-keyed cache | Owner required correctness under aigateway `byok` **and** `shared`. |
| **r3** | **Credential required · no service credential · no new secret** | Owner confirmed callers are already authenticated when they reach url4-cloud, so the anonymous path bought nothing and cost a standing privileged secret. |

## 1. Purpose & scope

### 1.1 The gap

`apps/url4-cloud` has no catalog surface. Its complete HTTP surface is `POST /token`,
`GET /?q=<url4>`, `DELETE /`, `WS /ws`, `/healthz`, and the ops/docs routes
(`ops.py:71-110`). A client composing a url4 expression such as `/model('')!'intent'` has no
way to learn which `model` paths are addressable.

The aigateway catalog is read in exactly one place today: `_list_models` in the **Runner's**
connector (`runner/src/url4_cloud_runner/aigateway_connector.py`), invoked from
`build_aigateway_world`. It is consumed inside a Job Pod and **never surfaced** — so there is no
answer a user or an SDK can ask for.

> **This endpoint is a USER-FACING surface** (owner, 2026-07-26). It exists so a human, a UI, or
> an SDK can discover the addressable model set. The Runner is deliberately **not** a consumer and
> keeps its own `_list_models` — see §1.3 and §10.

### 1.2 What this adds

A read-only `GET /v1/models` on the url4-cloud **backend** that forwards the caller's own
aigateway credential upstream and serves the result from an **identity-keyed** TTL cache with
per-key single-flight, stale-on-error, failure backoff, a bounded LRU, and an upstream
concurrency bulkhead.

### 1.3 Non-goals

- **Serving the Runner.** The Runner is not a consumer of this endpoint, now or later (§10).
- Anonymous / pre-authentication access (§3 D1).
- url4-cloud holding any aigateway credential of its own (§3 D2).
- url4-cloud interpreting or reshaping the catalog.
- Any change to `apps/aigateway`.
- Pagination (§5.4 records the deliberate deviation).

## 2. The upstream contract, and what actually varies

`apps/aigateway/src/aigateway/routes/models.py`:

```python
@router.get("/v1/models")
async def list_models(request: Request, _current: CurrentAccount) -> dict:
    registry = request.app.state.providers
    data = [... for plugin in registry.all() for entry in plugin.register_models()]
    return {"object": "list", "data": data}
```

**Verified 2026-07-26:** `credential_mode` is read only in `routes/chat_credentials.py`
(lines 128, 356 — the chat dispatch path). It never reaches `routes/models.py` or the provider
registry. So the catalog body is, *today*, identical under `byok` and `shared`, and identical
for every account. It is nonetheless **auth-gated** (`CurrentAccount`), which is the single most
consequential fact in this spec: url4-cloud cannot answer without *some* credential.

### 2.1 Why the design must not rely on caller-invariance

"Which models does this gateway support" is caller-invariant today. "Which models can *I*
actually call" is not, and the two converge the moment aigateway makes the catalog reflect
usable credentials:

- **`byok`** — an account can only really call providers it has connected
  (`OAuthConnection` / api-key per `Profile`). The usable subset is **per account**.
- **`shared`** — the usable set is whichever `GlobalCredentialPool`s an admin has activated.
  Caller-invariant, but **deployment-state-dependent**, and a different answer from byok.

Given aigateway shipped shared credential pools on 2026-07-24, a catalog that reflects usable
credentials is a plausible near-term change rather than a hypothetical. r3 therefore does not
assume caller-invariance — and consequently needs no test guarding that assumption.

### 2.2 url4-cloud does not know about credential modes

Explicit non-goal: url4-cloud never reads, forwards, or branches on
`AIGATEWAY_CREDENTIAL_MODE`. That would couple two independently deployable apps through a
setting belonging to one of them, violating the monorepo rule that apps share only stable HTTP
contracts. Mode-agnosticism is achieved **structurally** — by treating the caller's credential as
part of the cache key — not by branching on the mode.

## 3. Design decisions (r3)

| # | Fork | Decision | Rationale |
|---|---|---|---|
| **D1** | Authentication | **A credential is required.** The endpoint accepts the same credential headers `start_run` accepts (`Authorization: Bearer`, `X-Profile`) and forwards them upstream. No credential ⇒ 401. | Owner confirmed callers are authenticated before reaching url4-cloud (`apigw → url4-cloud`). url4-cloud verifies nothing; aigateway remains the sole verifier, exactly as with `bearer_token` (`rest/_credentials.py`). |
| **D2** | Service credential | **None.** url4-cloud stores no aigateway credential. | Directly follows from D1: with no anonymous path there is nothing for a service credential to serve. This is the decision's main prize — **no new secret, no chart Secret reference, no rotation story** in an app that holds none today. |
| **D3** | Cache key | **Identity-keyed.** Key = SHA-256 of `(credential, profile)`. | The only design correct under both modes (§2.1). Also the natural consequence of D1: the credential is already on the request. |
| **D4** | Scope | **Backend endpoint only.** The Runner's `_list_models` is untouched. | Keeps the blast radius reviewable; avoids a Runner→backend dependency on the run-critical path. |
| **D5** | Mode awareness | **None.** | §2.2. |

## 4. Credential resolution

Reuses the rule `start_run` already established, so the two entry points cannot drift:

1. `Authorization: Bearer <token>` — the only credential source.
2. Absent, or a non-Bearer scheme → **401** (§5.3).

`X-Profile` is forwarded and participates in the cache key. A profile label with no credential
to scope is discarded along with the request itself, since (2) already rejects it — consistent
with `start_run`'s rule at `rest/routes.py:349`.

The credential is never logged, never placed in a metric label, and never echoed in a response.
The cache key is a **hash**, so raw credentials are never held as dict keys.

## 5. The endpoint

### 5.1 Request

```http
GET /v1/models HTTP/1.1
Authorization: Bearer <aigateway credential>     ; required
X-Profile: <routing profile>                     ; optional
If-None-Match: "a3f1c09e4b2d7f81"                ; optional
```

### 5.2 Success

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "a3f1c09e4b2d7f81"
Cache-Control: private, max-age=247
Vary: Authorization, X-Profile
```
```json
{
  "object": "list",
  "data": [
    {"id": "claude-haiku-4-5", "object": "model", "owned_by": "anthropic"},
    {"id": "openrouter/meta-llama/llama-3.3-70b", "object": "model", "owned_by": "openrouter"}
  ]
}
```

- **Body is aigateway's, verbatim.** url4-cloud is a proxy, not a reshaper. Verbatim keeps the
  response OpenAI-tool-compatible and means an added upstream field needs no change here.
- **`Cache-Control` is unconditionally `private`** — every response is now tied to a caller
  credential, so there is no public variant to reason about (an r2 complication D2 removes).
  `max-age` carries the entry's *remaining* TTL so a downstream cache expires in step with ours.
- **`Vary` is mandatory** and is the header-level counterpart of D3. Without it, any shared cache
  between client and app could do exactly the cross-account mixing the keyed cache prevents.
- **`ETag`** is a strong validator: first 16 hex of SHA-256 over the canonical serialized body.
  Derived from the body alone, so two callers with identical catalogs share an ETag — correct,
  since those are byte-identical representations.

`If-None-Match` matching that caller's current ETag ⇒ `304 Not Modified`, no body.

### 5.3 Failures — RFC 9457 `application/problem+json`

Reusing the app's existing `Problem` / `ProblemException` / `install_problem_handlers`
(`auth/problem.py`), so these render like every other url4-cloud error.

| Status | Condition | Notes |
|---|---|---|
| **401** | No credential supplied, **or** aigateway rejected the one supplied | Carries `WWW-Authenticate: Bearer`. Both cases share one generic `detail` — distinguishing them would tell an unauthenticated caller whether a token is *recognised*. |
| **502** | Upstream returned a bad status, non-JSON, or a malformed shape | |
| **503** | `aigateway_base_url` is not configured | Mirrors the `_deps` guard (`rest/routes.py:57`) — same class of misconfiguration, same treatment. |
| **504** | Upstream timed out | |

**Never a 500**, never a 200-with-error-body. Upstream detail is logged, never returned: the
endpoint must not describe this deployment's aigateway configuration to a caller whose
credential it has not verified.

### 5.4 Pagination — deliberate deviation

Standard practice paginates every list endpoint from day one. Not here:

- The set is bounded and small (the provider plugin registry — tens of entries) and does not
  grow with usage, tenants, or time.
- The upstream returns it unpaginated, so url4-cloud would invent a cursor contract over a
  payload it fetches whole regardless — pure cost, no benefit.
- The OpenAI `/v1/models` convention every client already implements is unpaginated.

Revisit above ~500 entries.

## 6. Internal design

### 6.1 Module layout

Mirrors the app's established port/adapter/factory shape (`jobs/port.py`, `jobs/k8s.py`,
`jobs/inprocess.py`, `jobs/factory.py`) so it reads like the code around it:

```
src/url4_cloud/catalog/
    __init__.py      exports + build_catalog_service(settings)
    port.py          CatalogSource protocol · Credential · ModelCatalog · error hierarchy
    aigateway.py     AigatewayCatalogSource — the httpx adapter
    cache.py         CachedCatalog — keyed TTL · per-key single-flight · stale-on-error
src/url4_cloud/rest/
    _credentials.py  credential resolution shared with routes.py (extracted, not duplicated)
    catalog.py       the GET /v1/models route
```

### 6.2 The port

```python
@dataclass(frozen=True, slots=True)
class Credential:
    """A caller-supplied upstream identity. `token` is the raw secret; `key` is its hash."""

    token: SecretStr
    profile: str | None
    key: str  # sha256(token, profile)[:32] — never the raw token


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    body: dict[str, object]
    etag: str


class CatalogSource(Protocol):
    async def fetch(self, credential: Credential) -> ModelCatalog: ...
```

`CachedCatalog` **wraps a `CatalogSource` and is itself a `CatalogSource`** — a decorator. That
is what lets every cache test drive a counting in-memory fake with no HTTP, and lets the route
depend on one type either way.

### 6.3 Cache semantics

Cache-aside, keyed by `Credential.key`, per the standard treatment of hot, small, slow-changing
data. In-process rather than shared (Redis): entries are a few KB, the App is stateless and
horizontally scaled, and per-replica caching bounds upstream load at *replicas × keys per TTL*
instead of *requests per TTL* — the whole goal — with no new infrastructure dependency.

Five composed behaviours:

1. **TTL** (`models_cache_ttl_s`, default 300s) per entry.
2. **Per-key single-flight.** One in-flight future per key; concurrent misses on the same key
   collapse to a single upstream call. Distinct keys proceed in parallel — a global lock would
   serialise unrelated accounts.
3. **Stale-on-error.** A refresh that fails while that key has a previous entry serves it and
   logs a warning; the cache never fails open into "no models". Bounded by
   `models_cache_stale_max_s` (default 3600s) — serve cached, refuse cold.
4. **Per-key failure backoff** (`models_cache_error_backoff_s`, default 30s). Single-flight
   collapses *concurrent* misses; this bounds *sequential* ones.
5. **Bounded LRU** (`models_cache_max_entries`, default 256) — see §7.

**Only successful fetches populate an entry.** Errors are never cached as results.

### 6.4 Wiring

`create_app` builds the service via `build_catalog_service(settings)` and stores it on
`app.state.catalog`, following the existing `bus` / `job_runner` / `interest` injection
convention and accepting an injectable `catalog=` parameter for tests. `make_local_app` wires it
identically, so local mode has the endpoint. The adapter owns one `httpx.AsyncClient`, closed on
ASGI shutdown alongside `bus.close` / `runner.aclose`.

The service is built whenever `aigateway_base_url` is configured — there is no credential to
configure, so that is the only precondition.

## 7. Security consequences of identity-keying

Keying on a credential url4-cloud *does not verify* introduces two vectors. Both are closed by
design, not by convention:

| Vector | Closure |
|---|---|
| **Cache-key flooding** — an attacker sends N distinct bogus tokens to exhaust memory. | Bogus tokens get 401 upstream, and **failures never create entries**, so no entry is minted. The LRU cap (`models_cache_max_entries`, 256) bounds the honest case regardless. Keys are fixed-length hashes, so key size is attacker-independent. |
| **Upstream amplification** — N distinct keys ⇒ N upstream calls, bypassing single-flight. | A **bulkhead**: an `asyncio.Semaphore` (`models_upstream_concurrency`, default 8) caps concurrent upstream catalog fetches process-wide. url4-cloud can never issue more than that many, whatever arrives. Overflow waits, then fails 504 rather than queueing unboundedly. |

The bulkhead bounds *concurrency*, not total request rate; the apigw in front of url4-cloud is
the rate-limiting layer, and this is the in-app backstop for when it is misconfigured or bypassed.

Note that D1/D2 already removed the largest security item in r1: with no service credential,
there is no standing privileged secret in url4-cloud to steal, and no anonymous enumeration of
the deployment's provider set.

## 8. Configuration

New `URL4_CLOUD_*` settings on `config.py`. **No new secret** — see D2.

| Setting | Default | Notes |
|---|---|---|
| `models_cache_ttl_s` | `300.0` | Freshness budget. |
| `models_cache_stale_max_s` | `3600.0` | Ceiling on stale-on-error service. |
| `models_cache_error_backoff_s` | `30.0` | Minimum gap between failed refreshes per key. |
| `models_cache_max_entries` | `256` | LRU cap (§7). |
| `models_upstream_concurrency` | `8` | Upstream bulkhead (§7). |

`aigateway_base_url` **already exists** (forwarded into Runner Jobs) and is reused — the same
aigateway Service URL. No new setting, and no chart Secret reference required by this feature.

## 9. Observability

Counters on the existing per-app OpenMetrics registry (`metrics.py` / `build_metrics()`):
cache hits, misses, stale-serves, upstream failures, bulkhead waits, and live entry count.
Without these, "is the cache working in prod" is unanswerable. **No metric is labelled by
credential or cache key** — that would reintroduce the identity leak at the metrics endpoint.

## 10. The Runner is not a consumer

An earlier draft floated repointing the Runner's `build_aigateway_world` at this endpoint to save
its per-Job-boot upstream fetch. **The owner ruled that out on 2026-07-26: this endpoint is for
users.** Recorded here so the idea is not rediscovered as an optimisation.

Why it would be a poor trade even ignoring intent: it puts a Runner→backend hop on the
run-critical path, so a backend blip could fail runs that aigateway alone would have served — a
strictly worse availability story than the Runner's current direct call. The Runner keeps
`_list_models`; the duplication between it and §6.1 is deliberate (they parse for different
purposes — see the `AIDEV-NOTE` in `catalog/aigateway.py`).

### Open question for the user-facing direction

There is **no CORS handling anywhere in url4-cloud** — not in the app, not in the chart. Any
browser client on a different origin will be blocked, and the required `Authorization`
header guarantees a preflight. This is pre-existing and applies equally
to `POST /token` and `GET /?q=`, so it is out of scope here, but it is the next thing a
browser-based consumer will hit. It needs its own ticket and a deliberate origin allowlist —
never `*`, since these are credentialed requests.

## 11. Acceptance

1. `GET /v1/models` returns aigateway's catalog verbatim, documented in the served
   OpenAPI/Scalar reference.
2. A request with no credential ⇒ 401 + `WWW-Authenticate: Bearer`, and no upstream call.
3. Same credential inside the TTL ⇒ no upstream call.
4. Two **different** credentials receive independently cached responses and never share an
   entry — the byok-correctness property.
5. Concurrent cold-cache requests **on one key** ⇒ exactly one upstream call; distinct keys are
   not serialised behind each other.
6. Concurrent upstream fetches never exceed `models_upstream_concurrency`.
7. aigateway down + warm entry ⇒ stale served; + cold ⇒ RFC 9457 problem, never a 500.
8. A rejected credential ⇒ 401 and **no** cache entry.
9. `Vary` present on every response; `Cache-Control` always `private`.
10. No new secret is introduced: no setting holds an aigateway credential.
11. `run_gates.py` green for `url4-cloud`; no test performs network I/O.
