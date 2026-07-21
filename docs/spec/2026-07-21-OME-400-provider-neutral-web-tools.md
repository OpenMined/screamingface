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

The SDK applies this policy to answer-producing member calls only:

```url4
/openrouter/google/gemini-3.1-pro-preview
  ?tools=web_search:web_fetch
  &tools.max_calls=12
  &web_search.max_results=5
  &web_search.exclude_domain.1=example.invalid
  ($question)!'Answer with evidence.'
```

The policy is backend-neutral and contains no credentials. Domains use contiguous one-based
query keys. Reducers, synthesis calls, and graders do not inherit benchmark research tools.

## Engine routing

The ScreamingFace engine owns tool backend selection:

- OpenRouter model routes translate the policy to OpenRouter-managed
  `openrouter:web_search`/`openrouter:web_fetch` declarations. Search uses `engine=auto`; fetch
  uses `engine=native`. AI Gateway remains a generic model transport and is unchanged.
- The two verified Hugging Face/DeepInfra routes translate the same policy into standard function
  tools. The engine runs the bounded model → Tavily → model loop itself.
- Routes without a complete adapter advertise no support and fail before model traffic.

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
