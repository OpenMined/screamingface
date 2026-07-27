---
title: url4-cloud model catalog endpoint — implementation plan
status: proposed — awaiting owner approval
created: 2026-07-26
revised: 2026-07-26 (r3 — credential required; no service secret)
ticket: OME-625
spec: docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md
ledger: docs/work/2026-07-26-OME-625-url4-cloud-model-catalog.md
---

# Implementation plan — OME-625 (r3)

Branch `OME-625-url4-cloud-model-catalog`. Stack `url4-cloud` (`sdlc-python`), TDD RED→GREEN per
batch, `run_gates.py` between batches. Conventional commits, body `Refs: OME-625`.

**r3 vs r2:** the anonymous path and the `aigateway_token` setting are gone (spec D1/D2), so
Batch 5 shrinks, `Cache-Control` stops being conditional, and Batch 6 loses the chart Secret
work. Missing credential is now a 401 with `WWW-Authenticate`, not a 503.

## Batch 1 — the port (no behaviour)

`catalog/port.py`:

- `Credential` — frozen slots dataclass: `token: SecretStr`, `profile: str | None`, `key: str`.
  Built by `Credential.derive(token, profile)`; `key` = SHA-256 over
  `f"{token}\x00{profile or ''}"`, first 32 hex. `__repr__` must not expose the token.
- `ModelCatalog` — `body: dict[str, object]`, `etag: str`.
- `CatalogSource` — `runtime_checkable` Protocol, `async def fetch(self, credential) -> ModelCatalog`.
- Errors: `CatalogError` base carrying the HTTP status the route maps it to —
  `CatalogRejected` (401), `CatalogBadResponse` (502), `CatalogUnavailable` (504). The route
  therefore holds no `isinstance` ladder.
- `compute_etag(body)` — SHA-256 over `json.dumps(body, sort_keys=True, separators=(",",":"))`,
  first 16 hex.

**RED:** stub satisfies `isinstance(stub, CatalogSource)` (mirrors aigateway's existing
`test_stub_satisfies_the_identity_resolver_port`); `compute_etag` stable across key ordering and
differs across bodies; distinct tokens ⇒ distinct keys, same token+profile ⇒ same key;
`repr()`/`str()` of a `Credential` contain no token substring.

## Batch 2 — the keyed cache (the substance; no I/O)

`catalog/cache.py` — `CachedCatalog(source, *, ttl_s, stale_max_s, error_backoff_s,
max_entries, upstream_concurrency, clock)`.

`clock` is an injected monotonic callable defaulting to `time.monotonic`, so tests drive time
directly — no `sleep`, no flakes.

State: an `OrderedDict[str, _Entry]` used as an LRU (`move_to_end` on hit, `popitem(last=False)`
on overflow), `_Entry` holding `catalog`, `fetched_at`, `last_error`, `last_error_at`; plus
`_inflight: dict[str, asyncio.Future]` and one `asyncio.Semaphore(upstream_concurrency)`.

`fetch(credential)` resolution order:

1. Fresh entry for `credential.key` (age ≤ `ttl_s`) → return it. **Hot path takes no lock and
   awaits nothing.**
2. An in-flight future for this key → `await` it (per-key single-flight; distinct keys never
   serialise).
3. Inside `error_backoff_s` of this key's last failure → serve stale if within `stale_max_s`,
   else raise the recorded error.
4. Register an in-flight future, acquire the semaphore, call `source.fetch(credential)`.
   Success → LRU-insert, clear the error, resolve the future. Failure → record the error; serve
   stale if within `stale_max_s`, else propagate to every waiter. Always discard the in-flight
   entry in `finally`.

Waiters receive the same exception semantics as the leader — no waiter may silently get `None`.

**RED** (counting fake source + injected clock; no HTTP):

- cold miss fetches once; hit within TTL fetches zero times; expiry refetches
- **N=20 concurrent misses on ONE key ⇒ exactly one `source.fetch`**
- **N concurrent misses on N DISTINCT keys ⇒ N fetches, not serialised** (fake records a
  max-observed-concurrency > 1)
- **two different credentials never observe each other's body** — the byok-correctness test
- upstream error + warm entry ⇒ stale served; beyond `stale_max_s` ⇒ raises
- cold-cache failure ⇒ raises and **creates no entry** (assert size == 0)
- second failing call inside `error_backoff_s` does not reach the source
- LRU: `max_entries + 1` distinct keys ⇒ oldest evicted, size capped
- bulkhead: `upstream_concurrency=2`, 10 concurrent distinct-key misses ⇒ high-water mark ≤ 2
- hot path takes no lock: concurrent hits against a source that asserts it is never called

## Batch 3 — the aigateway adapter

`catalog/aigateway.py` — `AigatewayCatalogSource(client)`; the credential arrives per call, not
at construction.

- `GET /v1/models` with `Authorization: Bearer <credential.token>` and, when
  `credential.profile` is set, `X-Profile`.
- Reuses the header/validation shape of the Runner's `_list_models`
  (`aigateway_connector.py`) — including its lesson that a transparent proxy can answer 200 with
  an HTML interstitial, so a JSON decode failure must be named, not escape as `JSONDecodeError`.
- Shape validation: `body["object"] == "list"`, `body["data"]` a list of objects each with a
  string `id`. Anything else → `CatalogBadResponse`. The body then passes through **verbatim**
  (spec §5.2) — validated, not reshaped.
