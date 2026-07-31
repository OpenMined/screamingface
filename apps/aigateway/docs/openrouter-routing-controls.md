# OpenRouter price and privacy routing controls

Constrain an OpenRouter chat request by **unit price** and **downstream data policy**, per
request, on `POST /v1/chat/completions`.

Four logical OpenRouter controls are exposed as five caller-visible leaves under the existing
`provider_params` wrapper (`max_price` has independent prompt and completion ceilings). AIGateway
does **not** expose OpenRouter's raw `provider` control object — see
[Excluded fields](#excluded-fields).

```bash
curl -sX POST http://localhost:9105/v1/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openrouter/anthropic/claude-fable-5",
    "messages": [{"role": "user", "content": "hi"}],
    "provider_params": {
      "sort": "price",
      "max_price_prompt": "1",
      "max_price_completion": "2",
      "data_collection": "deny",
      "zdr": true
    }
  }'
```

## The contract

| Request path | Type | Accepted values |
|---|---|---|
| `provider_params.sort` | string | `"price"` |
| `provider_params.max_price_prompt` | string | non-negative fixed-point decimal, max 64 chars |
| `provider_params.max_price_completion` | string | non-negative fixed-point decimal, max 64 chars |
| `provider_params.data_collection` | string | `"allow"`, `"deny"` |
| `provider_params.zdr` | boolean | `true`, `false` |

Every path is also published machine-readably by `GET /v1/model-parameters`, including its JSON
Schema and its cache behavior. That endpoint is the authoritative contract; this page explains it.

Only the **object** form is accepted. A top-level key literally spelled `"provider_params.sort"`
is rejected — the wrapper is the single addressing form.

### `sort`

Asks OpenRouter to try eligible endpoints in **ascending price order**.

OpenRouter's default strategy is price-prioritized *weighted load balancing*. Explicit
`sort: "price"` **disables that load balancing** and uses ordered attempts instead — so it is a
behavior change, not merely a stronger version of the default. Omit it to keep the default.

Throughput and latency sorting are not exposed.

### `max_price_prompt` / `max_price_completion`

Excludes endpoints whose advertised unit rate exceeds the value.

- **Unit:** USD per million prompt (resp. completion) tokens, following OpenRouter's routing
  contract.
- **These are unit-rate filters, not budgets.** Neither one caps what a request or a run costs. A
  long conversation at an accepted rate can cost arbitrarily much. Total-spend limits are not part
  of this feature.

Accepted grammar: `^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$` — fixed-point decimal, no leading zeroes
except for zero itself. Rejected: negative signs, `+`, exponents (`1e5`), `NaN`/`inf`, surrounding
whitespace, incomplete forms (`.5`, `1.`), and anything over 64 characters.

**Why a string and not a number:** a JSON number is parsed as a binary float, which would round
your ceiling before the gateway ever validated it. The string preserves the exact value you sent;
the gateway parses it as a `Decimal` and emits canonical fixed-point notation upstream. `"1.000"`
and `"1"` are the same ceiling; `"10"` stays `"10"`.

### `data_collection`

- `"deny"` — use only endpoints OpenRouter classifies as **not** collecting user data.
- `"allow"` — permit endpoints that may collect data. This matches OpenRouter's documented default,
  so stating it explicitly makes a research request's policy repeatable without making the request
  less private than omitting it.
- Omission preserves existing OpenRouter/account behavior.

`data_collection: "deny"` is **not a retention guarantee.** It filters endpoints by OpenRouter's
data-collection/training classification. Retention is a separate condition — see `zdr`.

Request-level `"allow"` does not override your OpenRouter account settings; those remain enforced
upstream under OpenRouter's own policy. AIGateway adds no deployment-wide data policy.

### `zdr`

- `true` — require OpenRouter **ZDR endpoint eligibility**.
- `false` — no routing effect upstream, so the gateway omits it (the request still bypasses the
  prompt cache; see [Caching](#caching)).
- Omission preserves existing OpenRouter/account behavior.

**Scope:** `zdr` is an *upstream endpoint-eligibility condition*. It asks OpenRouter to route to
endpoints that declare zero data retention. It is **not** an end-to-end no-retention guarantee, and
it makes no claim about retention by AIGateway, URL4, logs, tools, caches, or any other
intermediary. AIGateway cannot observe upstream storage and does not attest to it.

## Strict parameter support

Every OpenRouter dispatch carries gateway-owned `provider.require_parameters = true`. OpenRouter
defaults it to *false*, under which an endpoint that does not support a supplied parameter may still
receive the request and ignore the field — an HTTP 200 that silently dropped your price ceiling.

With strictness pinned, OpenRouter refuses instead. A request no endpoint can serve **in full**
comes back as an explicit sanitized error (typically `404`), never as a success that quietly
ignored a constraint. A tighter ceiling therefore trades availability for correctness, by design.

`require_parameters` is gateway-owned: it cannot be removed, and it cannot be set to false.

## Errors

| Situation | Response |
|---|---|
| Invalid value (bad grammar, unknown enum, wrong type, too long) | `400` `unsupported_parameters`, with the offending request path named and reason `malformed` |
| Unknown leaf under `provider_params` | `400` `unsupported_parameters`, reason `unknown` |
| Excluded routing field (see below) | `400` `unsupported_parameters`, reason `unknown` |
| No endpoint satisfies the combined filters | the sanitized upstream refusal (e.g. `404`); a valid credential stays valid |
| Internal policy-projection mismatch | `503` `provider_unavailable` |

Rejections name **request paths and closed reason codes only** — never the value you sent. A
rejection happens before any credential material is read and before any provider dispatch, and one
bad leaf refuses the whole request rather than serving it partially.

## Excluded fields

The raw `provider` object is **not** a request path, and neither is any of the routing/fallback
control plane around it. All of these are rejected by name, at the top level *and* inside
`provider_params`:

`provider` · `order` · `only` · `ignore` · `allow_fallbacks` · `quantizations` · `route` ·
`models` · `plugins`

Provider and endpoint pinning, provider ordering and allowlists, model fallback lists, and router
metadata are all out of scope. The gateway reconstructs the upstream `provider` object from the five
validated leaves above and nothing else, so an excluded field has no path to the wire.

Separately, generic LiteLLM dispatch controls (`api_base`, `base_url`, `model_list`, `extra_body`,
and the rest of the control plane) are **silently stripped at ingress** for every provider, before
profile, cache, credential and dispatch processing. They are not model parameters, so they are
dropped rather than reported. No caller field can redirect your account-scoped credential to another
host.

## Caching

**Every request carrying any of the five controls bypasses AIGateway's request cache**, and
responds with `X-AIGW-Cache: bypass`. Nothing is read from the cache and nothing is written to it.

This includes `zdr: false`: the bypass is owed to the field's *presence in the request*, not to its
effect on the wire. `GET /v1/model-parameters` publishes `cache_behavior: "bypass"` for all five
paths.

Why: the v1 cache key is prompt-only and cannot represent a routing policy, so a cached answer
produced under a *different* price ceiling or data policy could otherwise be served for yours. A
control will only become cacheable once the cache key carries the full reconstructed policy.

## Not yet transported by URL4

URL4 does not currently carry these controls. Setting them in a URL4 expression has no effect —
reach `POST /v1/chat/completions` directly to use them. Profile defaults and deployment-wide
defaults are likewise not supported: the controls are per-request only.
