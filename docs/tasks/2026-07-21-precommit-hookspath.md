---
id: OME-525
linear_url: https://linear.app/openmined/issue/OME-525/repo-introduce-pre-commit-framework-fix-stale-corehookspath-chain
status: done
type: task
priority: P1
labels: [repo, autonomous, agentic]
created: 2026-07-21
closed: 2026-07-21
---

# OME-525 — pre-commit framework + fix stale core.hooksPath

Introduce pre-commit (first in the monorepo) and fix the stale `core.hooksPath`
(`apps/desktop/.husky/_`, a removed legacy path) so the committed `.githooks/` fire again.
Fast hooks (ruff-check / ruff-format / std) on every commit; heavy `run_gates.py` on pre-push + CI.
Prerequisite for OME-514. Ledger `docs/work/2026-07-21-OME-525-precommit-hookspath.md`.
