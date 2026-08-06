---
title: URL4 Cloud model-parameter contract proxy
status: approved
created: 2026-08-05
ticket: OME-480
upstream: OME-479
downstream: OME-481
---

# URL4 Cloud model-parameter contract proxy

## Public contract

```http
GET /v1/model-parameters?model=openrouter%2Fopenai%2Fgpt-5.5
X-User-Email: alice@example.com
X-Profile: research
```

On success, URL4 Cloud returns AI Gateway's JSON document verbatim. URL4 Cloud checks only the
minimum envelope needed to avoid serving an unusable or mismatched contract:

- the body is a JSON object;
- `schema_version` is an integer;
- `model.id` equals the requested canonical model id;
- `parameters`, `tools`, and `transport` are objects.

Every response from this route carries:

```http
Cache-Control: private, no-store
Vary: X-Profile, X-User-Email
```

The route uses the existing mesh-verified identity and optional profile. AI Gateway remains the
sole owner of account/profile resolution, provider evidence, parameter schemas, and dispatch
validation. URL4 Cloud adds no cache: this document varies with account, profile, connection
state, and observed provider evidence.

## Failures

- Caller-correctable AI Gateway responses (`400`, `401`, `403`, `404`, `409`) retain their status
  and JSON body, with the private/no-store policy applied.
- An unconfigured upstream returns RFC 9457 `503`.
- A timeout returns RFC 9457 `504`.
- A transport failure, upstream `5xx`, non-JSON body, or malformed successful document returns
  RFC 9457 `502`; upstream details are not exposed.

No path returns a plausible empty parameter set after a failed lookup.

## Internal boundary

`ModelParameterSource` is a small port beside `CatalogSource`; widening `CatalogSource` would
break existing catalog-only adapters and fakes. The same `AigatewayCatalogSource` implements both
operations because they share one upstream and identity boundary. `CachedCatalog` exposes a
reference to that uncached detail source for composition, but never implements or caches the
detail operation itself. The two routes therefore preserve one HTTP client and shutdown lifecycle
without confusing cached and uncached behavior.

## Acceptance

1. `/v1/model-parameters` is present in the Engine OpenAPI document.
2. The requested model, verified identity, and optional profile reach AI Gateway.
3. A valid v1 contract passes through without field loss, including unknown fields.
4. A mismatched or malformed success fails as `502`.
5. Caller-correctable upstream responses retain their status and body.
6. Every outcome is `private, no-store` and varies by identity/profile.
7. `/v1/models`, execution, AI Gateway, URL4, and SDK behavior remain unchanged.
