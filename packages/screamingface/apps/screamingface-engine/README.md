# screamingface-engine — temporary package development app

This application is **temporarily located under `packages/screamingface/apps/`** so the
ScreamingFace SDK and its URL4 engine profile can be developed and tested together under the
existing `screamingface` package workstream.

It is not part of the `screamingface` Python wheel and this path is not the intended production
deployment boundary. Once application ownership, CI, and release responsibilities are approved,
promote it without changing its HTTP contract to:

```text
apps/screamingface-engine/
```

## Implemented responsibilities

This tracked development profile composes the generic `Url4Node` with ScreamingFace-owned
executable capabilities:

```text
GET /healthz
GET /.well-known/screamingface
GET /codex/gpt-5.5?[params&]q=(context)!intent
GET /gemini/2.5?[params&]q=(context)!intent
GET /claude/sonnet-4.6?[params&]q=(context)!intent
GET /gemini/3.1-pro-preview?[params&]q=(context)!intent
GET /reducers/majority-vote?q=(resolved-member-object)
GET /v1?q=<complete URL4 expression>
```

All successful bodies are plaintext. The registry body contains JSON text. Model routes return
only the first AI Gateway assistant message text. The SDK parses and validates structured
plaintext on the client.

The application is one persistent `Url4Node` process. Its model handlers call AI Gateway
in-process through one shared asynchronous HTTP client; they do not launch route subprocesses or
another engine. The thin ASGI wrapper owns only client lifecycle, global admission control, a
whole-evaluation timeout, and the advertised encoded request-target limit.

The Compose profile also configures an internal SearXNG service. Gemini and Claude then advertise
the named `web_search` capability; Codex remains tool-free. A capable model may call the engine's
standard `web_search` and `web_fetch` functions multiple times within a bounded loop. SearXNG
returns candidate titles, URLs, and snippets; the engine can read bounded public HTML/plaintext
pages after rejecting credentials, non-HTTP(S) URLs, private/non-global targets, unsafe redirects,
oversized responses, unsupported media, and known DRACO-contaminating sources. Every assistant
turn still uses AI Gateway's existing `POST /v1/chat/completions` contract, and the URL4 endpoint
returns only the final assistant plaintext.

The majority-vote handler is also registered once in that process. It accepts a resolved JSON
object with contiguous `member_1` through `member_n` string values, applies exact-string voting, and
breaks ties by numeric member position. It returns only the winning text and never contacts AI
Gateway. Nonempty intent, parameters, missing members, non-string values, and blank answers are
permanent URL4 `malformed_source` errors.

Registry claims are configuration-dependent: without `SCREAMINGFACE_SEARXNG_URL`, no route claims
`web_search`; with it, only the compatible Gemini and Claude routes do. The tool-free
`gemini/3.1-pro-preview` route maps to
`gemini-cli/gemini-3.1-pro-preview` for DRACO rubric judging. This development contract assumes
the AI Gateway owner will register that model identifier. If the Gateway deployment has not done
so, the URL4 route remains addressable but returns the ordinary safe `502 resolution_failed`
upstream error; the engine never bypasses Gateway or substitutes another judge.

The registry also advertises `limits.max_request_target_bytes`. It defaults to 61440 bytes and
is configurable with `SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES`. This is the exact encoded
HTTP request target—path, `?`, and query string—not the decoded URL4 expression length. The ASGI
wrapper returns HTTP 414 with `request_target_too_large` before URL4 evaluation when the limit is
exceeded. The maximum is deliberately 60 KiB: `httpx` limits absolute URLs to 64 KiB, leaving
roughly 4 KiB for the configured HTTP(S) origin. Uvicorn/h11 receives 128 KiB for parser and header
headroom; the SDK still preflights the stricter advertised value before model or judge spend.

## Benchmark boundary

The engine does not publish benchmark manifests, cases, answer keys, graders, or aggregators.
Those are local SDK concerns. For example, `sf.benchmarks.load("gpqa@1")` loads the pinned
Hugging Face source through the researcher's own process and credentials, then engine requests
contain only the concrete case prompt needed for model execution.

GPQA may require accepting its dataset terms and authenticating before loading it:

```bash
huggingface-cli login
```

No Hugging Face token is forwarded to either container. No synthetic or mock dataset fallback
exists.

## Run the local stack

From this directory:

```bash
./dev.sh
```

If another local stack owns the default host ports, select isolated host ports while preserving
the containers' internal topology:

```bash
AIGATEWAY_HOST_PORT=19105 SCREAMINGFACE_ENGINE_HOST_PORT=14404 ./dev.sh
```

This builds the engine, AI Gateway, and internal SearXNG containers. SearXNG has no host port and
requires no researcher API key. It still uses public upstream search engines, so research requests
need outbound network access. SDK-local benchmark loading does not contact any of these services;
model routes do.

AI Gateway starts with an empty, ephemeral provider profile store in this development profile.
ScreamingFace does not inject provider credentials or implement a parallel authentication path.
Until credentials are provisioned through AI Gateway, model routes therefore return the ordinary
provider-access failure (currently HTTP 401 from Gateway, safely surfaced as a URL4 502), while
health, registry, compilation, and deterministic reducer routes remain usable.

The engine and AI Gateway remain separate processes and containers, but share one Docker network
namespace in this local profile. The engine therefore calls AI Gateway at `127.0.0.1:9105`, which
satisfies AI Gateway's deliberately loopback-only policy when authentication is disabled. The AI
Gateway service owns both published host ports because Docker requires published ports to belong
to the container whose network namespace is shared. This is development topology only; a hosted
deployment should enable authentication rather than rely on this arrangement.

Verify:

```bash
curl -s http://127.0.0.1:4404/healthz
curl -s http://127.0.0.1:4404/.well-known/screamingface | python -m json.tool

curl -G http://127.0.0.1:4404/codex/gpt-5.5 \
  --data-urlencode "q=(What is 2 + 2?)!Answer briefly"

cd ../..
uv run python apps/screamingface-engine/scripts/smoke_phase2b.py
uv run python apps/screamingface-engine/scripts/smoke_phase2c.py
```

Neither smoke uses a mocked runtime component. Set `SCREAMINGFACE_ENGINE_URL` when the stack uses
an overridden host port. Phase 2B sends a literal reducer expression. Phase 2C constructs the
public SDK values, compiles the canonical recipe and concrete case expression, then invokes
`Fusion.run()`. It accepts either a validated provider-backed result or the engine's propagated
credential-free AI Gateway failure, proving the container topology without claiming an authorized
provider call.

Stop the stack:

```bash
docker compose down
```

## Native development

```bash
uv sync
uv run screamingface-engine
```

## Validation

The app is currently covered by the parent ScreamingFace package gates. From this directory:

```bash
cd ../..
uv run ruff check src tests apps/screamingface-engine/src apps/screamingface-engine/tests
uv run ruff format --check src tests apps/screamingface-engine/src apps/screamingface-engine/tests
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/screamingface-engine/src uv run pytest apps/screamingface-engine/tests \
  --cov=screamingface_engine --cov-fail-under=95 -q
```
