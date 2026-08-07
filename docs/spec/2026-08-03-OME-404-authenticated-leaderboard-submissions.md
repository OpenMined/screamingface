---
title: Authenticated leaderboard submissions — trust the mesh identity header
status: approved-design, pending-implementation
created: 2026-08-03
author: Filip Boltuzic + Claude (Sonnet 5)
supersedes: unauthenticated stub on POST /v1/scores (OME-404's original stub, OME-320)
related:
  - apps/aigateway/src/aigateway/core/auth/cloudflare_identity.py (pattern this mirrors)
  - apps/aigateway/src/aigateway/core/auth/middleware.py (_account_from_cloudflare_headers)
  - apps/url4-cloud/deploy/helm/templates/securitypolicy.yaml (Envoy-side header injection)
  - OME-326 (OpenMined's issue authentication header to participants — done 2026-08-03)
  - OME-684 (adopt the Cloudflare Access identity headers across url4-cloud and aigateway)
---

# Authenticated leaderboard submissions — spec

## Context

`POST /v1/scores` (`apps/scoreboard/src/scoreboard/routes/scores.py`) currently accepts
submissions with zero authentication — the route's own docstring says so — and stores whatever
free-text `submitted_by` string the caller sends. OME-404 asks for this to become authenticated.
It was blocked on OME-326 (OpenMined's participant identity issuance), which completed today
(2026-08-03), clearing the path.

Per today's team huddles (Kevin/Irina/Dmitry, then Ionesio directly), the intended mechanism is
already built and live for aigateway: Cloudflare Access authenticates the user; Envoy (the
platform's ingress) re-verifies that assertion and injects a single trusted header carrying the
user's email, replacing any client-supplied value of the same name. Downstream services never
verify a JWT themselves — they just read the header, behind a network-trust boundary that
guarantees only the mesh can present it. This spec adopts that exact pattern for the scoreboard
rather than inventing a new one.

## Decisions locked (2026-08-03)

| # | Decision | Choice |
|---|---|---|
| D1 | Header name | **`X-User-Email`** — the same constant (`HEADER_USER_EMAIL`) aigateway already uses in `core/auth/cloudflare_identity.py`. No new header convention. |
| D2 | Verification | **None, in scoreboard.** JWT/JWKS verification is Envoy's job (`apps/url4-cloud/deploy/helm/templates/securitypolicy.yaml`'s `claimToHeaders` mapping). Scoreboard trusts the header exactly as aigateway does. |
| D3 | Missing/blank header | **401**, no anonymous fallback. Mirrors aigateway's `_account_from_cloudflare_headers`, which raises rather than degrading to an unauthenticated identity. |
| D4 | `submitted_by` field | The client-supplied `submitted_by` on `ScoreSubmission` is **dropped from the write path** — the stored value is always the header-derived email. The schema field can stay for backward-compat read purposes if other callers rely on it, but `submit_score` no longer trusts it as input. |
| D5 | Network-trust boundary | Scoreboard must not be reachable except through the mesh, mirroring aigateway's `NetworkPolicy` + `allowedNetworks` invariant — a header that anyone could set directly is not authentication. Chart-level guard is in scope for this unit; the guard doesn't need to be identical code, only equivalent protection. |
| D6 | Scope boundary | This unit does **not** touch re-run/score verification (`verified_by_openmined`, OME-414) — that's a separate, much larger, still-unowned effort. This unit only answers "who submitted this," not "is the claimed score true." |

## Open questions

- Whether existing SDK/client callers (notebook, CLI) already send `X-User-Email` themselves or
  rely entirely on the mesh to inject it — if any client-side code constructs this header today,
  it needs auditing so a directly-reachable dev/test path doesn't let a caller self-assert
  identity. Out of scope to resolve here; flag to Ionesio if found during implementation.
- Exact NetworkPolicy/allowlist mechanism for scoreboard's chart (CIDR list vs. Envoy Gateway
  SecurityPolicy passthrough) — deferred to implementation; aigateway's existing
  `networkpolicy.yaml` + `_helpers.tpl` fail-guard is the reference, not a literal copy
  requirement.
