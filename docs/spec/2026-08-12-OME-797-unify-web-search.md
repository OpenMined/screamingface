# OME-797 — One web-search flag per route

Status: approved (owner, 2026-08-12) · Stack: url4-cloud

## 1. Problem

`url4.toml` declares two capability flags per route:

| Flag | Mechanism | Runs where |
|---|---|---|
| `web_tools` | Tavily `web_search`/`web_fetch` tool loop | url4-cloud runner |
| `native_web_search` | provider-side search envelope | aigateway → OpenRouter |

Three defects follow:

1. The operator must know which mechanism each model supports. The knowledge is in the
   operator's head, not in the code.
2. Both flags default to `false`. A route does not search until a person declares it.
3. The file header documents `web_tools` and never defines `native_web_search`.

## 2. Contract

One declared field replaces both:

```toml
[[aigateway.models]]
id = "openrouter/openai/gpt-5.5"   # web_search defaults to true
```

- `web_search: bool = True`. This is the only field an operator sets.
- The mechanism is derived, never declared.

### 2.1 Provider resolution

`provider_of(model_id)` returns the segment before the first `/`. An identifier with no `/`
is `anthropic`, which is the convention aigateway's catalog already uses.

```
"openrouter/anthropic/claude-opus-4.8" -> "openrouter"
"gemini-cli/gemini-2.5-pro"            -> "gemini-cli"
"claude-haiku-4-5"                     -> "anthropic"
```

The match is on the segment, NOT on a substring of the whole identifier. A substring test
gives `openrouter/anthropic/claude-opus-4.8` to a future `anthropic` entry, and that route
must use the OpenRouter envelope.

### 2.2 Mechanism selection

```
WEB_SEARCH_NATIVE_PROVIDERS = {"openrouter"}

uses_native_web_search := web_search and provider_of(id) in WEB_SEARCH_NATIVE_PROVIDERS
uses_web_tools         := web_search and not uses_native_web_search
```

INVARIANT: the two are mutually exclusive, and their disjunction equals `web_search`.

### 2.3 Why the set holds only `openrouter`

`web_search` is declared by exactly one aigateway plugin
(`plugins/openrouter_provider/parameters.py:279-286`). The other plugins register a bespoke
`custom_llm_provider` — `codex` (OpenAI Codex OAuth), `gemini-cli` (Google Code Assist),
`antigravity`, and aigateway's own `anthropic` handler — instead of litellm's stock vendor
routes. litellm exposes native search through `web_search_options`, which those bespoke
handlers do not carry; the string appears nowhere in aigateway. A request with an undeclared
parameter is refused by the parameter contract.

Adding a provider to the set is therefore aigateway work, per provider: declare the
parameter, build the envelope from one pure function used by both the dispatch path and the
cache-key projection (OME-777 invariant I1), key the fields, and bump the cache adapter
revision. Out of scope here.

## 3. No migration path

`web_tools` and `native_web_search` are deleted outright. There is no compatibility shim, no
alias, and no bespoke error for them — they are simply not keys any more.

WHY this is safe: `url4.toml` is baked into the image at `/etc/url4/url4.toml`, so the
config ships with the code that reads it. A config carrying the old keys and a runtime
expecting the new one do not coexist. If an operator overrides the file, the parser's
existing unknown-key check already fails closed at startup.

## 4. Behaviour that does not change

- `;web_search=false` in a URL4 expression disables retrieval on any route.
- `;web_search=true` on a route with `web_search = false` raises `web_retrieval_unavailable`.
- A Benchmark that requires retrieval on such a route raises
  `benchmark_retrieval_unavailable`. Retrieval fails closed; it never degrades silently.
- An explicit search request with no Tavily connection raises. An implicit one (the route
  searches by default, the caller said nothing, no benchmark policy) serves plain
  completions.
- Caller exclusion lists bind on both paths.
- The native path sends `web_search: true` and never `tools`. The Tavily path sends
  `tools`/`tool_choice` and never `web_search`.

## 5. Accepted consequences

- Routes whose tool round-trip is not verified end-to-end (anthropic, codex, gemini-cli,
  antigravity) now search by default when a Tavily key is present. Verification is a later
  PR, by owner decision. A deployment with no `TAVILY_API_KEY` is unaffected: those routes
  serve plain completions. Where a key IS present, the failure mode is not a silent
  downgrade: if one of those bespoke backends rejects an OpenAI-shape tool call, the call
  fails rather than answering without retrieval, and all 15 routes flip in one deploy.

### 5.1 DRACO moves — correcting an earlier claim in this spec

An earlier revision of this section claimed DRACO pins `web_search=false` and therefore does
not move. **That was wrong.** `definition.py:53` pins `("web_search", "false")` in
`JUDGE_PARAMS` only — Grading cannot retrieve. The Candidate call at `definition.py:236`
pins `web_search=True` with `EXCLUDED_DOMAINS`.

All eight DRACO lineup models are `openrouter/*`, and five of them
(`gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `kimi-k2.6`, `deepseek-v4-pro`,
`qwen3.6-plus`) declared `web_tools` and now derive to the native mechanism. Two consequences,
both accepted by the owner (2026-08-12):

1. **Search backend changes for 5 of 8 candidates** — Tavily → OpenRouter, which for these
   models resolves to Exa. `REVISION` hashes the dataset, protocol, `RETRIEVAL_POLICY_ID`,
   `EXCLUDED_DOMAINS` and judge fields, none of which change, so the published revision and
   route prefix stay identical across the change. `benchmarks/draco/aggregate.py` records
   which mechanism a given run used, in its protocol-caveat block.
2. **`EXCLUDED_DOMAINS` changes enforcement mode** — the Tavily loop filters results
   client-side (`web_tools._is_blocked`); the native path forwards
   `web_search_excluded_domains` and relies on the provider. For a reproduction whose
   blocklist covers `arxiv.org`, `paperswithcode.com`, `semanticscholar.org` and
   `alphaxiv.org` — the venues hosting the paper under reproduction — this moves a leakage
   control from enforced to trusted for those five candidates.
