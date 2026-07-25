# Running AIGateway behind Cloudflare Access

Cloudflare Access enforces the admission policy (OTP/PIN, or your IdP) at the edge. Users it
admits reach AIGateway with **no registration and no `/v1/auth/login`** — their account is
provisioned just-in-time from the identity Cloudflare asserts.

## ⚠️ The precondition that makes this safe

**The origin must be unreachable except through Cloudflare.**

`Cf-Access-Jwt-Assertion` is an ordinary HTTP header. If anything can reach AIGateway
off-path, it can set that header to any identity it likes. Enabling this feature on a directly
reachable origin is *worse* than no authentication, because the gateway will trust a forged
identity and attribute usage to a real user.

Acceptable ingress:

- a `cloudflared` tunnel to a `ClusterIP`-only Service (what this repo's kind setup does), or
- the Cloudflare proxy with Authenticated Origin Pulls (mTLS) enforced at the origin.

AIGateway still verifies every assertion itself — signature, `iss`, `aud`, `exp` — against
Cloudflare's published keys. That second layer is deliberate: it holds even if the ingress
story is later weakened. It is defence in depth, **not** a substitute for the above.

## 1. Create the Access application

In the Zero Trust dashboard: **Access → Applications → Add an application → Self-hosted**.

- Set the application domain to the hostname the gateway is served on.
- Add your policy (email OTP, IdP group, whatever admits the right people).
- Copy the **Application Audience (AUD) tag** from the application's Overview tab.
- Note your **team domain** — `<team>.cloudflareaccess.com`.

Both values are **non-secret**. The AUD only names which application an assertion is scoped
to; it grants nothing. They belong in chart values, not in a Secret.

## 2. Add a Service Auth policy for machine clients

Programmatic clients cannot complete an interactive login. Create a **service token**
(Access → Service Auth → Service Tokens), then add a policy to the application with:

- Action: **Service Auth** — with any other action Access redirects to an IdP login and
  ignores the token pair.
- Include: the service token you created.

The client then sends `CF-Access-Client-Id` and `CF-Access-Client-Secret`.

## 3. Configure the gateway

```yaml
config:
  authEnabled: true          # required — the gateway refuses to start otherwise
  cfAccess:
    enabled: true
    teamDomain: myteam.cloudflareaccess.com   # bare hostname, no scheme or path
    aud: <the AUD tag>
    adminEmails:
      - you@example.com
```

`adminEmails` grants `is_admin` at provisioning time. Cloudflare policy decides who can
**reach** the gateway; this decides who holds **authority inside** it. Keep them distinct.

Misconfigurations are startup errors, not runtime surprises: `cfAccess.enabled` with
`authEnabled: false` refuses to boot (it would make every caller anonymous), as does a missing
team domain or AUD, or a team domain carrying a scheme, port or path (which could redirect
key retrieval to an attacker-controlled host).

## 4. Client usage

Clients satisfy **two independent planes** — the edge (Cloudflare) and the app (AIGateway).

| Client | Edge credential | App credential |
|---|---|---|
| Browser | `CF_Authorization` cookie (automatic) | the same cookie, or the injected header |
| Human CLI | `cf-access-token: <jwt>` | `Authorization: Bearer <same jwt>` |
| Machine/SDK | `CF-Access-Client-Id` + `-Secret` | `Authorization: Bearer <same jwt>` |

Get a human CLI token with:

```sh
cloudflared access login https://<your-gateway-host>
cloudflared access token -app=https://<your-gateway-host>
```

> `cloudflared access login` starts a local listener the browser hands the token back to.
> Do **not** wrap it in `timeout` — the browser reports success while the token silently goes
> nowhere.

Note the two-header requirement for the CLI path: the edge does **not** accept the JWT in
`Authorization` (you get a 302 to login and never reach the origin), and AIGateway reads
`Authorization`, not `cf-access-token`. Send the same JWT in both.

## Identity mapping

| Access path | `accounts.external_subject` | `email` |
|---|---|---|
| IdP login | JWT `sub` (stable Access user UUID) | JWT `email` |
| Service token | JWT `common_name` (client ID) | none |

Accounts are keyed on `(external_idp, external_subject)`, **never** on email — email is
mutable at the IdP and can be reassigned to a different person. A user who changes their
email keeps their account; a new person given an old address gets a new one.

Federated accounts have a `NULL` `password_hash` and can never authenticate via
`/v1/auth/login`.

## Per-user attribution for machine clients

A service token identifies the **token**, not a person, so a fleet sharing one token collapses
onto a single account. Gateway-issued API keys (OME-592) restore per-user attribution: mint a
key once via the browser/CLI path, then send the service token to satisfy the edge *and*
`Authorization: Bearer aigw_...` to identify the human to the gateway.

## Troubleshooting

- **401 "Missing bearer token"** — no credential reached the gateway. Check the header is
  actually being forwarded (`cloudflared` logs) and not stripped by a proxy in between.
- **401 `cf_access_denied`** — the assertion failed verification. The gateway log carries the
  precise reason (wrong `aud`, unknown `kid`, expired); the response deliberately does not, so
  it cannot describe your Access configuration to an unauthenticated caller.
- **302 to a login page** — the request never reached the origin; that is Cloudflare, not
  AIGateway. For service tokens, check the policy action is **Service Auth**.
- **Everything 401s right after a deploy** — confirm the image actually contains the feature
  (`kubectl exec deploy/aigateway -- ls .../core/auth/cf_access/`) before debugging auth logic.
