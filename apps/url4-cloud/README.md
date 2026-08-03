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
# Prepare the pinned DRACO dataset once. The runtime never downloads benchmark data.
uv run --with datasets python -m url4_cloud.benchmarks.draco.prepare \
  --out /tmp/screamingface-benchmark-assets/draco

# Point the local Runner world at the prepared benchmark root.
URL4_BENCHMARK_ASSETS=/tmp/screamingface-benchmark-assets \
  uv run url4-cloud serve --local   # loopback only, :9108
```

Local mode expects aigateway to run with authentication **disabled** (`AIGW_AUTH_MODE=disabled`),
where every caller is anonymous. Nothing needs a token: url4-cloud carries no aigateway credential
in either mode.

`/opt/benchmarks` is the benchmark image's container path; it normally does not exist when running
directly from a host checkout. `URL4_BENCHMARK_ASSETS` must name a root containing one directory
per installed Benchmark, such as `draco/cases.json`. If `/tmp` is cleared, run the preparation
command again. Preparation is deliberately separate from startup so a run cannot silently
download a different dataset revision.

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

Each registered Benchmark installs the deterministic routes referenced by its expression directly
into every Runner world. Those routes are private and revision-qualified—for example,
`/benchmarks/draco/<revision>/tasks`—so Benchmarks cannot collide and an old saved URL4 cannot
silently execute against a newer protocol. DRACO's task preparation, verdict binding, and
Aggregation are in-process Python functions; Candidate and Judge calls remain explicit nodes in
the shareable URL4. Private assets load lazily from the Benchmark image, and the large cross-Case
row collection stays in URL4 context rather than subprocess argv.

## Benchmark Runner images

The base URL4 image intentionally contains no Benchmark datasets or private grading assets. A
deployed Engine that publishes Benchmarks must run evaluation Jobs with the layered Benchmark
image built by `Dockerfile.benchmark`. The control-plane Deployment can continue using the base
image.

From the repository root, build the matched pair with the same immutable version tag:

```sh
VERSION=0.1.0

docker build \
  -f apps/url4-cloud/Dockerfile \
  -t ghcr.io/openmined/screamingface-url4-cloud:${VERSION} \
  .

docker build \
  -f apps/url4-cloud/Dockerfile.benchmark \
  --build-arg BASE=ghcr.io/openmined/screamingface-url4-cloud:${VERSION} \
  -t ghcr.io/openmined/screamingface-url4-cloud-benchmark:${VERSION} \
  .
```

`Dockerfile.benchmark` downloads DRACO's pinned dataset during the build, prepares its runtime
files under `/opt/benchmarks/draco`, discards the build-only dataset tooling, and sets
`URL4_BENCHMARK_ASSETS=/opt/benchmarks` in the runtime image. The resulting image must be published
where the cluster can pull it. Adding a Benchmark means adding its definition to the registry and
its deterministic preparation command to this image.

Select that image for Runner Jobs while leaving the control plane on the base image:

```yaml
runner:
  image:
    repository: ghcr.io/openmined/screamingface-url4-cloud-benchmark
    # Omit tag to inherit the App image's resolved tag, or set the same immutable version.
```

Deploying Runner Jobs with only the base image will make Benchmark discovery succeed but
execution fail with `benchmark_unavailable`, because definitions are installed but their cases
and private grading assets are absent. Building, publishing, and selecting the Benchmark image
belongs to the deployment pipeline; SDK users do not prepare production assets themselves. See
[`deploy/helm/README.md`](deploy/helm/README.md) for the complete chart configuration.

## Model catalog — `GET /v1/models`

Discover which models an expression can address, proxied from aigateway's own `/v1/models` and
served from a per-caller cache. Design: `docs/spec/2026-07-26-url4-cloud-model-catalog-spec.md`
· OME-625.

The Engine enriches the catalog with `default_synthesizer`, a concrete model ID configured by
`URL4_CLOUD_DEFAULT_SYNTHESIZER` (default: `anthropic/claude-haiku-4-5`). Clients use it only when
a Fusion omits its synthesizer; the resulting URL4 still contains the concrete model route and is
therefore portable without consulting the catalog again.

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
  `config.aigatewayBaseUrl`. An ordinary deployed App answers `503` when it is unset. Local mode
  automatically uses `http://127.0.0.1:9105`, matching its bundled runner config; an explicit
  value still overrides that default. Everything else is a code default (see the
  `models_cache_*` fields in `config.py`).
