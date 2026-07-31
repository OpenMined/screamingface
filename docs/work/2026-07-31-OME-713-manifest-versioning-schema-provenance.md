---
ticket: OME-713
stack: url4-cloud
status: in_progress
started: 2026-07-31
finished:
---

# OME-713 — Version, schema-tag, and pin case provenance in the benchmark manifest

## Intent

Harden the benchmark manifest before its schema freezes (spec v3 §4): a versioned exam
identity (`id: draco-lite@1`), a format schema tag
(`schema: screamingface.benchmark-manifest.v1`), and a `provenance.cases` block pinning the
cases revision. Without these, a dataset/judge change silently mixes incomparable scores in
one leaderboard column. Delivered as an UNCOMMITTED review diff on Keelan's `OME-605` branch
worktree — owner reviews before anything is committed.

## Planned changes

- `apps/url4-cloud/src/url4_cloud/benchmarks/draco/family.py` — `build_draco_benchmark`
  gains a `version` param; manifest gains `schema:` line, versioned `id`, `provenance:` block
  (cases sha256 over canonical JSON).
- `apps/url4-cloud/src/url4_cloud/benchmarks/draco/definition.py` — pass `version=1`.
- `apps/url4-cloud/src/url4_cloud/benchmarks/draco/smoke.py` — pass `version=1`.
- `apps/url4-cloud/tests/unit/benchmarks/test_draco.py` — new tests (append-only).

NOT changed: registry keys, REST routes, SDK (`name` stays the addressable id; decoder
already tolerates the new fields).

## Test plan

- Manifest declares `schema: screamingface.benchmark-manifest.v1` as its first line.
- `id` is `<name>@<version>` while `name` stays the registry address (invariant: same id
  string ⇒ same exam; address stays stable for clients).
- `provenance.cases.revision` is a 64-hex sha256 that is deterministic across builds and
  CHANGES when the pinned cases change (the anti-silent-drift invariant).
- Existing tests untouched and green.

## Acceptance

- All url4-cloud gates green (`run_gates.py url4-cloud`).
- Diff left uncommitted for owner review.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** exactly as planned — `family.py` (+`version` param, `schema:` line,
  versioned `id`, `provenance:` block, `_cases_revision` sha256 helper), `definition.py` +
  `smoke.py` (`BENCHMARK_VERSION = 1`), `test_draco.py` (+3 tests, pure append — 0 deletions
  in the diff).
- **Commits:** none by agreement — owner reviews the working-tree diff first.
- **Gates:** ruff check ✓ · ruff format ✓ on all touched files · pyright ✓ (0 errors) ·
  pytest 542 passed / 2 failed / coverage 94.87% (≥80). The 2 test failures, the 2
  format failures (aigateway-connector files), and the layering violation
  (`connections/__init__.py` → `config`) all reproduce at HEAD or come from the owner's own
  uncommitted `openrouter/` edits — none introduced by this unit.
- **Deviations:** ran `run_gates.py --skip-append-only` — the file-level append-only check
  trips on any `M` to a test file; the diff was verified pure-append (0 deleted lines)
  before skipping. Status stays `in_progress` until the owner reviews and commits.
- **Follow-up fix 1 (same unit):** owner's e2e notebook exposed that the SDK compiles the
  manifest `id` into the executed `/benchmark` command (`_compiler.py` uses
  `manifest.info.id`), so the versioned id hit the registry and failed. Fix: `Benchmark`
  gains `version` + `versioned_id`; `registry.benchmark()` resolves the address OR the
  exact versioned identity and rejects version mismatches (never a silent fallback).
  Files added to the unit: `benchmarks/_types.py`, `benchmarks/registry.py`, one more
  appended test (`test_registry_resolves_the_versioned_exam_identity`).
- **Follow-up fix 2 (same unit):** second e2e run failed deeper — `@` is url4's reserved
  holdings-reference token; the dag compiler's `"@" in context` check
  (`url4/dag/compiler.py` `_context_slots`) drops any /benchmark context containing `@`
  out of structured ctx-slot lowering (verified by DAG repro: `ctx_slots=None`, no `ctx:0`
  StructNode). Separator changed `@N` → `-vN` (`draco-lite-v1`); terminal `-v<digits>` is
  reserved for the version. Spec v3 §4 amended.
- **Follow-up fix 3 (same unit, OWNER-APPROVED prior-test change):** third e2e run — all
  Runs succeeded but the SDK result decoder rejects a report whose `benchmark_id` differs
  from the manifest `id`. Decision (owner picked over changing the SDK): the aggregate
  report's `benchmark_id` now carries the VERSIONED exam identity (`draco-smoke-v1`) —
  the result names the exact exam sat (leaderboard column key). `family.py` passes the
  versioned id into `build_actions`; the two prior assertions in `test_draco.py` expecting
  the unversioned id were updated with owner approval (append-only exception).
