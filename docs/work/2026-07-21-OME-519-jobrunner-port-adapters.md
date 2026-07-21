---
ticket: OME-519
stack: url4-cloud
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-519 — JobRunner port + k8s/Docker adapters

## Intent
The url4-cloud App is stateless: run state is derived from the substrate, not held in memory
(spec §3). This unit adds the **JobRunner port** (`url4_cloud/jobs/`) that abstracts the job
substrate behind four operations — `schedule` / `stop` / `exists` / `status` — plus a
**deterministic job name** `url4-<hash(topic)>` that makes the single-use `409` check stateless
(a name collision on `create` *is* the "already ran" guard, spec §5). Two adapters implement it:
**K8sJobRunner** (batch/v1 Job, run-once — `backoffLimit:0`, `restartPolicy:Never`,
`activeDeadlineSeconds=deadline_s`) for prod (spec §9), and **DockerJobRunner** (docker SDK) for
the local/compose e2e (spec §11). The clients are injected so tests run headless against fakes —
no real cluster or daemon (INFRA rule).

## Planned changes
- `src/url4_cloud/jobs/__init__.py` — package exports.
- `src/url4_cloud/jobs/port.py` — `JobRunner` Protocol, `JobStatus` Literal, `job_name(topic)`,
  `JobAlreadyExists` domain error.
- `src/url4_cloud/jobs/k8s.py` — `K8sJobRunner` (injected `BatchV1Api`-shaped client).
- `src/url4_cloud/jobs/docker.py` — `DockerJobRunner` (injected docker-client-shaped client).
- `tests/unit/test_jobs_port.py` — deterministic name + port conformance.
- `tests/unit/test_jobs_k8s.py` — schedule spec / exists / stop / status-conditions against a fake.
- `tests/unit/test_jobs_docker.py` — schedule spec / exists / stop / status against a fake.
- `pyproject.toml` — add `docker` (the DockerJobRunner SDK), mirroring `kubernetes`.

## Test plan
- `job_name` is deterministic, DNS-1123-safe, `url4-`-prefixed, and topic-sensitive.
- Both adapters satisfy the `JobRunner` port (runtime-checkable isinstance).
- **schedule** builds the right-named spec: k8s Job with `backoffLimit:0`, `restartPolicy:Never`,
  `activeDeadlineSeconds=deadline_s`, and the topic/expression carried as env; docker container
  named identically with the same env. Returns the deterministic name.
- **schedule** on a name that already exists raises `JobAlreadyExists` (the stateless single-use
  guard) — k8s via the fake's `409`, docker via the exists pre-check.
- **exists** reflects a scheduled job and is `False` after `stop`/for an unknown topic.
- **stop** deletes/removes the job and is idempotent (no error when absent).
- **status** maps substrate state → the `JobStatus` enum: scheduled / running / succeeded /
  failed / timed_out (k8s `DeadlineExceeded`) / not_found.

## Acceptance
- Gates green (`run_gates.py url4-cloud` ALL GREEN); adapters importable; the deterministic name
  and the four operations behave against injected fakes with no real infra.

## Outcome

- **Actual files:** as planned — `src/url4_cloud/jobs/{__init__,port,k8s,docker}.py` +
  `tests/unit/test_jobs_{port,k8s,docker}.py`; `pyproject.toml` gained `docker>=7.1.0` (7.2.0
  resolved) mirroring `kubernetes`.
- **Design notes:** the port is **synchronous** (matches the sync kubernetes/docker SDKs; the async
  REST layer runs it in a threadpool). The injected-client seams are narrow **structural Protocols**
  (`BatchV1JobsClient` / `DockerContainersClient`) whose view members are read-only properties, so a
  real `V1Job` and the test fakes both conform. `schedule` raises the domain error
  `JobAlreadyExists` (k8s via the atomic `create` `409`; docker via an `exists` pre-check) rather
  than leaking the substrate exception. `status` maps only the states each substrate can observe —
  k8s yields `timed_out` from the `DeadlineExceeded` condition; both yield `not_found` on absence.
- **Commits:** on `OME-513-url4-cloud` (see the OME-519 commit).
- **Gates:** `run_gates.py url4-cloud` ALL GREEN (ruff · format · pyright · pytest+cov). 31 new
  tests; `url4_cloud/jobs/` at 100% line coverage.
- **Deviations:** ledger authored first this cycle (the OME-515 slip is corrected). No app.py change
  — the JobRunner is a port, not a router; production wiring injects
  `kubernetes.client.BatchV1Api()` / `docker.from_env()` in a later unit (REST OME-518 / deploy).
