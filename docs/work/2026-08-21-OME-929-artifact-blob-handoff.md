---
ticket: OME-929
stack: screamingface-engine
status: in_progress
started: 2026-08-21
finished:
---

# OME-929 — Over-cap result artifacts must survive the Runner Job

## Intent

Every full-scale benchmark run on the hosted Engine currently produces **no Report at all**. A
result over the 1 MiB inline cap spills to a content-addressed artifact, but the Runner Job pod
and the App pod each mount their own `emptyDir` at `/tmp` and `URL4_CLOUD_ARTIFACTS_DIR` is set
nowhere in the chart — so both fall back to the same pod-local default, which is two different
disks. The client redeems the claim ticket against the App and gets 404, after all 11,902 model
calls of a DRACO 3-pass run have been paid for. The artifact *is* the Report's payload
(`_decoded_result_body` raises on a `None` body), so losing it is total, not partial.

This unit moves spilled artifacts into self-hosted S3-compatible object storage (Garage) for the
`k8s`/`jetstream` backends, keeps the filesystem store for `inprocess`/local, and closes the
coverage gap that let the bug ship.

Spec: `docs/spec/2026-08-21-OME-929-artifact-blob-handoff.md` (owner decisions D1–D5)
Plan: `docs/plan/2026-08-21-OME-929-artifact-blob-handoff.md` (three iterations)

## Planned changes

Iteration 1 — ports (no behaviour change):
- `src/screamingface_engine/artifacts/{__init__,ports,filesystem}.py` — split the single
  `ArtifactStore` into `ArtifactWriter`/`ArtifactReader`; `ArtifactStore` retained as an alias
  for `FilesystemArtifactStore` (24 call sites, 4 test modules, append-only tests)
- `src/screamingface_engine/rest/artifacts.py` — render `ArtifactContent` (`FileResponse` for
  `LocalFile`, `StreamingResponse` for `RemoteStream`)

Iteration 2 — the adapter and the bug's acceptance test:
- `src/screamingface_engine/artifacts/sigv4.py` — pure SigV4 signer (no I/O)
- `src/screamingface_engine/artifacts/s3.py` — `S3ArtifactStore` over `httpx`
- tests: SigV4 vectors, fake-S3 round-trip, **separate-roots acceptance test**, cap boundary,
  upload-before-terminal-frame ordering

Iteration 3 — wiring and loud failure:
- `deploy/helm/` — Garage template + values + PVC; S3 settings into `configmap-runner-env.yaml`
  and `configmap.yaml`; credentials Secret via `envFrom` (TAVILY precedent)
- `src/screamingface_engine/{config,job_env}.py`, `adapters/factory.py` — derived selection
  (§4.3) + startup guard (§4.4)
- tests: `DEPLOY_TIME` ↔ rendered-chart contract test; startup-guard tests
- comment corrections: `artifacts.py` header, `job_env.py:242`, `job_env.py:305`, `app.py:104`

## Test plan

Risk-ranked (highest first), mirroring the ticket's R1–R5:

- **R1 the bug.** Writer and reader on separate storage — over-cap result round-trips.
  Parametrised over both adapters: fails for filesystem-on-separate-roots with the 404, passes
  for S3. 100% reproducible.
- **R2 silent regression.** Every existing artifact test uses one store instance in one process,
  so none of them can catch a writer/reader split. The R1 test is the structural fix. Plus the
  `DEPLOY_TIME` ↔ chart contract test, which would have gone red the day OME-892 landed.
- **R3 cap boundary.** `cap-1`, `cap`, `cap+1` — first two inline, third spills.
- **R4 ordering.** Upload completes before the terminal frame is published; otherwise the client
  can redeem a ticket for an object that does not exist yet.
- **R5 diagnosability.** A storage mismatch fails at startup/first write with the missing
  setting named — never a fetch-time 404 minutes after the spend.
- SigV4 correctness against AWS's published test vectors (table-driven, pure).
- Error paths: bad signature (403), missing object (`None`, not an exception), truncated upload
  surfaces rather than minting a ticket for absent content.

Explicitly **not** covered: real Garage behaviour under load, and multi-replica App (out of
scope — the App is pinned to one replica for the in-process subscriber gate).

## Acceptance

Spec §6, items 1-8. Headline: a >1 MiB result round-trips end to end on the deployed pods, and
a writer/reader storage mismatch can no longer reach fetch time.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** <vs planned>
- **Commits:** <sha — message>
- **Gates:** <run_gates.py result line / counts>
- **Deviations:** <anything that differed from the plan, or "none">
