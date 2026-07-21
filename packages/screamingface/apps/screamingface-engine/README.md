# screamingface-engine — temporary package development app

This app is temporarily under `packages/screamingface/apps/` while the SDK and its URL4 engine
profile are developed together. It is not included in the `screamingface` wheel. Once ownership
and deployment responsibilities are agreed, it can move to `apps/screamingface-engine/` without
changing its HTTP contract.

## What it is

One persistent `Url4Node` hosts the ScreamingFace execution profile:

```text
GET /healthz
GET /.well-known/screamingface
GET /docs
GET /openapi.json
GET /v1?q=<complete URL4 expression>
GET /{provider}/{model}?q=(context)!intent
GET /benchmarks/gpqa/1/cases
GET /reducers/majority-vote/1
GET /graders/exact-choice/1
GET /aggregators/mean/1

GET    /v1/connections
GET    /v1/connections/{provider}
POST   /v1/connections/{provider}/oauth
PUT    /v1/connections/{provider}/api-key
DELETE /v1/connections/{provider}
```

URL4 success bodies are plaintext. The public registry is JSON serialized as plaintext. The
private connection control plane returns sanitized JSON.

`/docs` is the human-readable API reference and `/openapi.json` is its OpenAPI 3.1 source. Both
are generated from the same startup model-route snapshot as the URL4 node, so the documented
model paths match the routes this engine can execute. The reference distinguishes current HTTP
and URL4 capabilities from planned work; in particular, it does not advertise DRACO as runnable.

The engine snapshots AI Gateway's protected model catalog once at startup and builds its model
routes and registry from the same immutable data. Model handlers use one shared HTTP client to
call AI Gateway; they never spawn route subprocesses. The ScreamingFace SDK never contacts AI
Gateway directly.

## Complete benchmark runs

The client submits one URL4 expression containing:

1. a benchmark cases data route and stable slice;
2. a Model or Fusion answer graph for each selected case;
3. a grader route for the Recipe and every member; and
4. an aggregator route over the case-grade records.

`/benchmarks/gpqa/1/cases` loads the pinned GPQA Diamond source and returns NDJSON so URL4
iteration receives structured `$item` values. The reference stays inside the engine graph and is
passed only to `/graders/exact-choice/1`; model routes receive the question, never the answer key.
`/aggregators/mean/1` returns `screamingface.report.v1` as plaintext JSON.

The registry advertises the benchmark manifest, cases/grader/aggregator routes, supported result
schemas, and encoded request-target limit. `sf.benchmarks.load("gpqa@1")` loads this manifest; it
does not fetch cases.

GPQA may require accepting its Hugging Face terms. In local development, supply the dataset token
to the engine container:

```bash
export HF_TOKEN=hf_...
./dev.sh restart
```

This token is separate from `sf.connect("huggingface")`, which configures Hugging Face as an AI
Gateway inference provider. No synthetic or mock dataset fallback exists.

DRACO is not advertised yet. Its remaining work is registering and verifying the production cases,
grader protocol, routes, tool policy, and model configuration. A complete study runs one URL4
benchmark transaction per candidate and compares the resulting reports client-side; it does not
depend on a generic all-settled multi-root primitive.

## Models, reducers, and tools

The majority-vote handler accepts a resolved JSON object with contiguous `member_1` through
`member_n` string values in the URL4 intent, applies exact-string voting, and breaks ties by member
position. It never contacts AI Gateway.

The engine advertises `web_search` and `web_fetch` only on the verified pinned Hugging Face
DeepSeek V4 Pro/DeepInfra and GLM 5.2/DeepInfra routes. Tool-enabled requests carry a colon-separated
URL4 scalar (`tools=web_search:web_fetch`), a positive `max_tool_rounds`, and explicit Tavily policy.
Every model turn goes through AI Gateway; Tavily calls go directly from the engine.

Tavily API keys are validated directly and retained only in process memory. They never enter AI
Gateway, URL4, model messages, responses, or logs. This is appropriate only for a researcher-owned
local engine. A shared deployment needs HTTPS, identity, authorization, and encrypted per-user
storage.

## Provider connections

The registry exposes supported provider ownership and authentication methods. These declarations
are currently explicit engine policy and should later be sourced from an AI Gateway provider
discovery endpoint. Model availability itself is already derived from AI Gateway at startup.
The local profile enables AI Gateway's API-key-only OpenRouter plugin; its advertised models are
therefore reflected from `GET /v1/models` rather than duplicated in this engine.

ScreamingFace owns the Gateway connection labeled `default` and selects it with
`X-Profile: default`. API keys and OAuth actions travel through the engine control plane; secrets
are never returned in public responses.

Use the SDK:

```python
import screamingface as sf

sf.connect()
sf.connections.list()
sf.connect("gemini", api_key="...")
sf.connect("openrouter", api_key="sk-or-...")
sf.connect("tavily", api_key="tvly-...")
sf.disconnect("gemini")
```

## Limits and errors

The registry's `limits.max_request_target_bytes` is the encoded request target, not decoded URL4
length. It defaults to 61,440 bytes, leaving headroom below HTTPX's 64 KiB absolute-URL limit. The
ASGI wrapper returns HTTP 414 before evaluation if the target is too large; the SDK preflights the
same limit before spend.

AI Gateway and tool failures are mapped to stable, sanitized engine errors. Credentials, raw
provider payloads, tool arguments, and tool result content are not included in diagnostics.

## Run the local stack

```bash
./dev.sh          # build/start detached and wait for health
./dev.sh restart  # recreate while preserving AI Gateway credentials
./dev.sh status
./dev.sh logs
./dev.sh down
```

The stack contains the ScreamingFace engine and AI Gateway. Tavily remains an external service.
AI Gateway data lives on the named `aigateway-data` volume; the commands above preserve it.
`docker compose down -v` is the explicit destructive credential reset.

Default host endpoints:

```text
ScreamingFace engine  http://127.0.0.1:4404
API reference         http://127.0.0.1:4404/docs
AI Gateway            http://127.0.0.1:9105
```

Verify:

```bash
curl -s http://127.0.0.1:4404/healthz
curl -s http://127.0.0.1:4404/.well-known/screamingface | python -m json.tool
curl -s http://127.0.0.1:4404/openapi.json | python -m json.tool
```

## Native development and validation

```bash
uv sync
uv run screamingface-engine

cd ../..
uv run ruff check
uv run ruff format --check
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
```
