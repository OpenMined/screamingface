---
ticket: OME-712
stack: url4
status: in_progress
started: 2026-08-04
finished:
---

# OME-712 — certify URL4 runtime foundations for benchmarks

## Intent

Certify the independently reviewable `packages/url4` base of the end-to-end benchmark stack:
outer bindings must reach iteration bodies through both compiler interfaces, large reducer
payloads must have a stdin path, and observed usage must preserve the actual served model.
The package remains benchmark- and provider-agnostic.

## Planned changes

- `docs/tasks/2026-07-31-ome-712-run-draco-url4.md` — missing Linear mirror.
- `docs/spec/2026-08-04-OME-712-url4-runtime-foundations.md` — package contract.
- `docs/plan/2026-08-04-OME-712-url4-runtime-foundations.md` — certification sequence.
- `docs/work/2026-08-04-OME-712-url4-runtime-foundations.md` — this audit trail.
- Existing `packages/url4` production files only if an evidence-backed defect is found.
- New append-only tests only at the public compiler, command-route, or observation seams.

No database schema or model changes; migration rule S1 does not apply.

## Test plan

- Run the canonical URL4 gate on the unchanged branch as the baseline.
- Compiler: compare text and AST behavior for enclosing bindings, row-name shadowing, nested
  bodies, and per-row intent.
- Command route: default/context and intent stdin, invalid selector, payload above 128 KiB,
  and unchanged argv substitution/error behavior.
- Observation: requested and response model differ; missing response model remains absent.
- Run the complete append-only gate after any correction or refactor.

## Acceptance

- The spec, code, and behavior-level tests agree on all three contracts.
- No benchmark/provider policy enters `packages/url4`.
- No inherited test is modified, deleted, weakened, or skipped.
- The deployment-target Linux `url4` gate reports `ALL GATES GREEN`; any host-platform-only
  assertion is called out with its passing Linux CI evidence.
- The diff can be reviewed without reading the AI Gateway, URL4 Cloud, or SDK layers.

## Outcome

- **Actual implementation files:** `packages/url4/src/url4/cli/_serve.py`,
  `packages/url4/src/url4/dag/compiler.py`, `packages/url4/src/url4/dag/node.py`,
  `packages/url4/src/url4/dag/nodes.py`, and `packages/url4/src/url4/observe.py`, plus four new
  focused test modules.
- **Commits reviewed:** `30d0b3bf`, `dce957e1`, `4e71233f`, `d0eba10f`, and `ec2f5075`.
- **Local gate:** formatting, lint, type checking, append-only enforcement, and 1,124 tests
  passed. One Linux-kernel assertion intentionally fails on macOS because Darwin accepts the
  200,000-byte argv used to prove Linux `MAX_ARG_STRLEN`; the same payload passes over stdin.
- **Linux evidence:** PR #464's Python 3.12 and 3.13 URL4 lanes pass the complete suite.
- **Deviations:** the underlying five implementation commits predate this ledger under a
  standing owner exception; OME-712 remains cross-cutting and Linear was not mutated.
