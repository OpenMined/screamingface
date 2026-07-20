---
title: ScreamingFace Hugging Face and Tavily contract
ticket: OME-400
status: approved
date: 2026-07-20
---

# ScreamingFace Hugging Face and Tavily contract

## 1. Decision and ownership

ScreamingFace supports research-capable Hugging Face Inference models by composing two independent
services inside the application-owned `screamingface-engine` profile:

```text
ScreamingFace SDK
  -> screamingface-engine / URL4 node
     -> AI Gateway -> Hugging Face Inference -> pinned inference provider -> model
     -> Tavily search/extract
```

The SDK contacts only its configured ScreamingFace engine. AI Gateway remains the model and model-
credential boundary. Tavily is not a model provider and does not pass through AI Gateway; its
credential and requests are owned by the ScreamingFace engine. Generic `packages/url4` remains
provider-agnostic and requires no DRACO-, Gateway-, Hugging Face-, or Tavily-specific change.

SearXNG and direct public-page fetching are removed when the Tavily execution phase lands. There
is no runtime mock, legacy string-tool API, silent tool fallback, or direct SDK service client.

## 2. Hugging Face discovery and public identity

AI Gateway's protected `GET /v1/models` is the model-availability source of truth. ScreamingFace
does not copy an HF model list. Each HF Gateway entry is pinned to an inference provider:

```text
Gateway:      huggingface/deepseek-ai/DeepSeek-V4-Pro:deepinfra
Public URL4:  huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra
```

The public `~provider` suffix exists because `:` is not valid in a URL4 relative route. The engine
keeps the exact private Gateway ID and restores it for dispatch. A valid HF ID has a non-empty
repository path and exactly one non-empty terminal provider pin; a public ID may not already
contain `~`. Malformed or colliding aliases fail engine startup.

HF models are initially advertised with no named tools. Tool capabilities are attached only to
exact model/provider routes verified for the complete multi-turn tool protocol. A newly discovered
HF route therefore defaults to tool-free rather than inheriting an unproven provider-wide claim.

## 3. Provider connections

The public SDK remains:

```python
sf.connect("huggingface", api_key="hf_...")
sf.connect("tavily", api_key="tvly-...")
```

The HF key traverses SDK -> ScreamingFace engine -> AI Gateway and is persisted only by AI
Gateway. The Tavily key traverses SDK -> ScreamingFace engine and is owned by the engine's tool-
service adapter. Neither credential may appear in a URL4 expression, URL, registry, model message,
tool result, notebook output, representation, or log.

AI Gateway currently exposes model discovery but not provider/auth discovery. Until a protected
Gateway provider-capability endpoint exists, ScreamingFace's explicit provider policy adds
Hugging Face as API-key-only alongside the existing model providers. This is deployment policy,
not a model-list or runtime fallback. Tavily is always appended by the engine because it is an
engine-owned tool provider.

The future Gateway provider response must distinguish static capability, deployment readiness,
and current-user connection state. The engine will reflect available Gateway methods and combine
them with its own tool providers; the SDK will continue to read only the engine registry.

Phase 9B.2 implements the Tavily connection for the researcher-owned local engine as follows:

- `PUT /v1/connections/tavily/api-key` validates the candidate directly with authenticated
  `GET https://api.tavily.com/usage` before reporting `connected`;
- the validated key is retained only in the running engine process, is cleared by disconnect or
  restart, and has no environment-variable or persistence fallback;
- replacement is atomic: an invalid candidate leaves the previous validated connection active;
- the public registry advertises Tavily as API-key-only, while SDK list/get/disconnect behavior
  remains the same generic connection contract used by model providers; and
- invalid credentials, rate limits, service/network failures, and malformed success responses
  become safe structured errors without exposing either the candidate key or Tavily's body.

This process-memory implementation is deliberately for a researcher-owned local engine. It is not
a credential design for a shared hosted deployment. A hosted engine must add HTTPS, authenticated
researcher identity, authorization, and encrypted per-user credential storage before accepting
Tavily keys. The current implementation must not be exposed as an unauthenticated shared service.

## 4. Researcher-facing tool configuration

Tools belong to the benchmark because they are experimental policy applied consistently across
answer-producing members. They do not belong to `Fusion` and are not ordinary model parameters.
The approved public values are immutable typed objects:

```python
sf.Benchmark(
    "research@1",
    cases=cases,
    grader=grader,
    tools=(
        sf.tools.TavilySearch(
            search_depth="basic",
            max_results=5,
            topic="general",
            include_raw_content=False,
            exclude_domains=("example.invalid",),
        ),
        sf.tools.TavilyExtract(
            extract_depth="basic",
            format="markdown",
            timeout=30,
        ),
    ),
    max_tool_rounds=12,
)
```

`TavilySearch` and `TavilyExtract` expose the corresponding Tavily request fields with local type,
range, and combination validation. Built-in benchmarks pin their policy; ordinary users need not
construct these objects. `Benchmark.tools` becomes a tuple of typed tool values directly, with no
compatibility path for the unreleased string-tool representation.

The stable search policy surface is:

