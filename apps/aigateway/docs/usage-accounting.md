# Usage accounting

`POST /v1/chat/completions` can return bounded provider-attempt accounting under the top-level
`_aigw` key. OpenRouter and Anthropic are the initial supported providers.

This contract is pre-beta and may change incompatibly. The wire intentionally carries no numbered
version and no maturity label. This document and the packaged JSON Schema describe the current
contract; consumers must update with pre-beta changes.

## Current activation

The current implementation is temporarily opt-in for non-streaming calls:

```http
X-AIGW-Accounting: enabled
```

The activation header is gateway transport metadata. It is not forwarded to a provider, does not
enter provider parameter validation and does not alter the effective request-cache key. Streaming
accounting and default-on activation are the next delivery unit; until then, an opted-in
`stream:true` request is rejected before provider dispatch.

## Response shape

```json
{
  "_aigw": {
    "usage_accounting": {
      "schema": "aigw.chat_usage_accounting",
      "capture_status": "complete",
      "gateway_call_id": "call_0123456789abcdef0123456789abcdef",
      "cache": {"status": "miss", "reference": null},
      "observed_attempts": 1,
      "rendered_attempts": 1,
      "omitted_attempts": 0,
      "attempts": [
        {
          "schema": "aigw.provider_attempt",
          "attempt_id": "attempt_0123456789abcdef0123456789abcdef",
          "sequence": 1,
          "dispatch_index": 1,
          "attempt_index": 1,
          "provider": "openrouter",
          "requested_model": "openrouter/example/model",
          "response_model": "example/model",
          "provider_response_id": "generation-1",
          "transport": "litellm_async_http",
          "outcome": "succeeded",
          "http_status": 200,
          "latency_ms": 120,
          "usage": {
            "status": "complete",
            "source": "provider_raw_response",
            "input": {"total": 10, "uncached": 10, "cache_read": 0, "cache_write": 0, "cache_write_by_ttl": []},
            "output": {"total": 5, "reasoning": null}
          },
          "pricing_context": {"service_tier": null, "backend": null},
          "direct_cost": {"status": "reported", "amount": "0.001", "unit": "openrouter_credits", "source": "openrouter.usage.cost"},
          "provider_extensions": [],
          "provider_extensions_truncated": false,
          "redirect_hop_count": 0,
          "failure_code": null
        }
      ]
    },
    "request_economics": {
      "schema": "aigw.request_economics",
      "observed_new_attempts": 1,
      "direct_cost_status": "complete",
      "known_direct_cost_subtotals": [
        {"amount": "0.001", "unit": "openrouter_credits", "source": "openrouter.usage.cost"}
      ]
    }
  }
}
```

The packaged authority for exact required fields, enums, bounds and closed-object behavior is
`aigateway.core.usage_accounting/usage_accounting.schema.json`.

## Attempt meaning

One attempt represents one local provider send-pipeline admission. It proves that the gateway
admitted a send; it does not by itself prove provider receipt, model execution or billing.

- Gateway overload retries have different `dispatch_index` values.
- Hidden LiteLLM resends have different `attempt_index` values in one dispatch.
- Redirect hops remain one attempt and increment `redirect_hop_count`.
- A redirect cycle that is indistinguishable from a hidden resend marks capture `partial`.
- Failed attempts may still carry provider-authored usage or cost and must not be discarded from
  accounting solely because `outcome` is not `succeeded`.

## Status rules

Consumers may treat request cost as complete only when all of these hold:

```text
capture_status == complete
omitted_attempts == 0
direct_cost_status == complete
```

`null` means unknown or not reported, never zero. A cache hit has no new attempts. Its optional
`cache.reference` describes only historical final-response evidence and is explicitly not incurred
in the current request.

## Money and precision

Direct cost is provider-authored evidence only. Amounts are canonical non-negative fixed-point ASCII
strings with up to 18 integer and 33 fractional digits.

- Raw JSON decimals are parsed directly as `Decimal` and retain their lexical precision.
- Exact summation uses Decimal arithmetic without a finite context rounding the result.
- Binary float is not an exact money intermediary.
- Converted integer token evidence can remain useful with `source=provider_converted_response`.
- If only a converted floating-point cost remains, it must not be presented as exact direct cost
  unless that carrier is independently proven lossless.

Full raw JSON evidence is parsed only when decoded content is at most 256 KiB. Accounting metadata is
also bounded: at most 64 rendered attempts and 64 KiB for the complete `_aigw` object. Bounds degrade
to explicit partial/unavailable states instead of failing an otherwise successful provider response.

## Provider extensions

Provider-specific audit facts use namespaces such as `openrouter.response_usage` and
`anthropic.usage`. Extensions are bounded, typed, allowlisted scalar facts. They cannot contain raw
provider objects, prompts, generated text, credentials, headers, arbitrary error text or tracebacks.
Generic consumers may ignore all extensions and still interpret the canonical attempt structure.

## Ownership boundary

AIGateway owns observation, normalization, sanitization and request-local summaries. Engine owns
deterministic attribution, run/subtree rollups, persistence, UI and any pricing calculation not
directly authored by the provider response.
