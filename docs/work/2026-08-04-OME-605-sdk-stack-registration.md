---
ticket: OME-605
stack: repo
status: done
started: 2026-08-04
finished: 2026-08-04
---

# OME-605 — Register the ScreamingFace SDK stack

## Intent

Make the new `packages/screamingface` SDK a first-class repository stack: discoverable in the
repo guidance, runnable through the canonical gate command, and explicitly owned for review.

## Planned changes

- Register the SDK and all CI-equivalent checks in `.claude/sdlc.local.md`.
- Add the SDK to `CONTRIBUTING.md` setup, gates, CI, release-state, and reference sections.
- Add an explicit `/packages/screamingface/` CODEOWNERS entry using already verified owners.
- Bring the `working-in-this-repo` routing skill up to date with the active components.

## Test plan

- Demonstrate the gate runner rejects `screamingface` before registration.
- Run `uv run .claude/scripts/run_gates.py screamingface` after registration.
- Confirm the documented gate list matches `.github/workflows/screamingface-tests.yml`.

## Acceptance

- Contributors and agents can discover, route, test, and review SDK changes without guessing.
- The one-command local lane covers lint, format, typecheck, tests/coverage, deterministic
  notebooks, build, and distribution contents.
- Documentation does not claim an SDK publish workflow exists when it does not.

## Outcome

- **Actual files:** `.claude/sdlc.local.md` registers the SDK's seven checks;
  `CONTRIBUTING.md` documents setup, gates, CI, current release state, and reference docs;
  `.github/CODEOWNERS` explicitly registers the package with the already verified shared-library
  owners; `working-in-this-repo/SKILL.md` now routes every active URL4/SDK component accurately.
- **Commits:** this focused restack commit
  (`chore(screamingface): register SDK repository stack`)
- **Gates:** RED was the runner's `stack 'screamingface' not in .claude/sdlc.local.md` error;
  `run_gates.py screamingface` then passed append-only, Ruff, format, Pyright, 95%-coverage tests,
  deterministic notebooks, build, and distribution-content verification.
- **Deviations:** no new cleanup issue was created, per explicit user direction. Documentation
  records that release-please versioning exists but a tagged PyPI publish workflow does not.
