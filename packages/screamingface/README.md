# screamingface

The Python SDK for composing URL4-backed model fusions and measuring whether a fusion beats its
strongest member.

## Quickstart

```python
import screamingface as sf

sf.setup(mode="mock", static_widgets=True)
model_ids = sf.models.list(max_price=20)
fusion = sf.Fusion(
    "frontier-trio",
    models=model_ids[:3],
    reduce="majority_vote",
    judge=model_ids[0],
)
run = fusion.evaluate("gpqa", first=20, seed=0)

print(fusion)       # notebook-friendly lineup table
print(fusion.url4)  # canonical recipe only when explicitly requested
print(run.score, run.baseline, run.gain)
```

Fusions can also be kept as reviewable configuration. See
[`examples/fusion.yaml`](examples/fusion.yaml):

```yaml
name: yaml-trio
models:
  - codex/gpt-5.5
  - gemini-cli/gemini-2.5-pro
  - anthropic/claude-sonnet-4-6
reduce: majority_vote
judge: codex/gpt-5.5
```

```python
fusion = sf.Fusion.from_yaml("fusion.yaml")

# The same fields can be supplied inline.
fusion = sf.Fusion(**fusion_config)
```

YAML is loaded with PyYAML's safe loader and does not execute or contact providers. Model IDs are
exact, provider-qualified IDs from `sf.models.list()`; the SDK does not silently translate aliases
such as `hf/` or route a recipe through a provider absent from the active gateway catalog.

The executed [YAML quickstart notebook](examples/yaml_quickstart.ipynb) walks through catalog-ID
validation, `Fusion.from_yaml(...)`, the lineup representation, explicit `.url4`, equivalent
`Fusion(**mapping)` construction, evaluation, and the rich Run result card.

The word “budget” has no special meaning in a Fusion name. Runtime budgeting and spend approval
were removed from this SDK. The optional `sf.models.list(max_price=20)` argument only filters the
catalog by listed per-token price; it does not reserve funds, approve spending, or enforce a cap.
In live mode, `sf.models.list()` reports models loaded by AI Gateway even when their providers are
not connected yet, so Python and YAML users can compose the same fusion before authentication.

The checked-in [notebook](examples/00_quickstart.ipynb) executes this path in explicit mock mode.
Its questions and model answers are synthetic and its output is prominently labeled as a
simulation. It demonstrates the SDK—not provider quality on GPQA.

`mode="mock"` and `static_widgets=True` are intentionally separate:

| Setting | Changes execution? | Purpose |
| --- | --- | --- |
| `mode="mock"` | Yes | Uses the bundled synthetic fixture and deterministic local model answers; no gateway, provider calls, or spend. |
| `static_widgets=True` | No | Uses stable non-interactive representations suitable for committed GitHub notebook output. |

Keep both in the committed quickstart so it executes offline and reproducibly. For a real local
run, use `sf.setup()` and leave `static_widgets` at its default `False`. Static widgets alone do not
mock providers or benchmark results, and live mode never silently becomes mock mode.

From a repository checkout, launch Jupyter through the package environment:

```bash
cd packages/screamingface
uv run --extra notebook jupyter lab examples/00_quickstart.ipynb
# Or open the declarative version:
uv run --extra notebook jupyter lab examples/yaml_quickstart.ipynb
```

In an existing Jupyter or editor session, select the interpreter at
`packages/screamingface/.venv/bin/python`. A global Python kernel opened from the repository root
can otherwise import the top-level repository directory as an empty namespace named
`screamingface` instead of importing this SDK.

## Live mode and AI Gateway

`sf.setup()` defaults to live mode. It looks for AI Gateway in this order:

1. the explicit `gateway=` argument;
2. `SCREAMINGFACE_GATEWAY_URL`; then
3. `http://127.0.0.1:9105`.

In a notebook, zero-argument `sf.setup()` renders an interactive login/provider panel. In a
script, supply a gateway JWT with `token=`/`SCREAMINGFACE_GATEWAY_TOKEN`, or pass an AI Gateway
`username=` and `password=`. There are no built-in credentials and live mode never falls back to
mock mode. Re-running `sf.setup()` for the same gateway in the same Python kernel reuses the
authenticated in-memory session. `sf.shutdown()`, a kernel restart, or switching gateways requires
authentication again.

