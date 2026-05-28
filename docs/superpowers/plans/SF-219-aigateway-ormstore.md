# SF-219: AIGateway ORMStore

## Status

Implemented as the AIGateway storage replacement for the previous OS credential-store design.

## Scope

- Replace `apps/aigateway` OS credential storage with a Tortoise-backed `ORMStore`.
- Store credential blobs in `credential_blobs(service, account, value)`.
- Use SQLite by default for local development and Postgres via `AIGATEWAY_DATABASE_URL` for hosted deployments.
- Keep provider OAuth services/account naming stable as credential blob locators.
- Keep `apps/desktop` and `apps/server` credential behavior out of scope.

## Guardrail

`apps/aigateway` must not use OS keychain, Linux Secret Service/libsecret, Windows Credential Manager, or JSON-file credential-store shims for runtime credentials. Use `ORMStore` through Tortoise only.
