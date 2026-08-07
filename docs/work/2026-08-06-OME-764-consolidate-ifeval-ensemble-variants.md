---
ticket: OME-764
stack: url4-cloud
status: in_progress
started: 2026-08-06
finished:
---

# OME-764 — Consolidate IFEval ensemble variants: LANL early-exit flow replaces verifying-ensemble

## Intent

End state: two IFEval stories — `ifeval` (Zhou et al. 2023 canonical, plus its solo
corrective baseline `ifeval/self-corrective`) and `ifeval/lanl-ensemble` (Skurikhin et
al. §2, early exit). The OpenMined `ifeval/verifying-ensemble` variant runs all three
rounds unconditionally and a judge pick every round — ~3x token burn for the same
earliest-pass score — and is removed as superseded.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py`: absorb
  `lanl_ensemble.py`'s builder; drop the verifying-ensemble build + `IFEVAL_VERIFYING_ENSEMBLE`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/lanl_ensemble.py`: delete.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/corrective_policy.py`: drop
  `JUDGE_PICK_INSTRUCTION`, `ENSEMBLE_PROTOCOL_REVISION`, `VERIFYING_ENSEMBLE_REVISION`,
  `ENSEMBLE_ROUTE_PREFIX` + its routes; rehome resolve-candidate / member-record /
  member-answer routes under `LANL_ROUTE_PREFIX`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/runtime.py`: drop `_select` +
  `SELECT_ROUTE` + `ENSEMBLE_AGGREGATE_ROUTE` registrations.
- `apps/url4-cloud/src/url4_cloud/benchmarks/__init__.py`: registry drops
  `IFEVAL_VERIFYING_ENSEMBLE`.
- Tests: `test_ifeval_iterative_correction.py` (drop verifying-ensemble cases, keep
  self-corrective + machinery), `test_ifeval_lanl_ensemble.py` (import path),
  `test_flat_benchmark_resources.py`, `test_url4_executor.py`, `test_aigateway_connector.py`,
  `test_ifeval_aggregate_case_mapping.py` (revision import).

## Test plan

- Existing LANL suite stays green (gate table, selection, envelope, expression shape).
- Self-corrective tests stay green untouched — protects the solo baseline.
- Registry test asserts `ifeval/verifying-ensemble` is GONE and `ifeval/lanl-ensemble`
  present — protects the "menu names the protocol it runs" invariant.
- Member-machinery routes respond under the LANL prefix.

## Acceptance

- `uv run pytest tests/unit` green in apps/url4-cloud; url4 suite untouched/green.
- `grep -r "verifying-ensemble" src/` returns nothing.
- Benchmark registry: draco, humaneval?, ifeval, ifeval/self-corrective, ifeval/lanl-ensemble.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus: `test_ifeval_member_shape.py` rewritten to pin the
  surviving machinery (judge-letter parsing via LANL select, prose constants, member
  bounds); `test_ifeval_candidate_validation.py` / `test_ifeval_case_evaluation_route.py`
  / `test_candidate_retrieval_scope.py` / `test_benchmark_manifests.py` retargeted to
  `ifeval/lanl-ensemble`; notebook `packages/screamingface/examples/07_ifeval_e2e.ipynb`
  ids swapped (not executed — paid runs are Khoa's).
- **Commits:** none yet — uncommitted on `feat/ifeval-fidelity` alongside the fidelity work.
- **Gates:** apps/url4-cloud `uv run pytest tests/unit`: 966 passed, 5 skipped, 1 xfailed;
  packages/url4: 1127 passed. `grep -r "verifying-ensemble" src/` clean.
- **Deviations:** the E2E `test_member_shaped_corrective_runs_member_checks_retries_and_judging`
  is `xfail(strict=True)`: converting it to the LANL flow exposed a url4-core decode bug
  (`OME-765`, filed, blocks this) — a mid-list iterate source in a paren-stripped map-row
  body is misparsed, so the lanl-ensemble continuation cannot execute until the core fix
  lands in its own url4 PR. A drafted fix is recorded on `OME-765`; url4 package edits
  were reverted out of this branch per owner instruction.
