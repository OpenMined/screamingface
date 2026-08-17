# Cloudflare Access, URL4 Cloud, and AI Gateway authentication topology

Date: 2026-08-01
Scope: local first-party repository sources, reconciled with the separately reviewed first-party
Pulse tenant documentation for the deployed hostname and service overlay.

## Primary sources reviewed

- [Pulse ScreamingFace overview](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/)
- [Deployed architecture](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/architecture/)
- [Credentials and identity](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/credentials/)
- [Evidence and current status](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/evidence-and-status/)
- [Deployed URL4 Cloud](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/apps/url4-cloud/)
- [Deployed AI Gateway](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/apps/aigateway/)
- [Deployment decisions](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/decisions/)
- [Infrastructure change workflow](https://pulse.dev.screamingface.ai/docs/tenants/screamingface/change-workflow/)
- [Pulse gateway identity flow](https://pulse.dev.screamingface.ai/docs/products/gateway-identity-flow/)
- [Cloudflare Access HTTP applications](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/)
- [Cloudflare Managed OAuth](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/)

## Conclusion

The hosted topology is:

```text
ScreamingFace Python Client
  │ Cf-Access-Token: <short-lived Access application token>
  ▼
Cloudflare Access at fusion.dev.screamingface.ai
  │ Cf-Access-Jwt-Assertion
  ▼
Envoy Gateway / URL4 HTTPRoute
  │ verifies issuer + Access application audience
  │ overwrites X-User-Email from the verified email claim
  ▼
URL4 Cloud control plane ── schedules URL4 Runner Job
  │ X-User-Email (never the Cloudflare Access token)
  ▼
internal AI Gateway at sf-aigw:9105
  │ resolves the account and its encrypted, per-account provider credential
  ▼
model provider
```

Therefore:

- The SDK authenticates to the Cloudflare-protected URL4 Cloud origin, not to AI Gateway.
- The SDK completes the browser login through Cloudflare's encrypted token-transfer endpoint. URL4
  Cloud and AI Gateway are not OAuth callback services.
- `AIGW_AUTH_MODE=cloudflare_headers` is the downstream AI Gateway identity mode. It is not an SDK
  login switch.
- The Access token terminates at the public edge. URL4 forwards only the verified email identity to
  AI Gateway.
- Provider credentials are per AI Gateway account and encrypted at rest. There is no shared
  provider or administrator key in the Python Client path.

## Public and internal origins

### URL4 Cloud is the public origin

The generic cloud values define the URL4 HTTPRoute hostname and turn on its Cloudflare Access
SecurityPolicy. Required install-time inputs include the Gateway parent, Access team domain, Access
application audience, NATS URL, and the internal AI Gateway Service URL
([URL4 cloud values](../../../../apps/url4-cloud/deploy/helm/values-cloud.yaml)).

The chart describes the mesh gateway as the cloud front door: Cloudflare Access authenticates the
caller, the gateway re-verifies the assertion and injects `X-User-Email`, and URL4 forwards that
identity to each run ([URL4 chart values](../../../../apps/url4-cloud/deploy/helm/values.yaml)).

The Pulse tenant documentation supplies the concrete deployed overlay:

- `fusion.dev.screamingface.ai` is the public URL4 Cloud origin;
- AI Gateway is private at `sf-aigw:9105`.

The Python Client should therefore point at `fusion.dev.screamingface.ai`. URL4—not the Client—calls
the private AI Gateway.

### AI Gateway remains internal

The AI Gateway production values set `authMode: cloudflare_headers`, disable its Ingress, and allow
only URL4 Cloud and URL4 Runner pods through its NetworkPolicy
([AI Gateway production values](../../../../apps/aigateway/charts/aigateway/values-prod.yaml)). The
base values make the service `ClusterIP` and warn that exposing an Ingress while trusting
`X-User-Email` would permit identity forgery
([AI Gateway values](../../../../apps/aigateway/charts/aigateway/values.yaml)).

## Where Cloudflare identity is established

Cloudflare Access performs the user-facing login at the edge. URL4's Envoy `SecurityPolicy` then
verifies the proxied `Cf-Access-Jwt-Assertion` (or browser `CF_Authorization` cookie) against the
configured team issuer and application audience. It maps the verified `email` claim to
`X-User-Email` ([SecurityPolicy](../../../../apps/url4-cloud/deploy/helm/templates/securitypolicy.yaml)).

The policy's important invariants are:

- `claimToHeaders` overwrites `X-User-Email`, so a forged client header does not survive;
- the audience check rejects tokens issued for another Access application;
- the Access team domain and application audience are required deployment inputs.

The repository does not provision the Access application or tunnel. It consumes their team-domain
and audience values for in-cluster verification.

## What the Python Client does

The SDK creates caller authentication automatically for its configured Engine origin; there is no
`auth="cloudflare"` argument ([Client construction](../../src/screamingface/client.py)). Explicit
`client.login()` is available, and the first protected HTTP request can start the same flow.

The flow is:

1. Probe the configured Engine and obtain the Access application audience from `cf-access-aud` or
   the `kid` on its login redirect.
2. Generate an ephemeral Curve25519 keypair in the Python process.
3. Print the Engine's `/cdn-cgi/access/cli` login URL and open it on desktop Python.
4. Let the user complete the configured Access identity-provider or email-OTP login in a browser.
5. Poll `login.cloudflareaccess.org/transfer/<ephemeral-public-key>`.
6. Decrypt the returned application token with the ephemeral private key.
7. Keep the token only in memory and apply it as `Cf-Access-Token` to REST requests and WebSocket
   handshakes ([caller authentication](../../src/screamingface/_authentication.py),
   [transport propagation](../../src/screamingface/_transport.py)).

The private key never leaves the Python process. The transfer payload is encrypted for that key,
and the peer key is supplied with the response. The SDK validates the token's `exp` and refreshes
by running login again before expiry. `logout()` clears it and opens the application logout URL in
the browser; `close()` only clears local process state.

In a local terminal the login URL is printed and the default browser is opened. In Jupyter or
Colab, the URL is printed for the user to click. Because the browser and kernel rendezvous through
the encrypted transfer endpoint, no localhost listener, pasted callback, dynamic client
registration, or loopback-client setting is required.

The current package implements only this Access flow. Cloudflare Managed OAuth could be considered
as a future standards-based migration using OAuth discovery and authorization code + PKCE; it is
not a second runtime mode today.

## What URL4 Cloud forwards

URL4 Cloud's caller-identity mapping is:

```text
X-User-Email  <->  URL4_CLOUD_IDENTITY_USER_EMAIL
```

The source contract says this is the caller information URL4 forwards and that it does not carry
the incoming authentication token into the app-to-gateway hop
([job environment contract](../../../../apps/url4-cloud/src/url4_cloud/job_env.py)). URL4 reads the
verified header and hands it to the scheduled runner
([run route](../../../../apps/url4-cloud/src/url4_cloud/rest/routes.py)). The runner applies that
identity to AI Gateway requests without inventing an `Authorization` header
([runner connector](../../../../apps/url4-cloud/src/url4_cloud/runner/connector.py)).

URL4 also proxies model-catalog and provider-connection operations to AI Gateway with the same
verified identity ([catalog adapter](../../../../apps/url4-cloud/src/url4_cloud/catalog/aigateway.py),
[connection adapter](../../../../apps/url4-cloud/src/url4_cloud/connections/aigateway.py)).

## What `AIGW_AUTH_MODE` means

AI Gateway has three separate modes:

- `cloudflare_headers`: trust `X-User-Email` only from declared networks;
- `jwt`: verify AI Gateway's own bearer token;
- `disabled`: use one anonymous account for loopback-only local development.

These are defined in AI Gateway settings
([auth mode contract](../../../../apps/aigateway/src/aigateway/config.py)). In
`cloudflare_headers` mode, AI Gateway checks the TCP peer before reading the header, rejects missing
identity, and resolves the account by normalized email
([auth dependency](../../../../apps/aigateway/src/aigateway/core/auth/middleware.py),
[identity mapping](../../../../apps/aigateway/src/aigateway/core/auth/cloudflare_identity.py)).

Disabling AI Gateway auth locally does not test Cloudflare login; it selects an anonymous local
account. Conversely, production `cloudflare_headers` mode does not perform browser login—it
consumes identity established at the URL4 edge.

## Provider credential flow

For the current OpenRouter API-key surface, the SDK sends the key only to its configured SF Engine
through `PUT /v1/connections/{provider}` ([SDK connections](../../src/screamingface/connections.py)).
URL4 holds it only long enough to call AI Gateway and does not expose it in its response
([URL4 connection route](../../../../apps/url4-cloud/src/url4_cloud/rest/connections.py)).

AI Gateway validates the key, associates it with the account resolved from `X-User-Email`, and
persists it encrypted for later model dispatch
([connection route](../../../../apps/aigateway/src/aigateway/routes/oauth_connections.py),
[credential store](../../../../apps/aigateway/src/aigateway/core/credential_blob/store.py)). The
Helm values explicitly reject a chart-level shared OpenRouter key because provider keys are
per-account credentials ([provider configuration](../../../../apps/aigateway/charts/aigateway/values.yaml)).

## Separate URL4 execution capability

URL4's `/token` endpoint mints a short-lived, topic-bound execution capability, and the SDK sends it
as `URL4-Capability` when starting a run
([URL4 token route](../../../../apps/url4-cloud/src/url4_cloud/rest/routes.py),
[SDK transport](../../src/screamingface/_transport.py)). This is separate from:

1. the Cloudflare Access token used to cross the public edge;
2. the verified `X-User-Email` propagated inside the cluster; and
3. the provider credential stored by AI Gateway.

## Infrastructure requirements

The infrastructure owner should configure:

1. A Cloudflare Access application on `fusion.dev.screamingface.ai` whose policy allows the intended
   users through email OTP or another configured identity provider.
2. A tunnel/routing path from that hostname to the cluster's identity-enforcing Gateway.
3. URL4 Cloud with the Access team domain and exact application audience, plus an internal AI
   Gateway base URL.
4. AI Gateway with `AIGW_AUTH_MODE=cloudflare_headers`, no public Ingress, and network access limited
   to URL4 control-plane and runner peers.
5. Per-account provider connection provisioning through URL4, with no SDK admin key or shared
   provider key.

No Managed OAuth, dynamic-client-registration, or loopback-client setting is required by the
currently implemented Client login flow.

## Suggested acceptance checks

- An unauthenticated request to `fusion.dev.screamingface.ai` redirects to Access and exposes the
  application audience.
- `client.login()` completes the browser login and both REST and WebSocket requests cross Access
  with `Cf-Access-Token`.
- The login works from a local terminal and a remote notebook without a localhost callback.
- A forged `X-User-Email` is overwritten by Envoy's verified claim.
- URL4 Runner requests to AI Gateway contain `X-User-Email` and no Cloudflare Access token.
- AI Gateway is unreachable through a public Ingress and rejects untrusted peers.
- Two Access users resolve to distinct AI Gateway accounts and cannot use each other's stored
  provider connection.
- A provider key can be connected through URL4, is never returned, and is encrypted at rest by AI
  Gateway.
