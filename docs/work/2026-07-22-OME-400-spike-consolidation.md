---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-22
finished: 2026-07-22
---

# OME-400 — Consolidate the ScreamingFace SDK spike for handoff

## Intent

Preserve the working SDK and DRACO reference implementation while removing abandoned demo work,
making the existing branch gates green, and leaving one unambiguous current architecture and
engine-owner handoff. This is consolidation of an unreleased spike, not a new runtime feature.

The owner explicitly approved discarding the unrelated AI Gateway logging experiment, the Colab
deployment experiment, and the temporary bearer-token extension to `sf.config`. The owner also
approved the Confidence-Gate exception needed to mechanically format existing tests and regenerate
deterministic notebook fixtures during this cleanup; their behavior must not be weakened.

## Planned changes

- Remove the abandoned AI Gateway logging, Colab, Caddy/demo deployment, and SDK bearer-token work.
- Preserve the intentional DRACO Lite ten-criterion update and readable candidate construction.
- Apply canonical Ruff formatting to the three committed files currently failing the format gate.
- Regenerate every deterministic notebook from its checked-in builder without executing paid work.
- Reconcile the current SDK README, engine-reference README, architecture plan, normative contract,
  task mirror, and repo-local guidance with the implemented engine-owned benchmark boundary.
- Add one concise handoff for the ScreamingFace engine owner, including private SDK coupling and
  the `url4-cloud` transport integration boundary.
- Leave the untracked colleague-owned `apps/url4-cloud/` tree untouched and uncommitted.

## Test plan

- Run the append-only gate and confirm only the explicitly approved mechanical fixture/test changes
  remain.
- Run Ruff lint and format checks, Pyright, SDK and engine tests with required coverage,
  deterministic notebook verification, fixture verification, and package build.
- Confirm no changes are staged or committed under `packages/url4`, `apps/aigateway`, or
  `apps/url4-cloud`.
- Confirm `git diff --check` passes and no notebook contains execution output.

## Acceptance

- The abandoned demo/token/logging work is absent.
- One current contract describes the implemented SDK-to-engine behavior without legacy API claims.
- The engine handoff is explicit and does not assign engine implementation ownership to the SDK.
- The complete ScreamingFace gate passes.
- The final diff is reviewable by scope and safe to share as a reference spike.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** removed the abandoned uncommitted AI Gateway logging, Colab/demo deployment,
  and SDK bearer-token work; formatted the three previously red committed Python files;
  regenerated the deterministic notebook set; updated the current architecture, runtime contract,
  repo routing guidance, READMEs, task mirror, and executable fixtures; added
  `scripts/check_contract_fixtures.py`, its CI gate, and the engine-owner handoff.
- **Commits:** pending owner review.
- **Gates:** authoritative `run_gates.py screamingface --skip-append-only` green: Ruff lint and
  format, Pyright, 401 SDK tests at 95.13%, 318 engine tests at 95.11%, executable contract
  fixtures, deterministic notebooks, and wheel/sdist build. `git diff --check` is green and the
  notebooks contain no execution outputs.
- **Deviations:** the append-only automation was skipped only because the owner explicitly
  approved canonical formatting of three existing test/source files and deterministic regeneration
  of existing notebook fixtures. Historical phase ledgers remain preserved as audit evidence; the
  current contract and task header explicitly mark their removed APIs as superseded. The
  colleague-owned untracked `apps/url4-cloud/` tree was not changed or included.
