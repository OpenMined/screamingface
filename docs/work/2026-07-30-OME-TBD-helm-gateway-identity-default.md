---
ticket: OME-TBD
stack: repo
status: in_progress
started: 2026-07-30
finished:
---

# OME-TBD — Make gateway-identity the default cloud deployment shape

## Intent

Third unit after the url4-cloud and aigateway code halves. Those made identity FLOW; this makes the
charts deploy the topology that identity flow requires, as the default for cloud installs.

Owner decisions (2026-07-30): change both charts; aigateway becomes internal-only (no public
Ingress); url4-cloud's edge defaults to the Gateway API (Envoy) rather than the traefik Ingress.

The load-bearing point: trusting `X-User-Email` is only sound while aigateway cannot be reached
except through Envoy and the Runner Pods. Today's chart contradicts that twice — aigateway publishes
a public traefik Ingress, and its NetworkPolicy FAILS OPEN (`templates/networkpolicy.yaml` omits
`from:` when `ingressCIDRs` is empty, while `values-prod.yaml` enables it with no CIDRs).

## Planned changes

`apps/aigateway/charts/aigateway/`
- `values.yaml` — `config.authMode: gateway_headers` (new, default); `ingress.enabled: false`;
  `networkPolicy` gains client selectors and defaults to enabled.
- `templates/_helpers.tpl` — `aigateway.authMode`, resolving the legacy `config.authEnabled`.
- `templates/configmap.yaml` — emit `AIGW_AUTH_MODE`; stop emitting `AIGATEWAY_AUTH_ENABLED`
  (emitting both can trip the app's own conflict check); add the two config guards.
- `templates/networkpolicy.yaml` — fail closed; allow only the declared clients; `fail` rather than
  render an allow-all.
- `values-prod.yaml` — same posture explicitly.

`apps/url4-cloud/deploy/helm/`
- `values.yaml` — `gateway.enabled: true` + `ingress.enabled: false`; document that the identity
  headers come from the Gateway and that nothing per-run is chart-configured.

## Test plan

- `helm template` / `helm lint` both charts clean at defaults and with the prod values.
- aigateway renders `AIGW_AUTH_MODE: gateway_headers` and no `AIGATEWAY_AUTH_ENABLED`.
- `authEnabled: false` still renders mode `disabled` (legacy path preserved).
- `authMode: gateway_headers` + `ingress.enabled: true` FAILS to render (the unsafe combination).
- `authEnabled: false` + `authMode: gateway_headers` FAILS to render.
- The NetworkPolicy always renders a non-empty `from:`; an empty client set FAILS rather than
  rendering an allow-all.
- The rendered policy pairs `namespaceSelector` AND `podSelector` in ONE `from` element per client
  (two elements would be OR and would admit the whole namespace).
- url4-cloud renders an HTTPRoute and no Ingress at defaults.

## Acceptance

- A default cloud install has: aigateway internal-only, header identity, a fail-closed policy that
  admits exactly the url4-cloud App and Runner Pods, and url4-cloud behind the Gateway.
- The dangerous combinations cannot be rendered at all.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned.
- **Commits:** not committed yet.
- **Gates:** `helm lint` clean on both charts (defaults and `values-prod.yaml`). Renders verified:
  - url4-cloud → ConfigMap, Deployment, **HTTPRoute**, Role, RoleBinding, Secret, Service,
    ServiceAccount — and **no Ingress**.
  - aigateway (prod) → ConfigMap, Deployment, Job, **NetworkPolicy**, Secret, Service,
    ServiceAccount — and **no Ingress**; `AIGW_AUTH_MODE: "gateway_headers"`, no
    `AIGATEWAY_AUTH_ENABLED` key.
  - Guards all fire: `gateway_headers`+Ingress FAILS; `authEnabled=false`+`gateway_headers` FAILS;
    empty peer set FAILS; `authEnabled=false`+`authMode=disabled` renders `disabled`;
    `jwt`+Ingress is allowed; a CIDR-only peer set renders.
- **Deviations:** none.

## Consequences a deployer must know

- **url4-cloud will not install without `gateway.parentRef.name`.** With `gateway.enabled` now the
  default, the values schema rejects an empty name (`/gateway/parentRef/name: minLength`). Loud, not
  silent — but it does mean a bare `helm install` fails until the Gateway is named.
- **`helm upgrade` on an existing install loses its traefik edge**, because the Ingress is no longer
  rendered. Pin the old shape with `ingress.enabled=true` + `gateway.enabled=false`.
- **aigateway's public host is gone.** Anything depending on `gateway.screamingface.ai` — the
  provider-credential UI, OAuth callbacks — is unreachable until it is routed through the mesh
  gateway. `publicUrl` is kept but only matters if the gateway is re-exposed.

## Still not done

- Nothing provisions credentials for a header-derived principal (carried over from the aigateway
  code unit) — a fresh caller still gets `404 profile_not_found`.
- **The NetworkPolicy is unverified against a real CNI.** A policy object only restricts traffic if
  the cluster's CNI enforces NetworkPolicy; several do not. The acceptance test is: from a Pod in
  another namespace, `curl -H 'X-User-Email: …' http://<aigw-svc>:9105/v1/chat/completions` must
  TIME OUT. If it answers, `gateway_headers` is not safe in that cluster regardless of this chart.
- The mesh gateway itself (the Envoy Gateway/GatewayClass, its listeners, and the identity filter
  that injects the headers) is cluster infrastructure neither chart installs.
