---
ticket: OME-527
stack: url4-cloud
status: in_progress
started: 2026-07-21
finished:
---

# OME-527 — rename protocol package to url4_streaming_protocol

## Intent
The protocol package is a generic CloudEvents streaming protocol, not cloud-specific. Rename
`url4_cloud_protocol` → `url4_streaming_protocol` and update every reference. Mechanical, gate-verified.

## Planned changes
- `git mv src/url4_cloud_protocol src/url4_streaming_protocol`.
- Replace the old name → new across `src/`, `tests/`, `pyproject.toml` (packages), `docs/protocol.md`,
  `.claude/sdlc.local.md` (coverage gate), the CI cov, and the spec/plan.
- `uv sync` (re-install the editable package under the new name).

## Test plan
- `run_gates.py url4-cloud` green after the rename + sync; no `url4_cloud_protocol` references remain
  in living code/config/docs.

## Acceptance
- Gates green; grep finds no `url4_cloud_protocol` outside historical ledgers.

## Outcome (fill at the end — required before COMMIT)
- **Actual files:** `git mv src/url4_cloud_protocol → src/url4_streaming_protocol`; 22 files updated
  — all `src/`+`tests/` imports, `pyproject.toml` (packages + coverage), the `url4-cloud` card cov
  gate, the CI cov, `docs/protocol.md`, spec §2.2/§7, and the plan.
- **Commits:** see the OME-527 commit on `OME-513-url4-cloud`.
- **Gates:** `run_gates.py url4-cloud` GREEN (ruff · format · pyright · pytest+cov, whole suite).
  Append-only check `--skip-append-only` — the mechanical rename touched tests committed by
  OME-516–521; it is an import rename, **not** a test-logic change (authorized under OME-527).
- **Deviations:** the new name is 4 chars longer, so one runner docstring line was rewrapped to
  stay ≤100. Shell `grep -rl | xargs sed` was flaky (BSD quirk) → did the replace in Python.