Gateway login and provider authorization are deliberately separate. Logging in identifies you
and unlocks your encrypted AI Gateway credential vault; it does not grant Anthropic, Google, or
Hugging Face inference access. For this quickstart, you bring an API key from each provider you
want to use. Those providers bill their own calls. The SDK submits each key to the configured AI
Gateway, which encrypts it at rest. The SDK then removes the key from the widget field and does
not retain it in Session state.

```python
session = sf.setup(
    gateway="https://gateway.example",
    token="...",  # prefer SCREAMINGFACE_GATEWAY_TOKEN outside short-lived examples
)
```

The notebook discovers loaded providers from the running gateway and renders rows using a
temporary SDK-local authentication-method map for the gateway's current provider plugins. The
SDK will prefer gateway-reported `auth_methods` when that capability becomes part of the gateway
HTTP contract. Keyless local providers are shown separately.
Providers are alphabetized as compact rows without nested cards or scrolling. Connection fields
stay collapsed until requested. A provider offering both methods shows separate **Connect with
OAuth** and **Use API key** actions. Choosing API key replaces those actions inline with a masked
field plus **Save API key** and **Cancel**; choosing OAuth replaces them with a prominent
**Authorize provider** link and **Cancel connection**. Connected rows show their status and
**Disconnect**. After OAuth starts, the notebook checks the gateway automatically until
authorization succeeds or expires; **Check connection status** remains as a manual fallback. The
same operations are available headlessly.

The unauthenticated setup view is a compact sign-in card. It explains that the AI Gateway account
unlocks encrypted provider connections while upstream provider keys and billing remain separate.

Headless connection operations use the same gateway APIs:

```python
sf.providers()
sf.connections()
connection = sf.connect("anthropic", api_key="...")
connection = sf.connect("anthropic", api_key="...")  # replaces the default key
sf.disconnect(connection.id)

oauth = sf.connect_oauth("codex")
print(oauth.authorize_url)
active = sf.wait_for_connection(oauth.connection_id)
sf.shutdown()
```

Loading or displaying a Fusion never requires provider credentials. Immediately before a live
evaluation, the SDK refreshes gateway connections and checks every fusion model. Missing providers
or unavailable models raise one typed `FusionNotReady` error listing all required actions. This
happens before progress rendering, dataset loading, model calls, or spend. Runtime failures remain
per-model so a provider outage after a successful preflight does not discard other answers.

`Run` records the exact URL4 recipe, dataset identity, selected non-secret profiles, per-model
scores, token usage, estimated costs, dated pricing provenance, incomplete rows, and structured
provider failures. Its notebook representation renders score, gain, best-member baseline, cost
status, reducer/judge, per-model accuracy bars, failures, and provenance in one result card. Mock
cards are prominently marked `SIMULATED · NO PROVIDER CLAIM`; live cards are marked
`LIVE PROVIDER RUN`. One provider failure does not discard successful panel answers.

Live GPQA loading also requires `uv sync --extra datasets`, Hugging Face authentication, and prior
acceptance of the gated dataset terms. Real GPQA question text is never bundled in this package or
committed in notebook output.

Live notebook evaluation displays dataset loading and exact model-call progress automatically. A
20-question, three-member fusion therefore advances through 60 calls. Each question queries all
fusion members concurrently; questions run sequentially and each provider request has a 30-second
timeout. Pass `progress=False` to suppress the display.

## What URL4 does

`Fusion` compiles the panel into a canonical URL4 expression and includes versioned,
non-secret ScreamingFace metadata for its name and tie-breaking judge. `fusion.url4` exposes that
recipe; the normal text/HTML representation intentionally shows the lineup instead. During evaluation,
URL4 performs the model fan-out and invokes the majority-vote reducer. ScreamingFace supplies the
model I/O, benchmark scoring, best-member baseline, and provenance. Every member response is reused
for the baseline, so comparison does not make duplicate provider calls.

ScreamingFace uses `url4.Url4Node` in embedded mode: the SDK constructs and evaluates the node
inside the Python process, and its outbound I/O adapter translates `sf-model://...` sources into
AI Gateway completion calls. Users do **not** start a URL4 server for the quickstart. The separate
`url4_server.ipynb` example demonstrates the optional deployment mode where the same node is
served over HTTP for remote URL4 clients; AI Gateway is the only external service required by a
live ScreamingFace notebook.