```python
sf.tools.TavilySearch(
    search_depth="basic",          # advanced | basic | fast | ultra-fast
    chunks_per_source=None,        # 1..3; advanced only
    max_results=5,                 # 0..20
    topic="general",               # general | news | finance
    time_range=None,               # day/week/month/year or d/w/m/y
    start_date=None,               # ISO YYYY-MM-DD
    end_date=None,                 # ISO YYYY-MM-DD
    include_answer=False,          # bool | basic | advanced
    include_raw_content=False,     # bool | markdown | text
    include_images=False,
    include_image_descriptions=False,
    include_favicon=False,
    include_domains=(),            # ordered unique values; at most 300
    exclude_domains=(),            # ordered unique values; at most 150
    country=None,                  # general topic only
    auto_parameters=False,
    exact_match=False,
    include_usage=False,
    safe_search=False,             # incompatible with fast/ultra-fast
)
```

Image descriptions require images. If both dates are supplied, the start cannot be later than the
end. The stable extract policy surface is:

```python
sf.tools.TavilyExtract(
    extract_depth="basic",         # basic | advanced
    chunks_per_source=None,        # 1..5
    include_images=False,
    include_favicon=False,
    format="markdown",             # markdown | text
    timeout=None,                  # numeric 1.0..60.0 seconds
    include_usage=False,
)
```

At model runtime, the only exposed calls are `web_search(query)` and
`web_fetch(url, query=None)`. Runtime arguments are separate from benchmark policy and are never
accepted as arbitrary SDK dictionaries.

The compiler emits scalar URL4 parameters. Repeated values use stable numbered keys rather than a
hidden JSON string:

```text
?tools=web_search+web_fetch
&tavily.search.max_results=5
&tavily.search.exclude_domain.1=example.invalid
&tavily.extract.format=markdown
```

Tool configuration repeats on each answer-producing member. Model reducers and benchmark judges
remain tool-free.

## 5. Engine execution

For each tool-enabled member, the engine performs the bounded behavior established by the current
HF benchmark runner:

1. Preflight the model route, verified tools, HF connection, and Tavily connection before spend.
2. Call the same HF model through AI Gateway with the benchmark's function declarations.
3. If the model emits tool calls, retain its assistant message and call identities.
4. Execute calls through Tavily in emitted order and append sanitized tool-result messages.
5. Call the same model with the complete conversation.
6. Repeat until final assistant text or the configured tool-round limit.
7. Return only the final plaintext answer to URL4.

`max_tool_rounds` names the behavior honestly: the reference runner's `max_calls_per_row` bounds
model-loop iterations, and one round may emit multiple tool calls. Tavily timeouts, rate limits,
and transient server failures receive bounded retries. Invalid tool arguments become safe tool
errors the model may inspect. Exhaustion becomes an explicit `tool_budget_exhausted` failure, not
an empty answer. Results are deterministically bounded and mark truncation.

Panel members remain independent. Their model calls may run concurrently, while calls emitted by
one model turn execute sequentially for reference-pipeline parity. Fusion reduction and DRACO
judge calls are tool-free.

## 6. AI Gateway dependency contract

Gateway provider adapters must not silently discard request fields. The minimum DRACO request
surface to verify end to end is `temperature`, `max_tokens`, `reasoning_effort`, `tools`, assistant
`tool_calls`, and subsequent tool-result messages. Unsupported parameters must return a structured
`400 unsupported_parameter` response.

Known external gaps are:

- Codex currently drops `temperature` and `max_tokens` in its upstream payload.
- Gemini currently drops `reasoning_effort`, preventing the requested low-reasoning judge parity.
- Codex multi-turn tool-message fidelity is not established.
- `GET /v1/models` does not advertise model request/tool capabilities.
- AI Gateway has no provider/auth-capability discovery endpoint.

These are AI Gateway responsibilities. ScreamingFace does not compensate with silent defaults or
direct provider calls. Phase 9 can implement HF/Tavily execution against verified fields while the
full mixed-model DRACO claim remains gated by the relevant Gateway capabilities.

## 7. DRACO acceptance

Implementation proceeds from the smallest real proof:

1. one DRACO case through one pinned HF model with Tavily search/extract and rubric grading;
2. one case through two verified HF members plus one model reducer;
3. the documented eight-solo/five-fusion structure; and
4. the complete configured DRACO run.

The initial known pairs are DeepSeek V4 Pro on DeepInfra and GLM 5.2 on DeepInfra. Kimi K2.6 on
Fireworks remains discoverable if Gateway offers it but is excluded from the canonical DRACO
configuration because the recorded MedXpert run observed extensive empty responses. Another HF
provider must be probed before Kimi is pinned in `draco@1`.

A DRACO reproduction claim requires the same dataset/cases, prompts, tool policy, model/provider
pins, Fusion structures, judge protocol, and aggregation formula through the new engine. Generated
answers need not be byte-identical because model generation and search results vary. Automated
tests use injected transports rather than a user-facing mock runtime; separately marked live
acceptance exercises the real HF and Tavily path.

## 8. Delivery slices

- **9B.1:** Gateway-derived HF routes, URL4-safe aliases, and HF API-key connection support; no
  tool claims.
- **9B.2 (implemented):** engine-owned, directly validated, process-local Tavily connection and
  explicit shared-hosting boundary.
- **9B.3 (implemented):** typed SDK tool values, benchmark policy, and URL4 compilation.
- **9B.4:** Tavily adapter plus bounded HF agent loop; remove SearXNG.
- **9B.5:** canonical DRACO configuration, notebook, real one-case/two-member acceptance, then full
  reproduction readiness.
