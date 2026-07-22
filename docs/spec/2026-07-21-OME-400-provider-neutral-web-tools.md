# OME-400 · provider-neutral web tools

Status: implemented contract.

## Public SDK

Researchers describe capabilities, not vendors:

```python
benchmark = sf.Benchmark(
    "research@1",
    cases=load_cases,
    grader=sf.graders.Rubric(...),
    tools=(
        sf.tools.WebSearch(
            max_results=5,
            exclude_domains=("example.invalid",),
        ),
        sf.tools.WebFetch(),
    ),
    max_tool_calls=12,
)
```

There are no public `TavilySearch`/`TavilyExtract` aliases and no vendor parameter dictionary.
`WebSearch` exposes the portable behavior currently shared by the supported backends:
`max_results`, `include_domains`, and `exclude_domains`. `WebFetch` declares page retrieval.
`max_tool_calls` is required for a tool-enabled benchmark and is bounded to `1..32`.

## URL4 wire contract

An engine-advertised benchmark owns one immutable versioned policy data route. Its manifest names
that route explicitly:

```json
{
  "id": "draco@1",
  "tools": ["web_search", "web_fetch"],
  "max_tool_calls": 12,
  "tool_policy_route": "/benchmarks/draco/1/tool-policy"
}
```

The complete run URL4 resolves that route once in each case graph, builds one shared model-input
envelope, and passes that same resolved value to every answer-producing member:

```url4
(
  tool_policy:0.0:/benchmarks/draco/1/tool-policy,
  question:0.0:$item.input,
  model_input:0.0:{
    schema:'screamingface.model-input.v1',
    question:'$question',
    tool_policy:'$tool_policy'
  },
  member_1:0.0:/openrouter/google/gemini-3.1-pro-preview($model_input)!'Answer with evidence.',
  member_2:0.0:/huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra($model_input)
    !'Answer with evidence.',
  result:0.0:{member_1:'$member_1',member_2:'$member_2'}
)!'$result'
```

The route returns `screamingface.tool-policy.v1` JSON as URL4 data. The policy is backend-neutral
and contains no credentials. Reducers, synthesis calls, and graders do not inherit benchmark
research tools. Reusing the named `tool_policy` and `model_input` sources prevents both the policy
document and its envelope from being copied onto every member route and makes the benchmark
version the authority. Scalar weight `0.0` marks these as instrumental URL4 bindings; it does not
weight the models or their answers.

A researcher-authored local `sf.Benchmark` has no engine-owned policy route. Its complete run URL4
therefore carries the same portable policy inline as `tools`, `tools.max_calls`, and
`web_search.*` scalar query parameters. Repeated domains use contiguous one-based keys. This is
the portable custom-benchmark form, not a legacy fallback.

## Engine routing

The ScreamingFace engine owns tool backend selection:

- OpenRouter model routes translate the policy to OpenRouter-managed
  `openrouter:web_search`/`openrouter:web_fetch` declarations. Search uses `engine=auto`; fetch
  uses `engine=native`. AI Gateway remains a generic model transport and is unchanged.
- The two verified Hugging Face/DeepInfra routes translate the same policy into standard function
  tools. The engine runs the bounded model → Tavily → model loop itself.
- Routes without a complete adapter advertise no support and fail before model traffic.
- Model routes strictly decode `screamingface.model-input.v1`, recover the ordinary question, and
  validate the referenced policy before selecting a backend. They also reject a request that
  combines a referenced policy with inline policy parameters.

OpenRouter owns its internal server-tool loop. The engine maps `tools.max_calls` to the available
server limits (`max_total_results` and fetch `max_uses`). The Hugging Face/Tavily path enforces it
as an exact count of emitted tool calls, not a count of model turns.

## Discovery and connections

Each registry model record contains:

```json
{
  "id": "huggingface/deepseek-ai/DeepSeek-V4-Pro~deepinfra",
  "provider": "huggingface",
  "supported_tools": ["web_search", "web_fetch"],
  "required_connections": ["tavily"]
}
```

OpenRouter tool-capable records have `required_connections: []`. The SDK uses this explicit
metadata for no-spend connection preflight; it never guesses a backend from a model ID.

Tavily credentials are local-engine state and never pass through AI Gateway. This remains suitable
for the researcher-owned local engine only. A shared deployment still requires HTTPS, user
identity, authorization, and encrypted per-user secret storage.

## Boundaries

- SDK → ScreamingFace engine only.
- ScreamingFace engine → AI Gateway for every model request.
- ScreamingFace engine → Tavily only for routes using the Tavily backend.
- OpenRouter → its managed search/fetch service for OpenRouter routes.
- No AI Gateway source or contract changes are part of this implementation.

This contract supersedes the public authoring and URL4-policy portions of
`2026-07-20-OME-400-huggingface-tavily-contract.md`; that file remains a historical record of the
earlier Tavily-specific phase.
