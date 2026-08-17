# OME-798 — Portal JS tests must be executed by something

Status: approved (owner, 2026-08-13) · Stack: scoreboard

## 1. Problem

`OME-769` shipped 14 tests in `apps/scoreboard/tests/portal/leaderboard-logic.test.js` covering the
board's load-bearing judgements — which row may be presented as state-of-the-art, row ordering, and
accuracy-bar scaling. They pass when run by hand.

**No pipeline runs them.** `scoreboard-tests.yml` has no JS step, and the `scoreboard` stack's
`gates:` list in `.claude/sdlc.local.md` has four entries, all Python. So the invariant those tests
exist to protect — only a reproducible entry may be presented as SOTA — is currently guarded by
something nobody executes. A test that never runs is documentation with a misleading file extension.

## 2. The trap this ticket is really about

The obvious fix is one line of YAML, and **two of the three obvious spellings of that line are
worse than doing nothing**, because they report success while running no tests. Measured on
Node v24.10.0:

| Invocation | Behaviour | Exit |
|---|---|---|
| `node --test tests/portal/` | Node 24 resolves the directory as a module and fails | non-zero, but for the wrong reason — it never runs the tests |
| `node --test "tests/portal/*.test.js"` | when nothing matches: `pass 0, fail 0` | **0 — a green step covering nothing** |
| `node --test tests/portal/*.test.js` | identical, because **Node expands globs itself** — whether the shell expands first is irrelevant | **0 — a green step covering nothing** |
| `node --test tests/portal/leaderboard-logic.test.js` | runs 14 tests; a missing file is an error | 1 on failure or absence |

A green tick is the whole point of a CI step, so a step that is green while collecting zero tests is
actively harmful: it converts "untested" into "believed tested". The rename or directory
restructure that silently empties a glob is exactly the sort of change nobody re-verifies.

## 3. Contract

- The command is the **explicit file path**. It is the only form that fails when the tests are
  absent.
- **Accepted consequence:** a test file added later does not run until it is named. This is the
  lesser of the two risks — a missing file exits 1, an empty glob exits 0 — and both call sites
  carry a note saying to add new files explicitly.
- The command is identical in CI and in the gate card, so a local `run_gates.py scoreboard` and a
  PR check cannot disagree about what "the portal tests pass" means.
- The Node version in CI is **pinned**. The directory-form breakage above is version-specific, so a
  silent runner upgrade must not change what this step does.
- No new dependency, no `package.json`, no lockfile, no dependabot ecosystem, no release lane.
  Node's built-in runner is the whole harness.

## 4. Why the tests live outside `portal/`

`apps/scoreboard/Dockerfile` copies `portal/` **wholesale** into the image, so a test file placed
beside the code it tests would ship to production. They live in `tests/portal/` for that reason.
This is worth restating here because the natural instinct when adding more is to co-locate them.

## 5. Out of scope

vitest, jsdom, DOM-level tests of the rendering code, or any JS toolchain for the app. Those would
trigger the repo's "adding a new component" checklist — CI lane, lockfile, dependabot ecosystem,
CODEOWNERS entry — and belong in their own ticket. This unit adds zero dependencies on purpose.

## 6. Acceptance

- The portal tests run in `scoreboard-tests.yml` on PRs touching `apps/scoreboard/**`.
- `run_gates.py scoreboard` runs them, and the card lists the command.
- A deliberately broken assertion reds both — verified by doing it, not by reading the YAML.
