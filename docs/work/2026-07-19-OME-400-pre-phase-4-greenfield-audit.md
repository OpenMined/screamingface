---
ticket: OME-400
stack: screamingface
status: complete
started: 2026-07-19
finished: 2026-07-19
---

# OME-400 — Pre-Phase 4 greenfield audit and cleanup

## Intent

Audit every implemented ScreamingFace surface through Phase 3D as a greenfield system. Remove
dead compatibility-era code and stale documentation, correct architectural inconsistencies, and
enter Phase 4 with one supported SDK/engine contract.

## Approved decisions

- Keep explicitly labelled SDLC work ledgers and task history as audit evidence.
- Delete obsolete normative plans/specifications and obsolete user-facing examples and docs.
- Hide DRACO from the engine registry until its judge route and required `web_search` capability
  are genuinely runnable.
- Restrict `sf.config(engine=...)` to an HTTP(S) origin with no path, query, or fragment.
- Keep `packages/screamingface/examples/draco-eval-demo/` untouched and untracked.
- Modify prior ScreamingFace tests where the approved greenfield contract invalidates their old
  setup or expectations, and run the official gate with `--skip-append-only`. The owner explicitly
  approved this Confidence-Gate exception on 2026-07-19.

## Planned changes

- Remove dead mock-server scripts/configuration and pre-greenfield notebooks, generators, YAML,
  and HTML reference material.
- Remove dependencies and CI extras used only by those deleted surfaces.
- Ignore the local `draco-eval-demo` reference so package gates and commits cannot accidentally
  absorb or rewrite it.
- Reconcile root, package, engine, task, plan, and normative contract documentation.
- Move the canonical DRACO prompt out of the generic SDK and into the engine publisher.
- Stop advertising or serving DRACO until Phase 4 makes it loadable and runnable.
- Capture the exact selected `Case` values in `Run` so grading never rematerializes a mutable or
  non-deterministic callable source.
- Reuse strict duplicate-key JSON decoding at every engine boundary and remove redundant engine
  publication state.

## Verification

- Absence searches for every removed API, schema, mock path, and obsolete artifact.
- Focused tests for origin-only configuration, Run case snapshots, strict registry JSON, and the
  runnable-only registry invariant.
- SDK and engine coverage gates at 95% or higher.
- Ruff, formatting, Pyright, fixture regeneration, current notebook regeneration, package builds,
  and CI configuration validation.

## Outcome

Completed the approved greenfield cleanup through Phase 3D.

- Deleted the superseded normative plan/spec, user-facing notebooks, notebook generators, YAML
  example, static HTML reference, mock/local server scripts, URL4 TOML, and generic SDK DRACO
  publication module.
- Removed the SDK's unused YAML, dataset, widget, and live-test-marker dependencies and updated
  both lockfiles and CI installation.
- Reconciled the root, contributor, SDK, engine, plan, specification, and task documentation with
  the sole supported SDK -> HTTP screamingface-engine -> AI Gateway boundary.
- Restricted engine configuration to one HTTP(S) origin and added focused validation coverage.
- Captured exact selected `Case` values in every `Run`; grading now consumes that immutable
  snapshot instead of rematerializing a callable source.
- Applied the shared duplicate-key-rejecting JSON decoder to registry and manifest plaintext.
- Removed DRACO from the development engine registry, manifests, case routes, and publisher code.
  A 404 contract test prevents it from being advertised accidentally before Phase 4 is runnable.
- Updated old tests only where the new greenfield contract required it, under the owner's explicit
  Confidence-Gate approval. The gate's append-only check was skipped; no other gate was weakened.
- Added the local `draco-eval-demo` reference to `.gitignore`, leaving every file inside it
  untouched while preventing accidental linting or commits.

The planned prompt move became unnecessary after the owner chose to hide DRACO completely. Phase
4 should add the canonical prompt directly to its real publisher together with the judge route,
working `web_search` adapter, cache semantics for independent passes, and pinned dataset revision;
there is no dormant partial DRACO implementation to preserve.

## Verification results

- `uv run .claude/scripts/run_gates.py screamingface --skip-append-only` — all configured gates
  green (Ruff lint/format, Pyright, pytest, and >=95% SDK coverage).
- SDK: 240 tests passed; 96.88% coverage.
- screamingface-engine: 45 tests passed; 97.69% coverage.
- Phase 0 fixture construction passed.
- Phase 1 walkthrough regeneration produced no diff.
- SDK source and wheel distributions built successfully.
- `docker compose config --quiet` passed for the local engine stack.
- `git diff --check` passed.
- Tracked runtime/user-documentation absence searches found no obsolete route namespace, mock
  implementation, in-process fallback, deleted artifact reference, YAML API, or compatibility
  alias. The remaining negative wording in the normative exclusion list and the DRACO 404 test
  are intentional contract assertions.

No architectural uncertainty remains in the implemented Phase 0-3D boundary. Phase 4 capability
work remains deliberately unimplemented and must be reviewed with the owner before execution.
