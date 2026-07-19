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

This tracked development profile composes the generic `Url4Node` with ScreamingFace-owned data:

```text
GET /healthz
GET /.well-known/screamingface
GET /benchmarks/gpqa@1
GET /benchmarks/gpqa@1/cases
GET /benchmarks/draco@1
GET /benchmarks/draco@1/cases
GET /codex/gpt-5.5?[params&]q=(context)!intent
GET /gemini/2.5?[params&]q=(context)!intent
GET /claude/sonnet-4.6?[params&]q=(context)!intent
GET /reducers/majority-vote?q=(resolved-panel-object)
GET /v1?q=<complete URL4 expression>
```

All successful bodies are plaintext. Registry and manifest bodies contain JSON text; case routes
contain normalized NDJSON. Model routes return only the first AI Gateway assistant message text.
The SDK parses and validates structured plaintext on the client.

The application is one persistent `Url4Node` process. Its model handlers call AI Gateway
in-process through one shared asynchronous HTTP client; they do not launch route subprocesses or
another engine. The thin ASGI wrapper owns only client lifecycle, global admission control, and a
whole-evaluation timeout.

The majority-vote handler is also registered once in that process. It accepts a resolved JSON
object with contiguous `member_1` through `member_n` string values, applies exact-string voting, and
breaks ties by numeric panel position. It returns only the winning text and never contacts AI
Gateway. Nonempty intent, parameters, missing panels, non-string values, and blank answers are
permanent URL4 `malformed_source` errors.

The current development profile intentionally supports tool-free model requests only. The registry does not claim
`web_search`, and `gemini/3.1-pro-preview` is not advertised because AI Gateway does not currently
register that model identifier. DRACO remains discoverable and declares its unmet requirements;
it becomes runnable only after those real capabilities exist.

## Dataset access

The case routes load the canonical Hugging Face datasets:

- `Idavidrein/gpqa`, subset `gpqa_diamond`, split `train`
- `perplexity-ai/draco`, split `test`

GPQA may require accepting the dataset terms and authenticating locally first:

```bash
huggingface-cli login
```

The Compose profile forwards `HF_TOKEN` from your shell into the engine container. No synthetic
or mock dataset fallback exists.

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

This builds the engine and AI Gateway containers. Discovery and benchmark loading do not contact
AI Gateway; model routes do.

Verify:

```bash
curl -s http://127.0.0.1:4404/healthz
curl -s http://127.0.0.1:4404/.well-known/screamingface | python -m json.tool
curl -s http://127.0.0.1:4404/benchmarks/draco@1 | python -m json.tool

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
