# OME-883 — Hosted provider connection-panel behaviour

## Decision

The existing shared Engine-origin classifier is the temporary policy seam. Loopback origins
(`localhost`, loopback IPs, and unspecified loopback-bound origins) retain BYOK controls. Every
other origin is hosted and renders provider availability without Connect, Disconnect, API-key,
OAuth, pending-flow, or cancellation controls.

The Engine's provider catalogue is authoritative for managed availability on hosted origins.
Every advertised hosted provider is presented as “Connected” and “Available via ScreamingFace”.
The row's connection status is caller-scoped BYOK state and is deliberately ignored on hosted
origins because it does not represent the operator-managed credential used for execution.

## Invariants

- Hosted classification is computed once by `_is_hosted_engine` and carried in panel state.
- Hosted rendering never installs a credential-mutating widget callback.
- Hosted rendering never exposes caller-scoped account labels or BYOK status.
- Local rendering and programmatic `Client.connect()` / `disconnect()` remain unchanged.
- Static HTML and interactive notebook rendering present the same hosted status language.

## Explicit limitation

This is a UI guard for the tester release, not a security boundary. Direct Engine connection
requests remain possible until an Engine-owned policy is introduced.
