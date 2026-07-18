# sf-url4-engine — temporary package development app

This application is **temporarily located under `packages/screamingface/apps/`** so the
ScreamingFace SDK and its URL4 engine profile can be developed and tested together under the
existing `screamingface` package workstream.

It is not part of the `screamingface` Python wheel and this path is not the intended production
deployment boundary. Once application ownership, CI, and release responsibilities are approved,
promote it without changing its HTTP contract to:

```text
apps/sf-url4-engine/
```

## Phase 1 responsibilities

This tracked development profile composes the generic `Url4Node` with ScreamingFace-owned data:

```text
GET /healthz
GET /.well-known/screamingface
GET /sf/benchmarks/gpqa@1
GET /sf/benchmarks/gpqa@1/cases
GET /sf/benchmarks/draco@1
GET /sf/benchmarks/draco@1/cases
```

All bodies are plaintext. Registry and manifest bodies contain JSON text; case routes contain
normalized NDJSON. The SDK parses and validates those bodies on the client.

Phase 1 does not execute Fusion expressions or judge requests. Model and reducer identities are
advertised now so the wire contract is stable; their executable endpoint adapters arrive in the
corresponding execution phases.

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

This builds the profile and AI Gateway containers. AI Gateway is included for the later model
execution phases, but Phase 1 discovery and benchmark loading do not contact it.

Verify:

```bash
curl -s http://127.0.0.1:4404/healthz
curl -s http://127.0.0.1:4404/.well-known/screamingface | python -m json.tool
curl -s http://127.0.0.1:4404/sf/benchmarks/draco@1 | python -m json.tool
```

Stop the stack:

```bash
docker compose down
```

## Native development

```bash
uv sync
uv run sf-url4-engine
```

## Validation

The app is currently covered by the parent ScreamingFace package gates. From this directory:

```bash
cd ../..
uv run ruff check src tests apps/sf-url4-engine/src apps/sf-url4-engine/tests
uv run ruff format --check src tests apps/sf-url4-engine/src apps/sf-url4-engine/tests
uv run pyright
uv run pytest --cov=screamingface --cov-fail-under=95 -q
PYTHONPATH=apps/sf-url4-engine/src uv run pytest apps/sf-url4-engine/tests \
  --cov=sf_url4_engine --cov-fail-under=95 -q
```
