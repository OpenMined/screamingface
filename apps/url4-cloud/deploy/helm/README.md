# url4-cloud

Helm chart for **url4-cloud** — the stateless REST + WebSocket control plane (spec §9). It renders
the App **Deployment · Service · Ingress · ConfigMap · Secret**, the namespace **RBAC bootstrap**
(**ServiceAccount · Role · RoleBinding**) that lets the App schedule Runner Jobs in its own
namespace, and a documented **Runner Job template** ConfigMap.

## Install

NATS (JetStream) is the telemetry bus and is declared as a chart dependency (Chart.yaml,
condition `nats.enabled`, default off). Because Helm resolves declared dependencies before
evaluating their condition, **`helm dependency build` is a prerequisite for `helm template` /
`install` in both modes** — it vendors the subchart `.tgz` once (network to `nats-io/k8s`):

```bash
helm dependency build apps/url4-cloud/deploy/helm

# Reuse an existing in-cluster NATS (JetStream) — leave the subchart inert, point the App at it:
helm upgrade --install url4 apps/url4-cloud/deploy/helm \
  --namespace url4-cloud --create-namespace \
  --set config.natsUrl=nats://my-nats:4222

# Or deploy the bundled NATS (JetStream enabled) alongside the App:
helm upgrade --install url4 apps/url4-cloud/deploy/helm \
  --namespace url4-cloud --create-namespace \
  --set nats.enabled=true
```

`helm lint` needs no vendored dependency (it only warns), so it runs without the build step.
Quote indexed `--set` keys in zsh. To override the ingress host, set the full `host`/`paths`
structure (see `values.yaml`).

## RBAC (spec §9)

The App is stateless — it holds no run state and re-derives each Job's identity from the token's
topic. To do that it needs, **in its own namespace only**:

| API group | Resource   | Verbs                              |
|-----------|------------|------------------------------------|
| `batch`   | `jobs`     | create · get · list · watch · delete |
| `""`      | `pods`     | get · list                         |
| `""`      | `pods/log` | get                                |

The `RoleBinding` targets the App's `ServiceAccount` (the Deployment's subject). These are exactly
the calls `url4_cloud.jobs.k8s.K8sJobRunner` makes, and the Role covers the labels the App stamps on
the Jobs it creates (`url4_cloud.jobs.port.RUNNER_LABELS`).

## Runner Job template

`templates/job-runner.yaml` renders a **ConfigMap** (`<release>-url4-cloud-runner-job-template`),
not a live Job. The App builds the real per-request Job in code
(`K8sJobRunner._manifest`) with a deterministic name `url4-<hash(topic)>` — the stateless single-use
`409` guard. The ConfigMap is the operator reference to that shape (run-once `backoffLimit:0` /
`restartPolicy:Never`, 16 h `activeDeadlineSeconds`, the `app.kubernetes.io/*` labels).

## Labels

All resources carry the k8s **recommended labels** (`app.kubernetes.io/name·instance·version·
managed-by·part-of·component`) via `templates/_helpers.tpl` (docs/protocol.md §9).

## OCI image annotations

The container image should carry the OCI **`org.opencontainers.image.*`** annotations
(opencontainers/image-spec) — set as `LABEL`s at build time, e.g.:

```dockerfile
LABEL org.opencontainers.image.title="url4-cloud" \
      org.opencontainers.image.description="ScreamingFace url4-cloud control plane + runner" \
      org.opencontainers.image.source="https://github.com/openmined/screamingface" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.vendor="OpenMined"
```

`image.repository` defaults to `ghcr.io/openmined/screamingface-url4-cloud`; the tag defaults to the
chart `appVersion`.

## Lint / render

```bash
helm lint apps/url4-cloud/deploy/helm
helm template apps/url4-cloud/deploy/helm
```
