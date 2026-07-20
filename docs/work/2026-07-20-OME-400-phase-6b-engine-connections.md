---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 6B engine provider-connection bridge

## Intent

Implement the approved private provider-connection control plane in the temporary
`screamingface-engine`. The engine will advertise public provider ownership, intercept connection
management requests before URL4 evaluation, and adapt them to AI Gateway's existing APIs without
changing AI Gateway, URL4, SDK preflight, or notebook widgets.

## Planned changes

- Extend the canonical engine catalog and public registry with provider capabilities and explicit
  model-provider ownership while keeping private Gateway model/profile identifiers internal.
- Add a focused asynchronous AI Gateway connection adapter for list/status, OAuth start and
  completion, API-key create/replace, and idempotent disconnect using only existing Gateway APIs.
- Add an application-owned private JSON control plane under `/v1/connections`, including the
  public OAuth callback boundary, before all other traffic delegates unchanged to `Url4Node`.
- Normalize Gateway failures into the approved safe ScreamingFace error schema without retaining
  credentials, tokens, unsafe upstream bodies, or internal identifiers.
- Bound request bodies, response bodies, redirects, timeouts, OAuth state lifetime, and adapter
  lifecycle; escape callback HTML and keep anonymous operation local-only.
- Persist the development Gateway database and generated secret material through named Docker
  volumes while keeping all published ports loopback-only.
- Update the temporary engine README and Phase 6 plan/task records after verified behavior exists.

## Test plan

- Add new Phase 6B tests first and confirm RED for missing provider registry fields and control
  routes.
- Cover exact public registry provider/model ownership and prove private Gateway aliases remain
  absent.
- Cover list, single status, OAuth start, OAuth callback, API-key PUT, and idempotent DELETE using
  deterministic fake Gateway HTTP transports.
- Cover method/path/content-type/body bounds, duplicate JSON fields, missing/unknown providers,
  unsupported methods, redirects, timeouts, unavailable Gateway, invalid Gateway responses, and
  safe normalized error envelopes.
- Prove sentinel keys/tokens appear only in the one outbound Gateway request body and never in
  URLs, responses, errors, representations, or logs.
- Cover OAuth state expiry, mismatch, single use, cancellation, and escaped callback HTML.
- Run engine-focused tests, the full ScreamingFace SDK suite, coverage, Ruff, formatting, Pyright,
  the authoritative ScreamingFace gate, and an isolated Docker smoke test where feasible.

## Acceptance

- The tracked development engine serves the exact approved provider registry and private JSON
  connection routes while URL4 success responses remain plaintext and unchanged.
- All current-user connection state is sanitized to public provider IDs and no credential or
  Gateway-private identifier crosses the engine boundary.
- API keys use only PUT JSON bodies; OAuth uses bounded single-use engine callback state; private
  failures use stable safe codes.
- Engine and Gateway clients share one bounded lifecycle, development persistence survives an
  ordinary restart, and host ports remain loopback-only.
- No AI Gateway source, schema, migration, URL4 source, SDK execution preflight, or widget is
  introduced in this phase.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** extended the canonical engine catalog, registry, shared Gateway client, app
  assembly, and ASGI wrapper; added focused connection-Gateway and connection-ASGI modules; added
  Phase 6B route/boundary tests; updated the engine Compose profile, README, provider-connections
  contract, architecture plan, and task record.
- **Commits:** pending the owner's requested commit after review.
- **Gates:** the authoritative ScreamingFace gate is green (append-only check, Ruff lint and
  formatting, Pyright, and the SDK test suite at the required coverage). The full engine suite is
  green with 113 tests and 95.82% coverage. An isolated Docker profile proved registry/status
  behavior, API-key secrecy, named-volume persistence across `down`/`up`, idempotent disconnect,
  and an OAuth authorize URL whose callback is owned by the engine.
- **Deviations:** the reviewed universal `/v1/connections/oauth/callback` idea was corrected after
  verifying AI Gateway's existing provider clients. The engine now owns the already-registered
  provider-specific callback paths (`/auth/callback`, `/oauth2callback`, and `/callback`) and
  relays only `code` and `state`. OAuth state expiry, mismatch, and single-use enforcement remain
  AI Gateway's responsibility rather than being duplicated in the engine. No AI Gateway or URL4
  source was changed.
