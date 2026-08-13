---
ticket: none filed — investigation of OME-806
stack: screamingface
status: done
started: 2026-08-13
finished: 2026-08-13
---

# Verify the WebSocket against the same roots as HTTP

## Intent

Follow-up to `2026-08-13-websocket-disconnected-drops`, and the unit that unit's
observability was built to make possible. The diagnostic half was deployed to `fusion.dev`
and the reporting user retried; the error named a cause nobody had hypothesised:

```
websocket_disconnected after 0.0s (SSLCertVerificationError)
```

`httpx` and `websockets` resolve certificate authorities differently, so the Client could
mint its capability over HTTPS and then fail to open a WebSocket to the same host.

## Planned changes

- `packages/screamingface/src/screamingface/_engine/transport.py` — `_websocket_ssl_context`,
  built once per transport beside the `httpx` client it must agree with, passed to both
  `connect()` calls.
- `packages/screamingface/tests/test_transport_tls_trust.py` — new, self-contained.
- `docs/spec/2026-08-13-websocket-disconnected-drops.md` — record mechanism T in the catalog
  the spec already keeps.

## Test plan

Failing first:

- The WebSocket's trust store equals the HTTP half's, certificate for certificate.
- That store is non-empty — the failure guarded against is "trusts nothing", not "trusts the
  wrong roots".
- A plain-HTTP Engine is given no context at all, because `websockets` refuses one on a
  `ws://` URI.

## Acceptance

- The three above fail against `main` and pass after the change.
- `run_gates.py screamingface` green.
- Local development over `http://127.0.0.1` is byte-identical to before.

## Outcome

- **Actual files:** as planned.
- **Gates:** `screamingface` — ALL GATES GREEN.
- **Evidence for the diagnosis:**
  - Client: `websocket_disconnected after 0.0s (SSLCertVerificationError)` — 0.0s places the
    failure in the TLS handshake, before any WebSocket protocol ran.
  - Engine: `POST /token 200 OK`, `/v1/models 200`, `/v1/benchmarks/draco/lite 200`,
    `/v1/connections 200`, and **no** `ws attach` or `ws rejected` line. HTTPS reached the
    host; the socket never did.
  - Source: `httpx._config.create_ssl_context` resolves `SSL_CERT_FILE` → `SSL_CERT_DIR` →
    `certifi`; `websockets` calls `ssl.create_default_context()`, which trusts OpenSSL's own
    paths. They agree while those variables are set and diverge in the default case.
- **Regression safety:** the HTTP capability mint runs BEFORE the WebSocket and now uses the
  same context, so any trust configuration that reaches the WebSocket has already satisfied
  it. There is no working configuration this changes. Verified that `http://` yields `None`,
  which is the library's own default for `ssl`, so the local path is unchanged; 45 tests
  driving the real transport against a local `http://` Engine pass.

## Deviations

- **No Linear issue and no `docs/tasks/` mirror**, by direction — exploratory pass. OME-806
  tracks the symptom; this does not close it (Envoy drain, edge idle cuts and Pod rollout
  remain open).
- **Branched from `main` after the parent PR merged**, rather than stacking on it, at the
  owner's request. The parent's ledger was left exactly as merged; this is its own unit.
- **`httpx.create_ssl_context()` rather than `certifi.where()`**, deliberately. Naming
  `certifi` would make the WebSocket ignore `SSL_CERT_FILE` that the HTTP half honours,
  recreating this same class of bug pointing the other way and breaking private-CA and
  TLS-inspecting-proxy setups. The invariant worth holding is that the two halves agree.
- **Two measurement errors made and corrected while investigating.** `get_ca_certs()`
  returning `[]` was first read as "the store is empty"; it does not enumerate
  capath-loaded certificates, and this machine's store verifies fine. A first attempt to
  simulate the user's environment set `SSL_CERT_FILE`, which `httpx` also honours, so it
  broke both halves rather than one. The mechanism was then established from both
  libraries' source instead.
- **Not reproduced on the reporting user's machine.** The mechanism is confirmed from
  source and the symptom matches exactly, but the environment was not available. A
  one-line check they can run is recorded in the PR.
