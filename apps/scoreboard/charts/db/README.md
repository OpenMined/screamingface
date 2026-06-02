# postgres

Single-instance PostgreSQL chart for scoreboard development and k3s demos.

Install with the scoreboard overlay:

```bash
helm upgrade --install scoreboard-db apps/scoreboard/charts/db \
  --namespace scoreboard \
  --create-namespace \
  --values apps/scoreboard/charts/db-scoreboard.values.yaml \
  --wait
```

The chart creates a Secret with `username`, `password`, `database`, and `database-url` keys. The scoreboard app chart consumes only `database-url`.

This chart is not production database infrastructure. It has no HA, backups, PITR, or managed upgrade policy. Use managed Postgres or a Postgres operator for production.