- `401`/`403` → `CatalogRejected`; `httpx.TimeoutException` → `CatalogUnavailable`; other non-2xx
  and `httpx.HTTPError` → `CatalogBadResponse`.

**RED** (`httpx.MockTransport` only): happy path · non-JSON body · `{"object":"list"}` with no
`data` · `data` entries missing `id` · 401 ⇒ `CatalogRejected` · 500 ⇒ `CatalogBadResponse` ·
timeout ⇒ `CatalogUnavailable` · `Authorization` forwarded · `X-Profile` forwarded only when set ·
`caplog` assertion that no token substring is ever logged.

## Batch 4 — credential extraction + the route

**4a — extract, no behaviour change.** Move `_bearer` and `_forwarded_credential` from
`rest/routes.py` into `rest/_credentials.py`; `routes.py` imports them. The existing
`tests/unit/test_rest.py` must pass **unchanged** — that is the gate on this sub-batch, and it
ships as its own commit so the refactor is bisectable apart from the feature.

**4b — the route.** `rest/catalog.py`, own `APIRouter`, exported from `rest/__init__.py`,
included in `create_app` beside `rest_router`.

```python
@router.get("/v1/models", tags=["Catalog"], summary="List addressable models",
            responses=_MODELS_RESPONSES)
async def list_models(request, authorization=Header(None), cf_access_jwt=Header(None),
                      x_profile=Header(None), if_none_match=Header(None)) -> Response
```

- No resolvable credential → `ProblemException(401, ...)` **plus `WWW-Authenticate: Bearer`**,
  and **no upstream call**.
- `app.state.catalog is None` → `ProblemException(503, ...)` (mirrors the `_deps` job-runner
  guard).
- `CatalogError` → `ProblemException` with the status the error carries; upstream detail logged,
  never returned.
- Always sets `Vary: Authorization, Cf-Access-Jwt-Assertion, X-Profile` and
  `Cache-Control: private, max-age=<remaining, floored at 0>`.
- `If-None-Match` matching that caller's ETag → `304`, no body. Weak-comparison-safe (tolerate a
  `W/` prefix) per RFC 9110 §13.1.2, which specifies weak comparison for `If-None-Match`.

**RED** (`TestClient`, injected fake catalog): 200 + shape · **two different `Authorization`
values ⇒ different bodies** · `Cf-Access-Jwt-Assertion` wins over `Authorization` · no credential
⇒ 401 + `WWW-Authenticate`, upstream never called · `Vary` always present · `Cache-Control`
always `private` · ETag stable across a repeat · `If-None-Match` ⇒ 304 · `max-age` decreases as
the injected clock advances · `CatalogRejected` ⇒ 401 · `CatalogBadResponse` ⇒ 502 ·
`CatalogUnavailable` ⇒ 504 · unconfigured ⇒ 503 · never a 500 · route present in `app.openapi()`.

## Batch 5 — wiring, config, metrics

- `config.py`: the five cache settings of spec §8. **No credential setting** (spec D2).
- `catalog/__init__.py`: `build_catalog_service(settings) -> CachedCatalog | None` — `None` only
  when `aigateway_base_url` is unset. Mirrors `jobs/factory.build_job_runner`'s
  "unconfigured ⇒ None" contract.
- `app.py`: set `app.state.catalog`; register the client-close shutdown hook; include the router;
  accept an injectable `catalog=` parameter as `bus`/`job_runner`/`clock`/`interest` already are.
  Wire `make_local_app` identically.
- `metrics.py`: hit / miss / stale / error / bulkhead-wait counters + entry gauge.

**RED:** factory returns `None` without a base URL and a `CachedCatalog` with one; `create_app`
and `make_local_app` honour an injected catalog; the shutdown hook closes the client; counters
move; **no metric label contains a credential or cache key**; **no `Settings` field holds an
aigateway credential** (asserts spec acceptance #10 stays true).

## Batch 6 — docs

- `apps/url4-cloud/README.md` + the served OpenAPI description: document the endpoint, that a
  credential is required, that Cloudflare Access satisfies it with no client change, and that the
  answer is *per credential*.
- Helm chart values for the five cache settings. **No Secret reference needed** — r3 introduces
  no secret.

## Verification

Per batch: `uv run ruff check` · `ruff format --check` · `pyright` · `pytest --cov` (≥80, per
the SDLC card). Final: full `run_gates.py` for `url4-cloud`, plus a manual `make_local_app` smoke
against a stub aigateway exercising two distinct credentials and one credential-less request.

## Risks

| Risk | Mitigation |
|---|---|
| Extracting `_forwarded_credential` regresses `start_run` | Batch 4a is its own commit; existing `test_rest.py` must pass unchanged |
| Cache-key flooding via bogus credentials | Failures create no entry; LRU cap; fixed-length hashed keys (spec §7) |
| Upstream amplification across distinct keys | Semaphore bulkhead (spec §7); apigw is the rate limiter in front |
| Credential leaking into logs / metrics / cache keys | `SecretStr`, hashed keys, `caplog` + metric-label tests |
| Stale catalog advertises retired models | `stale_max_s` ceiling; 300s TTL |

## Out of scope

Runner refactor (spec §10) · anonymous access · any url4-cloud-held credential ·
reading `AIGATEWAY_CREDENTIAL_MODE` (spec §2.2) · pagination · any aigateway change.
