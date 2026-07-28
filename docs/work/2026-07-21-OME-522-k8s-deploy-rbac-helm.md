---
ticket: OME-522
stack: url4-cloud
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-522 — k8s Deployment/Service/Ingress + RBAC bootstrap + Helm chart (+ NATS)

## Intent
Ship the deploy surface for the stateless url4-cloud App (spec §9): a Helm chart under
`apps/url4-cloud/deploy/helm` that renders the App **Deployment + Service + Ingress + ConfigMap +
Secret**, a **namespace-scoped RBAC bootstrap** (ServiceAccount + Role granting `batch/jobs`
`[create,get,list,watch,delete]` and `pods` `[get,list]` + `pods/log` + RoleBinding to the App's
ServiceAccount) so the stateless App can schedule Runner Jobs **only in its own namespace**, a
**Runner Job template** (documented ConfigMap mirroring `K8sJobRunner._manifest`), the **NATS**
chart dependency, k8s **recommended labels** via `_helpers.tpl`, and a note of the OCI
`org.opencontainers.image.*` annotations the image should carry. Clones the aigateway/scoreboard
`charts/<app>` Helm pattern.

## Planned changes
- `apps/url4-cloud/deploy/helm/Chart.yaml` (+ NATS dependency, condition-gated)
- `apps/url4-cloud/deploy/helm/values.yaml`
- `apps/url4-cloud/deploy/helm/.helmignore`
- `apps/url4-cloud/deploy/helm/README.md`
- `apps/url4-cloud/deploy/helm/templates/_helpers.tpl` (app.kubernetes.io/* recommended labels)
- `apps/url4-cloud/deploy/helm/templates/{deployment,service,ingress,configmap,secret,serviceaccount,role,rolebinding}.yaml`
- `apps/url4-cloud/deploy/helm/templates/job-runner.yaml` (documented Runner-Job-template ConfigMap)
- `apps/url4-cloud/deploy/helm/templates/NOTES.txt`

## Test plan
- Infra unit — no Python added, so `run_gates.py url4-cloud` must stay GREEN (append-only + full suite).
- `helm lint apps/url4-cloud/deploy/helm` clean.
- `helm template` renders all resources; RBAC verbs match spec §9; env keys match `Settings`
  (`URL4_CLOUD_*`) and `K8sJobRunner._env`; SA wired into the Deployment and bound by the Role.

## Acceptance
- Chart lints clean and templates without error; RBAC grants exactly the spec §9 verbs on
  jobs/pods/pods-log; the RoleBinding targets the App's ServiceAccount; the runner template mirrors
  `K8sJobRunner._manifest` (run-once: `backoffLimit:0`/`restartPolicy:Never`, 16 h deadline);
  recommended labels present; OCI annotations documented; `run_gates.py url4-cloud` GREEN.

## Outcome
- **Actual files:** as planned. `apps/url4-cloud/deploy/helm/` — `Chart.yaml`, `values.yaml`,
  `.helmignore`, `README.md`; `templates/` — `_helpers.tpl`, `deployment.yaml`, `service.yaml`,
  `ingress.yaml`, `configmap.yaml`, `secret.yaml`, `serviceaccount.yaml`, `role.yaml`,
  `rolebinding.yaml`, `job-runner.yaml` (documented Runner-Job-template ConfigMap), `NOTES.txt`.
- **Commits:** see the OME-522 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud` ALL GREEN (append-only · ruff check · ruff format · pyright ·
  pytest+cov ≥80). No Python added, so the suite is unchanged. `helm lint` rc=0 (one expected
  WARNING: nats subchart not vendored offline — the declared dependency is not fetched here).
  `helm template` verified rc=0 on a dep-stripped scratch copy — renders 9 resources (Deployment,
  Service, Ingress, ConfigMap×2, Secret, ServiceAccount, Role, RoleBinding); RBAC verbs =
  jobs[create,get,list,watch,delete]/pods[get,list]/pods-log[get]; RoleBinding→App ServiceAccount;
  runner template mirrors `K8sJobRunner._manifest` + `RUNNER_LABELS` exactly.
- **Deviations:** (1) The Runner Job template is a **ConfigMap** (the explicitly-allowed
  "documented configmap" form), not a live `Job` — the App builds the real per-request Job in code
  (`K8sJobRunner`), so a helm-managed Job would collide and be inert; the ConfigMap documents the
  exact shape for review. (2) NATS is declared as a condition-gated Chart.yaml dependency (default
  off); Helm resolves declared deps before conditions, so `helm dependency build` is a prerequisite
  for `helm template`/`install` in both modes (documented in README). `helm lint` needs no
  vendoring and is green. (3) OCI `org.opencontainers.image.*` annotations are documented in
  README as image build-time `LABEL`s (they belong on the image, not the k8s manifests).
