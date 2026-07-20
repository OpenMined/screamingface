---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 6C SDK connection preflight and notebook UX

## Intent

Complete the approved provider-connection experience in the public ScreamingFace SDK. Researchers
can inspect and connect the providers advertised by their configured engine, receive one
actionable preflight error before model spend, and use a compact accessible notebook panel without
the SDK ever contacting AI Gateway directly or retaining credentials.

## Planned changes

- Add focused SDK connection-preflight and notebook-panel modules under
  `packages/screamingface/src/screamingface/`, then wire them through `connections.py`,
  `_execution.py`, `_grading.py`, `fusion.py`, and the public exports/errors.
- Add a notebook UI dependency only with explicit owner approval, and keep the non-interactive
  targeted Python flows deterministic and prompt-free.
- Add append-only Phase 6C tests for stage-specific run/grade/evaluate requirements, fresh status
  reads, structured errors, rejected-credential scheduling boundaries, HTML escaping, accessible
  controls, masked-and-cleared secrets, bounded OAuth polling/cancellation, and light/dark design
  tokens.
- Update generated connection/authentication and quickstart notebook guidance, deterministic
  notebook checks, package README/API examples, the Phase 6 plan, architecture record, and task
  ledger after runtime behavior is green.
- Leave AI Gateway and URL4 source, dataset access, discovery policy, benchmark definitions, and
  engine-owned credential storage unchanged.

Owner decisions recorded before implementation:

- replace the Phase 6A argument-free tuple behavior with a real `ConnectionPanel`; keep
  `sf.connections.list()` as the explicit plain-data operation and add no compatibility shim;
- add `ipywidgets>=8.1` only to the optional `notebook` dependency group, not the core SDK.

Confidence-gate decisions recorded during implementation:

- update the previously approved provider-free execution/grading fixtures to provide explicit
  connected status through a loopback fake engine;
- replace the obsolete Phase 6A argument-free tuple assertion with the approved panel contract;
- correct the DRACO missing-judge assertion to exercise `evaluate(...)`, where the complete union
  preflight belongs; and
- update the prior `evaluate()` facade test because `evaluate()` now owns the approved one-time
  union preflight and therefore no longer delegates through a monkeypatched public `run()` method.
  The owner explicitly approved this final prior-test change on 2026-07-20.

## Test plan

- RED: prove `run` checks only member/reducer providers, `grade` checks only a model judge,
  `evaluate` checks their union once before model spend, deterministic stages require no
  connection, and each preflight performs a fresh engine status read.
- RED: prove one `ConnectionRequiredError` preserves ordered provider/model/role details and gives
  explicit `sf.connect(...)` actions without opening UI or sending model requests.
- RED: prove rejected credentials preserve completed results and prevent new dependent scheduling
  while unrelated deterministic work remains local.
- RED: prove the panel renders every advertised provider and engine origin, escapes account/error
  text, exposes accessible square controls, never serializes live state, masks and clears keys,
  and bounds OAuth refresh/cancel behavior.
- RED: prove sentinels never appear in URLs, representations, HTML, errors, notebook JSON, or
  captured logs, and scripts receive typed actionable errors rather than hidden prompts.
- Run new tests, the full prior suite, coverage, Ruff, formatting, Pyright, deterministic notebook
  regeneration, and `uv run .claude/scripts/run_gates.py screamingface`.

## Acceptance

- `sf.connect`, `sf.disconnect`, and `sf.connections.list` retain the exact approved targeted
  behavior; argument-free `sf.connect()` provides the approved interactive provider panel.
- Model-backed stages fail once and before spend when required providers are not connected;
  benchmark loading, model discovery, ExactChoice grading, and aggregation remain independent.
- The widget follows the ScreamingFace design skill in both themes, is keyboard accessible, and
  retains no API key, OAuth token, live account label, or hidden serialized state.
- All connection traffic goes SDK -> `screamingface-engine`; no direct Gateway/provider client,
  runtime mock, compatibility fallback, or implicit prompt is introduced.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** added `_connection_preflight.py` and `_connection_panel.py`; integrated fresh
  checks and bounded auth-rejection scheduling through execution, grading, Fusion, connections,
  and strict registry decoding; normalized model-call auth failures in the engine Gateway adapter;
  added focused SDK/engine tests; added the generated connections guide; updated quickstart and
  architecture generators/notebooks, README, optional notebook dependency/lockfiles, CI
  regeneration, plan, and task records.
- **Commits:** `feat(screamingface): add provider connection preflight and widget` (this commit).
- **Gates:** Ruff lint and format green; Pyright green; 482 SDK tests green at 95.29% coverage;
  115 engine tests green at 95.84% coverage; `run_gates.py screamingface --skip-append-only` all
  green; frozen notebook-extra sync, Phase 0 fixture construction, sdist, and wheel build green.
  Phase 6B's isolated Docker proof already covered both engine-owned API-key and OAuth adapters
  without a paid model call.
- **Deviations:** prior execution/grading fixtures and facade expectations required the explicitly
  approved confidence-gate updates recorded above, so only the append-only precheck was skipped.
  No quality gate was weakened. No AI Gateway or URL4 source was changed.
