# Gateway identity — how a caller reaches a provider

How the ScreamingFace cloud stack answers "who is calling?". Envoy verifies the caller once at the
edge and re-injects the answer as four plain headers; url4-cloud carries them to each run; aigateway
resolves them to an account and picks that principal's credentials.

Contract: <https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/>

| Header | Source claim | Meaning |
| --- | --- | --- |
| `X-Tenant` | platform route config | Always present. The namespace every subject is scoped under. |
| `X-User-Id` | JWT `sub` | A human. Stable across an address change, so it is the preferred key. |
| `X-User-Email` | JWT `email` | A human. Used as the key only when no `X-User-Id` was issued. |
| `X-Service-Id` | JWT `common_name` | Automation. Its presence *instead of* the user headers is what marks a caller as a service. |

Envoy **clears all four off the inbound request** before re-injecting them, so a client cannot forge
them. That guarantee is what everything below rests on.

The `.mmd` files are the source of truth; the committed `.svg`/`.png` beside them were rendered
with `@mermaid-js/mermaid-cli` (`mmdc -i <file>.mmd -o <file>.svg`, and again with `-s 2` for the
PNG). Re-render after editing one, and keep the inline block below in step with it.

> The SVGs contain `<foreignObject>`, which is what makes `<b>` and wrapped labels work. They render
> in a browser, on GitHub and in any docs site, but a plain SVG rasterizer drops the text — use the
> PNG there.

---

## 1 · Request flow

The one counter-intuitive part: this is **not** header pass-through. The App that receives the
headers and the Runner Pod that calls aigateway are different processes, and the outgoing request
does not exist yet when the headers arrive — so identity is captured, serialized onto the Job spec
as plain env, and re-rendered by the connector.

[`gateway-identity-flow.svg`](gateway-identity-flow.svg) · [PNG](gateway-identity-flow.png)

<!-- source: gateway-identity-flow.mmd -->
```mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant E as Envoy
    participant A as url4-cloud App
    participant J as Job spec (env)
    participant R as Runner Pod
    participant G as aigateway
    participant P as Provider

    C->>E: GET /?q=(url4 expression)<br/>+ the caller's own token
    Note over E,A: Envoy verifies the token, STRIPS any client-sent<br/>X-* identity header, then re-injects them from the<br/>verified claims. A client cannot forge these.
    E->>A: GET /?q=(url4 expression)<br/>X-Tenant + X-User-Id / X-User-Email<br/>(or X-Service-Id for automation)<br/>+ URL4-Capability, Authorization, X-Profile

    Note over A,J: job_env.identity_from_headers()<br/>canonical name → value · blank counts as absent<br/>nothing present → None, and nothing is forwarded
    A->>J: schedule(identity=…)<br/>identity_to_env() → URL4_CLOUD_IDENTITY_*<br/>PLAIN env: identity is not a credential

    Note over A,R: THIS is why it is not header forwarding —<br/>the outgoing aigateway request does not exist yet.<br/>The App and the Runner are different Pods.

    J->>R: Pod starts with that env
    Note over R,G: job_env.identity_from_env() →<br/>build_aigateway_world(identity_headers=…)<br/>held for the whole run, like token and profile

    R->>G: POST /v1/chat/completions<br/>identity headers, THEN Authorization + X-Profile<br/>(gateway-owned last, so no inbound value wins)

    Note over G,P: current_account() in gateway_headers mode:<br/>identity_from_headers() → GatewayIdentity →<br/>account_id = uuid5(ns, tenant ∥ kind ∥ subject)<br/>get-or-create the Account, honouring is_active
    G->>P: provider call with THAT principal's credential
    P-->>G: completion
    G-->>R: OpenAI-shaped response + usage
    R-->>E: run frames over NATS → WebSocket
    E-->>C: Result / Terminated

    Note over G,P: No identity headers in this mode → 401.<br/>Never anonymous: one shared principal<br/>would pool every caller's credentials.
```

**Why the account id is derived, not allocated.** `account_id = uuid5(namespace, tenant ∥ kind ∥
subject)` — the same caller maps to the same id in every process, with no lookup as the source of
truth. `credential_blobs` and `oauth_connections` are keyed on that id, so an unstable id would
orphan every credential the caller has stored. The namespace constant must never change. The email
is deliberately *not* part of the key, so changing address does not lose access.

## 2 · Deployment topology

Trusting `X-User-Email` is only sound while aigateway cannot be reached except by the peers that
carry verified identity. Two chart settings enforce that, and both must hold: no Ingress, and a
fail-closed NetworkPolicy.

[`gateway-identity-topology.svg`](gateway-identity-topology.svg) · [PNG](gateway-identity-topology.png)