- Cache behaviour is observable at `/metrics` (`url4_cloud_catalog_*`).

## Provider connections — `/v1/connections`

The SF Client connects provider credentials through this control-plane surface:

```text
GET    /v1/connections
PUT    /v1/connections/{provider}
POST   /v1/connections/{provider}/oauth
DELETE /v1/connections/{provider}
```

The catalogue is derived from AI Gateway's enabled provider plugins and advertises each provider's
supported authentication methods. `PUT` accepts `{"api_key": "..."}` for any provider that
supports API-key authentication and asks AI Gateway to validate and store it; the App never
persists or echoes the key. `POST .../oauth` starts OAuth only when the selected provider advertises
that method and returns a sanitized authorization URL and lifetime. Provider-specific OAuth URLs,
callback paths, scopes, and token exchange remain owned by AI Gateway. One OpenRouter key
authorizes every enabled `openrouter/...` model
route, but does not authorize direct routes owned by other providers. `GET` and mutation responses
contain only the public provider name, supported methods, status, auth method, and optional account
label. AI Gateway account IDs, credential locators, and upstream error bodies never cross this
boundary.

As with model discovery, the App forwards only the verified `X-User-Email` identity. Local mode
uses AI Gateway's anonymous account when authentication is disabled and automatically addresses
it at `http://127.0.0.1:9105`. An ordinary deployed App returns `503` when
`URL4_CLOUD_AIGATEWAY_BASE_URL` is unset.

For hosted provider OAuth, `AIGATEWAY_PUBLIC_URL` must identify AI Gateway's browser-reachable
callback origin and the provider must allow that callback. Local plugins use their registered
loopback callback behavior. The Python Client still calls only URL4 Cloud; the user's browser is
redirected between the provider and AI Gateway to complete OAuth.

## Benchmark catalog — `GET /v1/benchmarks`

Discover the Benchmarks published by this Engine. The response follows the same list
envelope as `GET /v1/models`:

```json
{
  "object": "list",
  "default": "draco",
  "data": [
    {
      "id": "draco",
      "object": "benchmark",
      "title": "DRACO",
      "description": "The 100-task DRACO deep-research benchmark.",
      "href": "/v1/benchmarks/draco"
    }
  ]
}
```

`GET /v1/benchmarks/{id}` returns one minimal executable resource containing its stable id,
immutable protocol revision, selected and total Case counts, required fixed models, and the
Candidate-independent URL4 expression. Human-facing title and description live only in the
catalog above. `limit=N` selects the first `N`
Cases while building that resource; it does not name a separate Lite Benchmark. The Client fetches
the resource once, links each Candidate into its `/candidate` boundary, and sends each resulting
complete URL4 directly to the Engine for execution. Reports retain the revision so results remain
attributable after the stable public name points to a newer snapshot.

The installed DRACO adapter uses the complete 100-task dataset and five independent Judge passes
per criterion. Its fixed Judge is `openrouter/google/gemini-3.1-pro-preview`: the paper's exact
`Gemini-3-Pro Preview` was shut down on 2026-03-09, and Google designated Gemini 3.1 Pro Preview
as its replacement. Runs are therefore protocol-aligned but must disclose that Judge version
difference rather than claiming bit-for-bit reproduction of the paper's scores.

Candidate results expose one canonical, higher-is-better `score`. Benchmark-specific values such
as DRACO's coverage, pass rate, Judge spread, and verdict counts are diagnostics under `metrics`;
the primary score is not duplicated there.
