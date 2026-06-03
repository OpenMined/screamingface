# scoreboard

Helm chart for the ScreamingFace benchmark scoreboard.

Install the demo database chart first, then install this app chart:

```bash
helm upgrade --install scoreboard-db apps/scoreboard/charts/db \
  --namespace scoreboard \
  --create-namespace \
  --wait \
  --values apps/scoreboard/charts/db-scoreboard.values.yaml

helm upgrade --install scoreboard apps/scoreboard/charts/scoreboard \
  --namespace scoreboard \
  --wait
```

The app chart is database-agnostic. It consumes `SCOREBOARD_DATABASE_URL` from `database.existingSecret`, which defaults to the `scoreboard-db` Secret created by `charts/db`.

## Benchmarks

The post-install/post-upgrade seed Job runs `python -m scoreboard.seed` and passes `.Values.seedBenchmarks.benchmarks` as JSON. Re-running the Job is safe because benchmark registration is idempotent.

Disable seeding with:

```bash
helm upgrade --install scoreboard apps/scoreboard/charts/scoreboard \
  --namespace scoreboard \
  --set seedBenchmarks.enabled=false
```

## CORS

Production CORS should include the portal origin:

```yaml
cors:
  origins:
    - https://screamingface.ai
```

## Production

`values-prod.yaml` expects externally managed Postgres through a Secret with a `database-url` key, three app replicas, nginx ingress, TLS, and NetworkPolicy enabled:

```bash
helm template scoreboard apps/scoreboard/charts/scoreboard \
  --values apps/scoreboard/charts/scoreboard/values-prod.yaml
```
