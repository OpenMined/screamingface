# Spec — rename the Engine app to `screamingface-engine`

- **Ticket:** `OME-876` · follow-up `OME-877`
- **Status:** approved 2026-08-18
- **Supersedes naming in:** `docs/spec/2026-07-21-url4-cloud.md` (that spec's design is unchanged;
  only the component's name changes)

## Problem

The Engine app lives at `apps/url4-cloud` with Python package `url4_cloud`. Three other places
already call it the ScreamingFace Engine: the product docs, the Linear landing label
(`screamingface-engine`), and the published image prefix (`screamingface-url4-cloud`). The repo
name is the outlier.

The name is also actively misleading. `url4-cloud` reads as a component of the url4 language.
It is not: `packages/url4` is the language, and this app is the runtime that executes it. The
README already states the intended identity — "the ScreamingFace Engine".

## Decision

Rename the repo-side identity to `screamingface-engine` at scope tier **T2**, using **Path A**.

### T2 — what identity means

**Changes:** app directory · Python package · distribution name · console scripts · Dockerfiles ·
Helm chart name and helper namespace · container image repositories · CI workflow names and
filters · release-please component · dependabot · CODEOWNERS · agent config · live documentation.

**Does not change:** the `URL4_CLOUD_*` environment prefix (the pydantic `Settings` prefix and the
7 per-run Job env names in `job_env.py`) · the NATS subject and stream prefix in `subjects.py` ·
the Kubernetes pod labels in `RUNNER_LABELS` · `URL4_RUNNER_CONFIG` · the public hostname
`url4.screamingface.ai` · `apps/aigateway`.

**Never changes:** `packages/url4`, the `url4` import, `url4.streaming`, the `URL4-Capability`
header, or url4 expression syntax. These belong to a different component.

### Path A — the chart is renamed, its rendered identity is pinned

`deploy/helm/templates/_helpers.tpl` derives **both** `app.kubernetes.io/name` and every object
name from `Chart.yaml`'s `name`:

```
{{- define "…​.name" -}}{{- default .Chart.Name .Values.nameOverride … -}}{{- end -}}
{{- define "…​.fullname" -}}{{- printf "%s-%s" .Release.Name (include "…​.name" .) … -}}{{- end -}}
```

That single value therefore controls three things that are **not** cosmetic:

1. **A Deployment selector.** `selectorLabels` is `app.kubernetes.io/name` + `instance`.
2. **An allowlist entry in another app.** `apps/aigateway`'s NetworkPolicy admits client Pods by
   `app.kubernetes.io/name`; its values list `url4-cloud` and `url4-runner`. Denial happens at the
   CNI and, per that file's own comment, "surfaces as a connect timeout … with NOTHING in this
   gateway's logs, because the packet never arrives."
3. **The key that preserves the JWT signing secret.** `templates/secret.yaml` does
   `lookup "v1" "Secret" .Release.Namespace $secretName` specifically so live capability tokens
   survive upgrades — and `$secretName` is `fullname`. If the name moves, the lookup misses, the
   template falls through to `randAlphaNum 64`, and every in-flight token is invalidated.

**Path A sets `nameOverride: "url4-cloud"`**, which pins the valve. The chart is renamed; nothing
downstream of it moves.

Verified by rendering the chart with `Chart.yaml` actually renamed:

| | before | Path A | Path B (no pin) |
| --- | --- | --- | --- |
| Deployment name | `url4-cloud-url4-cloud` | unchanged | `url4-cloud-screamingface-engine` |
| `spec.selector` | `name=url4-cloud` | unchanged | `name=screamingface-engine` |
| `helm.sh/chart` | `url4-cloud-0.1.0` | `screamingface-engine-0.1.0` | `screamingface-engine-0.1.0` |

Path A's only rendered delta is a descriptive label. `values-cloud.yaml` sets none of
`nameOverride`, `fullnameOverride`, `auth.jwtSecret` or `auth.existingSecret`, so the cloud
deployment runs the defaults and the Secret hazard above would be live under Path B.

### Consequences accepted

- Deploying is an ordinary rolling update: no downtime, no in-flight runs killed, no change to
  `apps/aigateway`, live capability tokens preserved.
- `kubectl` continues to show `app.kubernetes.io/name: url4-cloud`. One line in `values.yaml`
  exists solely to state that the label lags the name deliberately, naming `OME-877`.
- New images carry a `URL4_CLOUD_`-prefixed config surface under a `screamingface-engine` name.

### Rejected alternatives

- **T1 (code identity only)** — leaves the chart, images and release component on the old name,
  so the visible deployed surface keeps contradicting the product. Too little for the churn.
- **T3/T4 (env prefix, NATS prefix)** — each is a breaking runtime contract on a live cluster.
  T4 additionally orphans every existing `url4-cloud_*` stream, because `owns_stream()` gates the
  reclamation sweep and would stop recognising them, leaving each holding its `max_bytes`
  reservation. Deferred to `OME-877` with a compatibility window.
- **Path B (rename the pod label now)** — replaces all 12 objects, requires a coordinated change
  in `apps/aigateway`'s chart, and regenerates the JWT signing secret. Deferred to `OME-877` as a
  three-phase, zero-downtime migration.

## Contracts unaffected

Because T2 stops short of the runtime surface, every one of these is byte-identical before and
after: the CloudEvents wire protocol · the `URL4-Capability` header · the four-step run handshake ·
the NATS subject and stream names · the Job env contract · the REST and WebSocket paths · the
`screamingface.<type>.v1` event schema strings · `_MANAGED_LABEL = "screamingface"`.

## Release identity

Version `1.3.0` carries forward, so the next tag is `screamingface-engine-v1.4.0`. The old
`url4-cloud-v*` tags remain as history. Images cut over cleanly: only `screamingface-engine` and
`screamingface-engine-benchmark` are published from this release onward; the old repositories stay
frozen at `1.3.0`, retained and not deleted.

The `url4-cloud` and `url4-cloud-runner` console scripts remain resolvable for one release. The
cluster is live, and during a rolling upgrade an old App pod schedules the new image with the old
command — the image reference comes from a ConfigMap while the command comes from Python, so the
two change at different moments.

## Out of scope

`docs/work/**`, `docs/tasks/**` and `CHANGELOG.md` are historical record and keep the old name
verbatim; rewriting them would falsify the ledger.
