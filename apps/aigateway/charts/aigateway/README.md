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
