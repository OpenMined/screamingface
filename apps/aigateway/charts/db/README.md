# postgres

Small single-instance PostgreSQL chart for development and demos.

## Install

```bash
helm install my-db ./charts/db --namespace my-namespace --create-namespace
```

## Resources

- `Secret/<release-name>`: `username`, `password`, `database`, and `database-url`.
- `Service/<release-name>`: cluster-internal Postgres service on port `5432`.
- `PersistentVolumeClaim/<release-name>-data`: data volume.
- `Deployment/<release-name>`: single `postgres:16-alpine` pod.

## Notes

- This is demo infrastructure only: no HA, no backups, no PITR, and no automated major-version upgrade policy.
- The generated password is URL-safe and is preserved on upgrade when Helm can read the existing Secret from the cluster.
- If `auth.password` is set manually, use a URL-safe value because the chart also writes a database URL Secret.
- Postgres is cluster-internal only. Do not expose it through Ingress or a public LoadBalancer.
- Deleting the PVC deletes the database.
