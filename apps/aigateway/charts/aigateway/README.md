# aigateway

Helm chart for ScreamingFace AI Gateway.

Install the demo database chart first, then install this app chart:

```bash
helm install aigw-db apps/aigateway/charts/db \
  --namespace aigw \
  --create-namespace \
  --wait \
  --values apps/aigateway/charts/db-aigateway.values.yaml
helm install aigw apps/aigateway/charts/aigateway --namespace aigw --wait
```

The app chart is database-agnostic. It consumes `AIGATEWAY_DATABASE_URL` from `database.existingSecret`, which defaults to the `aigw-db` Secret created by `charts/db`.

## Public URL

Set `publicUrl` to the externally reachable gateway origin when using hosted OAuth callbacks:

```bash
helm upgrade --install aigw apps/aigateway/charts/aigateway \
  --namespace aigw \
  --set publicUrl=https://aigateway.example.com \
  --set "ingress.hosts[0].host=aigateway.example.com" \
  --set "ingress.hosts[0].paths[0].path=/" \
  --set "ingress.hosts[0].paths[0].pathType=Prefix"
```

Quote indexed `--set` keys in shells such as zsh. If you override a list item, set the full `host` and `paths` structure.

For temporary k3s smoke tests without real DNS, a host such as `aigateway.40.76.107.241.nip.io` resolves to `40.76.107.241` and works with host-based Ingress rules.

## The admin surface

`/v1/admin` — the tenant and API-key management the `aigateway-ui` console drives — is gated on an
allowlist of email addresses, checked against the `X-User-Email` the mesh injects. It is a **second**
gate: header identity establishes *who* a caller is, `config.adminEmails` establishes whether they
may administer.

**It ships empty, and empty is not a no-op.** With no entries the admin API answers `503 Admin API
is disabled` to everyone, so a stock install has the surface switched off rather than open. Turn it
on deliberately:

```bash
helm upgrade --install aigw apps/aigateway/charts/aigateway \
  --namespace aigw \
  --set-string 'config.adminEmails[0]=you@example.com' \
  --set-string 'config.adminEmails[1]=colleague@example.com'
```

Matching is case-insensitive. The list is *not* stored in a Secret — these are identities, not
credentials, and they appear in the ConfigMap by design so that who may administer is auditable
from the rendered manifest.

## Who may connect

`networkPolicy.clientPodNames` defaults to `url4-cloud`, `url4-runner` and `aigateway-ui`. In
`cloudflare_headers` mode that list is not hardening — it **is** the authentication boundary, which
is why the template refuses to render an ingress rule with no peers rather than emitting one that
admits everything.

`aigateway-ui` is the admin console. It is a Backend-for-Frontend, so it is the console's *Pod* that
connects here, not a browser. If you override this list and drop the entry, the console does not
degrade — it is denied at the CNI, and the symptom is a connect timeout in the console with nothing
in this gateway's logs, because the packet never arrives. Drop it only if you do not deploy the
console.

## Production

`values-prod.yaml` expects externally managed Secrets and production ingress settings:

```bash
helm template apps/aigateway/charts/aigateway \
  --values apps/aigateway/charts/aigateway/values-prod.yaml
```

Production database infrastructure should be managed separately, for example CloudNativePG or managed Postgres.

Published releases include the app chart in GHCR:

```bash
helm install aigw oci://ghcr.io/openmined/screamingface/charts/aigateway \
  --version 0.2.0 \
  --namespace aigw
```
