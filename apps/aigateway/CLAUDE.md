# AIGateway Guardrails

- AIGateway runtime credential storage uses ORMStore through Tortoise (`credential_blobs`): SQLite locally, Postgres in hosted/prod. Do not add OS keychain/libsecret/Secret Service/Credential Manager usage under `apps/aigateway`.