<!-- source: gateway-identity-topology.mmd -->
```mermaid
flowchart TB
    NET([Internet])

    subgraph CL["Kubernetes cluster"]
        subgraph NSA["namespace: url4-cloud"]
            ENVOY["Envoy / Gateway API<br/><b>injects the identity headers</b><br/>chart: gateway.enabled=true"]
            APP["url4-cloud App<br/>app.kubernetes.io/name: url4-cloud<br/>HTTPRoute target"]
            JOB["Runner Jobs<br/>app.kubernetes.io/name: url4-runner<br/>one Pod per run"]
            AIGW["aigateway<br/>ClusterIP only, port 9105<br/><b>AIGW_AUTH_MODE=gateway_headers</b>"]
            DB[("Postgres<br/>credential_blobs<br/>AES-256-GCM")]
        end
        OTHER["any other Pod<br/>(other namespace or unlabelled)"]
    end

    PROV(["Provider APIs<br/>Anthropic · Google · OpenRouter"])

    NET -->|"HTTPS + caller token"| ENVOY
    ENVOY -->|"HTTPRoute<br/>+ X-Tenant / X-User-* / X-Service-Id"| APP
    APP -->|"schedules, passing identity<br/>as plain Job env"| JOB
    APP -->|"catalog: GET /v1/models<br/>NetworkPolicy: ALLOWED"| AIGW
    JOB -->|"POST /v1/chat/completions<br/>NetworkPolicy: ALLOWED"| AIGW
    OTHER -.->|"NetworkPolicy: DENIED<br/>fail-closed, non-empty from:"| AIGW
    NET -.->|"NO Ingress<br/>ingress.enabled=false"| AIGW
    AIGW -->|"egress open by design"| PROV
    AIGW --> DB

    classDef edge fill:#1e293b,stroke:#fb923c,stroke-width:2px,color:#e2e8f0
    classDef app fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#e2e8f0
    classDef gw fill:#083344,stroke:#22d3ee,stroke-width:3px,color:#e2e8f0
    classDef denied fill:#3f1d1d,stroke:#f87171,stroke-width:2px,color:#fecaca
    classDef ext fill:#1e293b,stroke:#94a3b8,stroke-width:1px,color:#e2e8f0

    class ENVOY edge
    class APP,JOB app
    class AIGW gw
    class OTHER denied
    class NET,PROV,DB ext

    linkStyle 5,6 stroke:#f87171,stroke-width:2px
```

**The NetworkPolicy detail that matters.** Each allowed client is ONE `from` element carrying both
its `namespaceSelector` and its `podSelector`. Selectors inside an element are ANDed; separate
elements are ORed — so splitting them would mean "any pod in that namespace OR that label anywhere",
i.e. the whole namespace. Two entries are needed because the App and the Runner Jobs share no label.

> **Unverified precondition.** A NetworkPolicy only restricts traffic if the cluster's CNI enforces
> it; some do not, and then the object is decoration. Since this policy *is* the authentication
> boundary in `gateway_headers` mode, test it: from a Pod in another namespace,
> `curl -H 'X-User-Email: …' http://<aigw-svc>:9105/v1/chat/completions` must **time out**. If it
> answers, header identity is not safe in that cluster.

## 3 · Auth modes and the refused configurations

[`gateway-identity-auth-modes.svg`](gateway-identity-auth-modes.svg) · [PNG](gateway-identity-auth-modes.png)

<!-- source: gateway-identity-auth-modes.mmd -->
```mermaid
flowchart TB
    REQ(["Request reaches aigateway"]) --> MODE{"AIGW_AUTH_MODE"}

    MODE -->|gateway_headers<br/><b>cloud default</b>| H1{"X-Tenant present<br/>AND one subject header?"}
    H1 -->|no| H401["<b>401</b><br/>never anonymous — a shared principal<br/>would pool every caller's credentials"]
    H1 -->|yes| HACC["GatewayIdentity → uuid5 account<br/>get-or-create, honours is_active"]
    HACC --> OK(["credential lookup for<br/>THAT principal"])

    MODE -->|jwt| J1{"Valid bearer token<br/>for an active Account?"}
    J1 -->|no| J401["<b>401</b>"]
    J1 -->|yes| OK

    MODE -->|disabled<br/><b>local only</b>| D1["anonymous account<br/>+ loopback-only middleware<br/>(client IP AND Host must be loopback)"]
    D1 --> OK

    subgraph REFUSED["Configurations the Helm chart REFUSES to render"]
        R1["authMode=gateway_headers<br/>+ ingress.enabled=true<br/><br/>a direct route in means anyone<br/>can set X-User-Email"]
        R2["authEnabled=false<br/>+ authMode≠disabled<br/><br/>two settings disagreeing about<br/>the auth posture"]
        R3["networkPolicy.enabled=true<br/>with no peers declared<br/><br/>an ingress rule with no from:<br/>admits every source"]
    end

    classDef ok fill:#064e3b,stroke:#34d399,stroke-width:2px,color:#e2e8f0
    classDef bad fill:#3f1d1d,stroke:#f87171,stroke-width:2px,color:#fecaca
    classDef dec fill:#1e293b,stroke:#fb923c,stroke-width:2px,color:#e2e8f0
    classDef local fill:#083344,stroke:#22d3ee,stroke-width:2px,color:#e2e8f0

    class OK,HACC ok
    class H401,J401,R1,R2,R3 bad
    class MODE,H1,J1 dec
    class D1 local
```

`AIGATEWAY_AUTH_ENABLED` is the legacy spelling: `false` still means `disabled`, and the chart
resolves the pair so only `AIGW_AUTH_MODE` reaches the app.

## Local development

Nothing above is required locally. `url4-cloud serve --local` fuses the App and the runner in one
process, and aigateway runs in `disabled` mode (anonymous, loopback-only) — so a plain `curl` works
with no identity at all. To exercise the identity path locally, send the headers yourself; there is
no Envoy to strip them:

```sh
curl -H 'X-Tenant: openmined' -H 'X-User-Email: me@openmined.org' \
     -H 'URL4-Capability: <token>' 'http://127.0.0.1:8000/?q=...'
```

## Known gap

Nothing yet provisions credentials for a header-derived principal. Each principal gets its own
credential namespace, so a caller with no configured profile reaches aigateway, authenticates, and
then gets `404 profile_not_found` — auth succeeds, the credential lookup does not.
