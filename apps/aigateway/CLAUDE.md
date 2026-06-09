# AIGateway Guardrails

- AIGateway runtime credential storage uses ORMStore through Tortoise (`credential_blobs`): SQLite locally, Postgres in hosted/prod. Do not add OS keychain/libsecret/Secret Service/Credential Manager usage under `apps/aigateway`.
- Secrets at rest in `credential_blobs` are encrypted via `SecretStoreMixin` (default `LocalSecretStore`, AES-256-GCM). Never write plaintext secrets to `credential_blobs` — always go through `ORMStore`, which encrypts on write and decrypts on read. To add a provider (KMS/Vault/HSM), implement the async `SecretStoreMixin` port and register it in `core/secrets/factory.py::build_secret_store`; do not edit `ORMStore` or call sites.
- The only plaintext key material is the master key: env `AIGATEWAY_SECRET_KEY` (base64 of 32 bytes) in hosted/prod, or the `secret_master_keys` sibling table for local single-worker dev. Never store the master key in `credential_blobs` (it is what encrypts that table) and never log it.
