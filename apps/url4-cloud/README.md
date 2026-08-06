# url4-cloud

REST + WebSocket url4 execution runner (k8s Jobs + NATS). Design: `docs/spec/2026-07-21-url4-cloud.md`
· epic OME-513.

One app, one image, two modes — `apps/url4-cloud/`, package `url4_cloud`, image
`ghcr.io/openmined/screamingface-url4-cloud`. The mode is chosen by **argv**, never sniffed from
the environment:

- **`url4-cloud serve`** — the stateless control-plane App (REST + WebSocket). The **default** when
  no subcommand is given, which is what keeps the image's `CMD ["url4-cloud"]` and the chart's
  Deployment command working.
- **`url4-cloud run`** — the one-shot Job mode (`url4_cloud/runner/`) that executes one url4
  expression, publishes telemetry to NATS and exits. `K8sJobRunner` schedules the App's **own**
  image with `command: ["url4-cloud", "run"]`.
- **`url4-cloud serve --local`** — both halves fused in one process, for development. Runs execute
  as `asyncio` tasks (`InProcessJobRunner`) and frames travel an in-memory log
  (`InMemoryEventStream`) instead of JetStream, so neither Kubernetes nor NATS is needed.
  **Only the two adapters change** — the 428 subscriber gate, sequencing, replay-from and the
  model catalog are the production code path, and auth is the same code with one deliberate
  exception: the prod boot REFUSES the insecure default JWT secret (`_require_prod_secret`),
  while local warns and starts anyway (`_warn_if_insecure`) so a dev server needs no setup.
  Token minting and verification are otherwise identical. See [Local mode](#local-mode).

**WHY one artifact rather than two.** The two halves already shared their whole wire vocabulary —
the Job env contract, the NATS subject naming, the JetStream binding — so the split's real cost was
three hand-synced duplicate modules plus contract tests whose only job was catching the copies
drift. The run mode's dependencies (httpx, nats-py, url4) were already a strict subset of the
serving mode's, so merging cost **zero** new dependencies; a Job now carries some serving-side
packages it never imports, which is the whole price paid.

The concepts both modes meet at — the CloudEvents + OTel wire protocol and the abstract classes
built on it — live in **`url4.streaming`** (`packages/url4`), alongside the url4 engine. Nothing
concrete lives there.

### Where code goes

`url4.streaming` holds concepts; the two modes hold implementations. Concretely:

| | lives in | examples |
|---|---|---|
| the wire protocol | `url4.streaming.protocol` | the CloudEvents frame models |
| abstract classes | `url4.streaming` | `EventPublisher`/`EventConsumer`, `Executor`, `JobRunner` |
| pure logic over them | `url4.streaming` | the run lifecycle, the frame codec, `job_name`, `parse_traceparent` |
| every implementation | the half that runs it | `K8sJobRunner`, the model catalog (serve) · `Url4Executor`, the aigateway connector (run) · the JetStream adapter (a shared leaf) |

The rule that decides it: **if it names a broker, a scheduler or a framework, it is not a concept** —
it belongs to whichever half runs it. `url4.streaming` therefore has no NATS client, no
FastAPI and no kubernetes client, and it imports nothing from the engine it ships beside.

One caveat that used to be a guarantee: because the contract ships inside the `url4` distribution,
the App's dependency closure contains the engine. `.claude/scripts/check_layering.py` still fails
the build if the two halves import each other, but it no longer proves the App is engine-free —
that property was given up when the contract moved here, and nothing enforces it.

> **INVARIANT — the import graph is the boundary now.** Two distributions used to prove the split
> structurally: a cross-import could not even be installed. One distribution, one venv and one
> image prove nothing, so `.claude/scripts/check_layering.py` proves it instead, as an
> intra-package rule with the same doctrine. `url4_cloud.runner.*` must not import the control
> plane (`app`, `rest`, `ws`, `auth`, `catalog`, `config`, `metrics`, `ops`, `schemas`,
> `adapters.k8s`, `adapters.factory`), and the control plane must not import `url4_cloud.runner.*`.
> They share exactly three leaves: **`job_env`, `subjects`, `adapters.jetstream`**. `cli.py` is
> exempt — dispatching to both is its entire job, and it imports each lazily inside the branch that
> runs it.
>
> What that buys, verified empirically: importing `url4_cloud.runner.main` loads **none** of
> fastapi, uvicorn, starlette, kubernetes, jwt or prometheus_client. A Job's cold start stays the
> engine plus httpx plus nats-py — the cost the separate slim image used to buy structurally.

In a **deployed** App the serving half is the control plane and executes nothing: it mints tokens,
bridges streams and schedules Jobs. Evaluating a url4 expression happens in a Job running the same
image in `run` mode.

`serve --local` is the single, declared exception, and `url4_cloud/local.py` is the only module
that crosses the line — it is named in **both** `CONTROL_PLANE` and `_EXEMPT` in
`.claude/scripts/check_layering.py`, so being exempt is a visible decision rather than a module
that quietly evaded the rule. It imports the run mode lazily, inside `create_local_app`, so an
ordinary `serve` never reaches it; `tests/unit/test_local_app.py` pins that the edge points one
way only.

The App reads production runs over JetStream through its own `JetStreamConsumer`, never the run
mode's `JetStreamPublisher` — both live in `url4_cloud/adapters/jetstream.py` as a shared leaf, and
the gate rejects any import across the line in either direction.

## Dev

```sh
uv sync
uv run pytest
uv run url4-cloud   # serve on :9108 (`serve` is the default subcommand)
```

## Local mode

```sh
uv run url4-cloud serve --local     # loopback only, :9108
```

Local mode expects aigateway to run with authentication **disabled** (`AIGW_AUTH_MODE=disabled`),
where every caller is anonymous. Nothing needs a token: url4-cloud carries no aigateway credential
in either mode.

No Kubernetes, no NATS: `InProcessJobRunner` spawns each run as an `asyncio` task and
`InMemoryEventStream` carries its frames, with real sequence numbers, replay-from and purge.
`tests/integration/test_local_spine.py` drives the whole protocol through it.

What differs from a deployed App — and nothing else does:

| Concern | Deployed | `--local` |
| --- | --- | --- |
| Run substrate | `K8sJobRunner` (one batch/v1 Job per run) | `InProcessJobRunner` (one `asyncio.Task`) |
| Event stream | JetStream | `InMemoryEventStream` |
| Caller identity | the verified `X-User-Email` Envoy injects | none — aigateway is anonymous |
| Admission | the cluster queues surplus Jobs | `local_max_concurrent_runs`, else `503` + `Retry-After` |
| JWT secret | `_require_prod_secret` refuses the dev default | dev default allowed, so the bind is loopback-only |

Runs still require an attached WebSocket subscriber first — the `428` gate is protocol discipline
and local mode keeps it rather than relaxing it for `curl`.

The declared world (`url4.toml`) is baked into the image at `/etc/url4/url4.toml` and is **not**
installed by the wheel, so in a checkout local mode falls back to the checkout's `url4.toml`. Set
`URL4_RUNNER_CONFIG` to override. Tuning: `URL4_CLOUD_LOCAL_MAX_CONCURRENT_RUNS`,
`URL4_CLOUD_LOCAL_STREAM_MAX_FRAMES`, `URL4_CLOUD_LOCAL_MAX_RUN_HISTORY`.

## Model catalog — `GET /v1/models`

Discover which models an expression can address, proxied from aigateway's own `/v1/models` and
served from a per-caller cache. Design: `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md`
· OME-625.

The caller is the verified `X-User-Email` the mesh gateway injects. Deployed, Envoy always supplies
it. Locally, aigateway runs with auth disabled and none is needed:

```sh
curl http://localhost:9108/v1/models
```

url4-cloud verifies nothing and **stores no aigateway credential of its own** — it forwards the
caller's identity and aigateway decides, including whether an absent identity is acceptable. Consequences worth knowing:

- **The answer is per credential.** Two callers can legitimately get different catalogs, which is
  what keeps this correct under either aigateway credential mode (`byok` / `shared`). Responses are
  therefore `Cache-Control: private` and carry `Vary`.
- **Caching is per credential too** — 5 min TTL, single-flight per key, and a stale entry is served
  if a refresh fails (bounded to 1 h) rather than failing open into "no models".
- **Enabled by `URL4_CLOUD_AIGATEWAY_BASE_URL`** — the same value the chart already sets as
  `config.aigatewayBaseUrl`. Unset ⇒ the endpoint answers `503`; everything else is a code default
  (see the `models_cache_*` fields in `config.py`).
- Cache behaviour is observable at `/metrics` (`url4_cloud_catalog_*`).

## Per-run cache policy

A different cache from the one above: aigateway's **response** cache, which answers an identical
model call from a stored corpus instead of dispatching it to the provider again. Design:
`docs/spec/2026-08-05-url4-cache-policy-spec.md`.

**Caching is ON by default.** Only declining is explicit — the gateway participates unless told
not to, so a switch that "turns caching off" is the only switch there is. Two carriers, one
meaning, scoped to the **whole run** (every leaf, every fan-out branch — per-node intent would
need url4 grammar and is out of scope):

```sh
# HTTP — the standard RFC 9111 request field on GET /
curl -H 'URL4-Capability: <jwt>' -H 'Cache-Control: no-store' 'http://localhost:9108/?q=...'
```

```json
{"type": "ai.url4.attach", "data": {"from_sequence": 1, "cache": {"participate": false}}}
```

| directive | effect |
| --- | --- |
| *(absent)* | participate — the default |
| `no-store`, `no-cache` | do not participate |
| `max-age=<seconds>` | participate under a freshness bound (see **Known-inert** below) |
| `url4-use-cache` | participate, explicitly — the token that lets the header override a frame opt-out |

Conflicting directives resolve to **not** participating: the worst case of declining is a missed
hit, while the worst case of participating against a caller who refused is a shared answer they
explicitly declined. Unknown and malformed directives are **ignored, never 4xx** — a cache
directive is a hint about cost, not a term of the request.

**Precedence: the header wins**, and the overridden declaration is announced as a `warn`
`ai.url4.log` on the stream. **First attach wins** on the frame side: a re-attach with a different
policy leaves the run's policy alone (calls may already have run under it) and warns.

> **INVARIANT — url4 never sends a cache control key other than `use-cache`.** aigateway's cache
> grammar is CLOSED to that one field, and any other key inside the request body's `cache` object
> makes the whole request **bypass** the cache — silently, with nothing raised anywhere, even
> alongside a valid `use-cache: true`. So every directive above collapses to participate/opt-out
> at url4's own edge (`rest/cache_header.py` → intent, `runner/cache.py` → the wire), and a run
> that participates sends **no `cache` field at all**. `tests/unit/test_runner_cache_body_field.py`
> pins it as a property over every input.

**Observability.** Each span carries `cache_status` (`hit`/`miss`/`bypass`) and `cache_reason` —
the gateway's vocabulary verbatim, so `opted_out` stays distinct from `unsupported_control`. The
run publishes one summary `ai.url4.log` with its hit, miss and **bypass-by-reason** totals
(`runner/cache_counters.py`). Not Prometheus: a run is a one-shot Job with no scrape endpoint, and
the layering gate keeps `url4_cloud.runner.*` out of `url4_cloud.metrics` anyway. **No counter is
labelled by cache key, prompt or credential** — the gateway's entry key is parsed and stops at
`runner/cache_readback.py`.

**Known-inert: `max-age`.** The bound is parsed and preserved end to end, but the gateway today
neither accepts a freshness bound nor reports an entry's `Age`, so a bounded run cannot prove a
hit fresh and declines instead — observably, as `bypass` / `opted_out`. The honouring path is
written and dormant; when either upstream half lands, the change is a branch, not a redesign.
