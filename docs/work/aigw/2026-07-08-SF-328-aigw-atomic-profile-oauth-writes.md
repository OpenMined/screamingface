---
ticket: SF-328
stack: aigateway
status: completed
started: 2026-07-08
finished: 2026-07-09
---

# SF-328 — AIGateway Atomic Profile/OAuth Credential Writes

## Intent

Make profile metadata and OAuth/API-key credential state transitions atomic where possible and explicitly compensating where cross-store atomicity is not available. This closes the C6/A2/A6 failure modes where concurrent profile-index writes could lose updates, OAuth connection completion could become active before credentials were durably persisted, and API-key profile writes could leave orphan credential blobs after profile-index failure.

## Planned changes

- `apps/aigateway/src/aigateway/core/credential_blob/store.py`: add a credential-blob mutation primitive with optimistic retry/conflict signaling.
- `apps/aigateway/src/aigateway/core/profile_index.py`: route profile-index `upsert` and `remove` through the mutation primitive instead of read/modify/write.
- `apps/aigateway/src/aigateway/main.py`: map profile-index mutation conflicts to a retryable sanitized response.
- `apps/aigateway/src/aigateway/routes/auth.py`: persist OAuth connection credentials before activation, add activation-conflict cleanup, and add API-key profile-index failure compensation.
- `apps/aigateway/src/aigateway/routes/oauth_connections.py`: share sanitized credential persistence behavior for API-key connection writes.
- `apps/aigateway/src/aigateway/routes/credential_persistence.py`: centralize sanitized credential-persistence failure handling.
- `apps/aigateway/tests/**`: add concurrency, retry-exhaustion, and injected-failure coverage for the protected state transitions.

## Test plan

- Cover concurrent profile-index updates across isolated store instances and assert no lost profile metadata.
- Cover empty-index create races, retry behavior, retry exhaustion, and concurrent remove/upsert behavior.
- Inject OAuth connection credential persistence failure and assert the connection does not become active without credentials.
- Inject OAuth connection activation conflict after credential persistence and assert connection-scoped credentials are deleted as compensation.
- Inject profile API-key index failure for new and existing profiles and assert the new blob is deleted or the prior blob is restored.
- Assert retryable profile-index conflicts return sanitized `503` responses instead of raw internal errors.

## Acceptance

- Profile metadata writes are protected by a database-backed optimistic mutation path suitable for multi-worker deployments using the existing JSON index.
- OAuth connection completion cannot leave an active connection without usable credentials.
- Profile API-key writes include tested cleanup/restore compensation when profile-index persistence fails.
- Tests cover concurrent isolated-store updates and injected write failures.
- No schema or model change is part of this unit; no migration is required.

## Test-Contract Exception

- Rule-5 Confidence-Gate approval granted by the requester on 2026-07-09 for the single prior-test behavior rewrite in `apps/aigateway/tests/unit/test_auth_routes.py`.
- The rewritten test is `test_connection_completion_persists_credentials_after_store_complete` renamed to `test_connection_completion_deletes_credentials_when_activation_conflicts`.
- The old assertion encoded the prior buggy ordering. The new assertion is stricter and verifies the fixed A2 behavior: credentials are persisted before activation, and activation conflict triggers credential deletion compensation.
- The remaining modified test files add coverage or update test doubles to satisfy the expanded credential-store port; they do not weaken prior assertions.
- Additional approval granted on 2026-07-09 for tightening browser/loopback OAuth callback error-page assertions. The prior contract required provider exception text to be HTML-escaped; the new contract is stricter and requires provider exception text not to be rendered at all, even escaped.

## Architecture Notes

- The mutation behavior is exposed on the credential-blob port and consumed unconditionally by `ProfileIndexStore`, preserving the repository boundary and avoiding implementation-type checks.
- The mutation behavior now supports `None` as a CAS delete/no-op result, so compensation can restore or delete a credential only when the slot still contains this request's write.
- Profile metadata is stored in account-scoped index rows (`account:<account_id>`) instead of one gateway-global row; legacy `default` row data is read lazily so existing profiles remain visible.
- The credential blob model shape is unchanged, and model files were not modified.
- Cross-store profile/OAuth operations use explicit compensation rather than pretending profile metadata and credential writes are a single database transaction.

## Hardening Follow-Up

- OAuth connection activation failures after credential persistence now delete connection-scoped credentials, mark the connection `error`, and return a sanitized retryable response for non-`IntegrityError` failures.
- OAuth browser and loopback callback generic failures now render a static sanitized message instead of provider exception text.
- Added tests for OAuth activation non-integrity failure cleanup, OAuth delete-compensation double-fault logging, API-key compensation double-fault logging, and sanitized browser/loopback callback error pages.
- Re-OAuth over an existing API-key profile now restores the prior API-key blob when profile-index completion fails.
- API-key compensation now preserves a concurrent slot write instead of blindly restoring/deleting over it.
- Added tests for nullable credential mutation delete/no-op behavior, API-key CAS compensation, API-key restore double-fault logging, and final-attempt retry exhaustion without extra backoff.
- Added tests for account-scoped profile-index writes, cross-account non-contention, and lazy legacy `default` row preservation.

## Outcome

- **Actual files:** planned AIGateway source and test files plus this work ledger.
- **Commits:** committed locally for SF-328.
- **Gates:** affected unit set passed (`224 passed`); canonical AIGateway gate passed with the approved append-only exception applied: `ALL GATES GREEN`.
- **Deviations:** no schema/model migration was added; the fix stays within the existing credential/profile storage shape.
