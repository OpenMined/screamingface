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
GET /{public-provider}/{model}?[params&]q=(context)!intent
GET /reducers/majority-vote?q=(resolved-member-object)
GET /v1?q=<complete URL4 expression>
GET /v1/connections
GET /v1/connections/{provider}
POST /v1/connections/{provider}/oauth
PUT /v1/connections/{provider}/api-key
DELETE /v1/connections/{provider}
```

URL4 and model success bodies remain plaintext. The registry is JSON text, while the separate
private connection control plane returns sanitized JSON. Model routes return only the first AI
Gateway assistant message text. At startup, the engine reads AI Gateway's protected
`GET /v1/models` catalog once, derives public routes for supported providers, and builds the URL4
node and public registry from the same immutable snapshot. There is no static availability
fallback or per-request catalog lookup. The SDK never contacts AI Gateway directly.

The application is one persistent `Url4Node` process. Its model handlers call AI Gateway
in-process through one shared asynchronous HTTP client; they do not launch route subprocesses or
another engine. The thin ASGI wrapper owns client lifecycle, global admission control, a
whole-evaluation timeout, the advertised encoded request-target limit, and the application-owned
connection control plane. All other request dispatch remains owned by `Url4Node`.

## Provider connections

The public registry advertises `codex`, `gemini`, `anthropic`, and `huggingface` capabilities and
explicitly maps every discovered model owned by those supported Gateway providers to one public
provider. Gateway order is preserved. Adding or removing one of those providers' models takes
effect on engine restart without a ScreamingFace availability edit. Models owned by providers
without a ScreamingFace connection contract remain hidden. Private AI Gateway provider names,
connection UUIDs, credential locators, claims, and tokens never appear in registry or connection
responses.

Provider display names and supported authentication methods are temporarily explicit
ScreamingFace policy. They are expected soon to come from a protected AI Gateway provider
discovery endpoint, read and validated with the model catalog at engine startup. Until that
contract exists, the engine does not infer authentication methods from model IDs.

ScreamingFace still owns its public aliases and request IDs. For example,
`claude-sonnet-4-6` becomes public `claude/sonnet-4.6` and is sent to chat completion as
`anthropic/claude-sonnet-4-6`; `gemini-cli/gemini-2.5-flash` becomes public
`gemini/2.5-flash`; Codex IDs are already public and pass through unchanged. A pinned Hugging Face
ID such as `huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra` is exposed as the URL4-safe public
ID `huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra`, while the exact colon-pinned ID is retained
for AI Gateway calls. A malformed supported provider record, an unpinned Hugging Face model, a
duplicate public alias, an unavailable catalog, or a catalog containing no supported models
prevents startup rather than exposing a stale or partial service.

Use the SDK-facing engine API:

```python
import screamingface as sf

sf.connections.list()
flow = sf.connect("codex")
print(flow.authorize_url)
connection = flow.wait()

sf.connect("gemini", api_key="...")
sf.disconnect("gemini")

