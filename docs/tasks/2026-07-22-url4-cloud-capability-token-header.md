---
id: OME-556
linear_url: https://linear.app/openmined/issue/OME-556/dedicated-capability-token-header-url4-capability-decouple-from
status: in_progress
type: task
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-22
closed:
---

# OME-556 — Dedicated capability token header URL4-Capability (decouple from Authorization)

The per-run capability JWT currently rides `Authorization: Bearer` (`auth/dependencies.py:23`)
on REST, colliding with the primary caller-identity slot (an API gateway / service mesh / client
SDK may already own `Authorization`, and can strip or overwrite it). Move it to a dedicated
request header **`URL4-Capability`** (bare JWT value — RFC 6648-clean, no `X-`; RFC 9449
DPoP-style secondary credential carried alongside, not on, `Authorization`).

**Owner-decided name (2026-07-22): `URL4-Capability`.**

Scope:
- REST: read the token from `URL4-Capability`; `401` problem+json on missing/invalid/expired.
- Keep the WS `?ticket=` query param (browsers cannot set WS headers).
- Remove the now-vestigial `WWW-Authenticate: Bearer` (semantics tied to `Authorization`).
- Update the OpenAPI security scheme, `docs/protocol.md §7`, spec §4/§7, and the mock client
  + tests.

**Acceptance:** REST auth reads `URL4-Capability`; unit tests cover present/missing/invalid;
OpenAPI + protocol docs updated; `run_gates.py url4-cloud` green (append-only respected —
contract-test edits are authorized under this ticket). RED-first per sdlc-python.

Parent: alignment epic (`…-spec-c-alignment`).