sf.connect("huggingface", api_key="hf_...")
```

ScreamingFace owns exactly the AI Gateway connection whose private label is `default`, and model
calls select it using `X-Profile: default`. Other Gateway connections are ignored. API keys travel
once in the engine request body and once in the internal Gateway request body; neither service
echoes them. AI Gateway remains the only credential store.

OAuth providers require their registered callback paths, so the browser returns to the engine at
`/auth/callback` (Codex), `/oauth2callback` (Gemini), or `/callback` (Anthropic). Gemini OAuth is
temporarily not advertised while AI Gateway's Code Assist onboarding/readiness flow is incomplete;
Gemini API-key connections remain available. The engine relays
only `code` and `state` over its loopback Gateway connection and returns its own generic HTML page.
The SDK never handles callback codes or provider tokens.

The Compose profile also configures an internal SearXNG service. The explicit capability overlay
currently adds `web_search` to `claude/sonnet-4.6`; all other dynamically discovered routes remain
tool-free. A capable model may call the engine's
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
`web_search`; with it, the compatible Claude route does. The tool-free `gemini/2.5-flash` route
maps to AI Gateway's registered `gemini-cli/gemini-2.5-flash` model and is the bounded judge used
by the explicitly non-comparable `draco-preview@1` SDK profile. Gemini research is not advertised
because Gemini 3 function-calling continuations require the
provider's encrypted `thoughtSignature`, which the current Gateway normalization drops. The
engine must not claim a named capability that fails after its first tool call. The provisional
`gemini/3.1-pro-preview` route is deliberately absent: canonical `draco@1` retains that pinned
judge requirement and therefore fails SDK preflight until AI Gateway officially registers it.
The engine never advertises an assumed model, bypasses Gateway, or substitutes another judge.

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
./dev.sh          # build, start detached, and wait until every service is healthy
./dev.sh restart  # recreate this stack without deleting provider credentials
./dev.sh status   # show Compose service health
./dev.sh logs     # follow recent logs; Ctrl-C leaves the services running
./dev.sh down     # stop this stack without deleting provider credentials
```

`./dev.sh start` is the explicit form of the default command. Startup waits up to three minutes
for AI Gateway, SearXNG, and the ScreamingFace engine health checks. Because services start
detached, closing the invoking terminal or interrupting `./dev.sh logs` does not stop them. An
unknown command fails before Docker with the supported-command list.

If another local stack owns the default host ports, select isolated host ports while preserving
the containers' internal topology:

```bash
AIGATEWAY_HOST_PORT=19105 \
SCREAMINGFACE_ENGINE_HOST_PORT=14404 \
CODEX_OAUTH_HOST_PORT=1457 \
./dev.sh
```

Codex OAuth uses the provider-registered loopback ports `1455` or `1457`; use `1457` only when
`1455` is occupied. Other provider callbacks continue to use `SCREAMINGFACE_ENGINE_HOST_PORT`.

This builds the engine, AI Gateway, and internal SearXNG containers. SearXNG has no host port and
requires no researcher API key. It still uses public upstream search engines, so research requests
need outbound network access. SDK-local benchmark loading does not contact any of these services;
model routes do.

AI Gateway starts with an empty provider connection store. Its SQLite database, encrypted
credential blobs, generated local master key, and generated JWT secret live on the named
`aigateway-data` volume. Ordinary `./dev.sh`, `./dev.sh restart`, and `./dev.sh down` preserve the
volume; `docker compose down -v` is the explicit destructive credential reset and is deliberately
not exposed by `dev.sh`. Until a provider is
connected through the engine, model routes return the ordinary provider-access failure while
health, registry, connection status, compilation, and deterministic reducer routes remain usable.

The engine and AI Gateway remain separate processes and containers, but share one Docker network
namespace in this local profile. The engine therefore calls AI Gateway at `127.0.0.1:9105`, which
satisfies AI Gateway's deliberately loopback-only policy when authentication is disabled. The AI
Gateway service owns both published host ports because Docker requires published ports to belong
to the container whose network namespace is shared. This is development topology only; a hosted
deployment should enable authentication rather than rely on this arrangement.

`AIGATEWAY_PUBLIC_URL` points to the engine's browser-visible localhost origin so AI Gateway builds
Gemini and Anthropic authorize URLs with the engine callback paths. Codex is the deliberate
exception: the engine requests
`SCREAMINGFACE_CODEX_OAUTH_REDIRECT_URI=http://localhost:1455/auth/callback`, and Compose publishes
that host port to the same engine listener. The browser therefore still returns to the
ScreamingFace engine; the SDK never contacts AI Gateway directly. Callback credentials are relayed
to AI Gateway in a JSON body, and raw engine access logging is disabled so OAuth codes, state
values, and URL4 query expressions do not appear in request-target logs.

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
