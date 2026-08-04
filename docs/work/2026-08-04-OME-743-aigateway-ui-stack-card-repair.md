---
ticket: OME-743
stack: aigateway-ui
status: in_progress
started: 2026-08-04
finished:
---

# OME-743 — complete and correct the `aigateway-ui` stack card

## PROCESS DEVIATION — RECONCILED 2026-08-04

This unit was planned in a session where the Linear MCP plugin was **unauthenticated**. The card
(`.claude/task-board.local.md`) names it the ONLY permitted transport — API tokens and raw
GraphQL are forbidden — so the ledger was written against `ticket: UNFILED`, with the owner
electing to proceed and record the deviation rather than authorize mid-session.

**All four dangling fields have since been back-filled** from a session that does hold MCP auth:

| field | correct value | status |
|---|---|---|
| ledger `ticket:` | `OME-743` | ✅ reconciled |
| ledger filename | `2026-08-04-OME-743-…md` | ✅ renamed |
| branch | `OME-743-aigateway-ui-stack-card-repair` | ✅ renamed (was `sdlc-card-aigateway-ui-gates`) |
| `docs/tasks/` mirror | `docs/tasks/2026-08-04-ome-743-aigateway-ui-stack-card-repair.md` | ✅ created |

The branch carried no commits at reconciliation time, so nothing needed rewriting — commits from
here on **must** carry `Refs: OME-743`.

**AIDEV-NOTE:** the deviation is kept on the record rather than deleted. The failure mode it
documents is real — a session without MCP auth cannot file work, and the repo's rules leave no
compliant alternative. See also `OME-741`, a separate instance of tooling leaving no legitimate
path for a rule the process explicitly permits.

## Intent

The `aigateway-ui` entry in `.claude/sdlc.local.md` has two independent problems.

**1 — the gate set is incomplete.** `aigateway-ui-tests.yml` has two jobs; the card mirrors only
one:

| CI job | steps | in the card |
|---|---|---|
| `test` | `npm ci` · `lint` · `lint:css` · `typecheck` · `test:ci` | all five |
| `Build the app` | `npm ci` · **`npm run build`** | **missing** |

So a build-only failure — bad Turbopack root, a server/client boundary violation, an
unserializable prop crossing into a Server Component — passes every local gate and first appears
in CI, or on a release tag in the image build. `tsc --noEmit` does not cover this: it never
exercises Turbopack module resolution, static generation, or the `output: "standalone"` bundle the
Dockerfile depends on. `apps/aigateway-ui/README.md` claims the gates match the workflow "step for
step", which is true of one job out of two.

Evidence this is real and not theoretical: `OME-736` ran `npm run build` **by hand** and recorded
it as an acceptance bullet, because the gate set would not run it.

**2 — the card still describes the pre-`OME-716` world.** `#462` merged 2026-08-03 and moved the
console from the OpenMined Design System to SFDS v2. The card was not updated, so it now
contradicts `apps/aigateway-ui/CLAUDE.md` — which says "Do not reintroduce OMDS" — and cites a
file that unit deleted.

## Planned changes

- `.claude/sdlc.local.md`
  - add `npm run build` to the `aigateway-ui` gates, **after `typecheck`, before `test:ci`**
    (fail-fast: the build is ~5 s, `test:ci` ~60 s, and the runner stops at the first red gate)
  - retarget the `lint:css` comment from OMDS to SFDS v2
  - rewrite the brand-law bullet: SFDS v2, the app register, gold used nowhere
  - drop the `src/brand/brand-version.txt` reference — `OME-716` deleted that file
- `apps/aigateway-ui/README.md` — correct the "step for step" claim to name both CI jobs

## Explicitly NOT in this unit

- **The missing a11y gate** (`OME-736`'s recorded card defect, `sdlc-react` rule 7). Not a card
  edit: `aigateway-ui` has no axe/jest-axe dependency and no `test:a11y` script, so it needs real
  tooling. Stays recorded, needs its own ticket.
- **`working-in-this-repo` skill** — its routing table carries the same inverted brand-law line.
- **`.github/workflows/aigateway-ui-tests.yml:47`** — step still named "Lint styles (OMDS token
  gate)".

## Test plan

No RED test: this unit adds no code. The gate set **is** the test, so verification is behavioural:

- `run_gates.py aigateway-ui` runs `npm run build` and reports it — proving the gate is wired
- the full set stays green (218 tests baseline)
- a deliberately broken build is caught by the gate and **not** by the other five — proving the
  gate closes a hole the existing ones do not

## Acceptance

- `npm run build` appears in the runner output between `typecheck` and `test:ci`
- gates green end to end
- the negative test above fails on `npm run build` specifically
- no OMDS claim and no dead file reference remains in the card
- `grep -c OMDS .claude/sdlc.local.md` returns only historical mentions, if any

## Outcome

- **Actual files:** as planned — `.claude/sdlc.local.md` and `apps/aigateway-ui/README.md`. No
  source file touched; no test touched (append-only gate clean).

- **Gates:** green, with the new gate in position.

  ```
  ✓ append-only test check (vs HEAD)
  ✓ npm ci
  ✓ npm run lint
  ✓ npm run lint:css
  ✓ npm run typecheck
  ✓ npm run build        ← this unit
  ✓ npm run test:ci      13 files, 218 tests passed
  ALL GATES GREEN
  ```

- **The negative test was run, and it is the real result of this unit.** A client component
  importing the `server-only` BFF module (`src/lib/aigateway/client.ts`) — the exact violation
  `apps/aigateway-ui/CLAUDE.md` says must "fail the build rather than ship the admin API's address
  to the browser":

  | gate | exit |
  |---|---|
  | `npm run lint` | 0 — does not catch it |
  | `npm run lint:css` | 0 — does not catch it |
  | `npm run typecheck` | 0 — does not catch it |
  | `npm run test:ci` | 0 — does not catch it (all 218 pass) |
  | **`npm run build`** | **1 — catches it** |

  Turbopack: `Client Component Browser: ./src/lib/aigateway/client.ts ← ./src/app/probe/page.tsx`.

  **So before this change the BFF invariant was enforced by CI but NOT by the local gate set.** The
  documented guarantee held on the remote and was unverifiable on the machine writing the code.

- **Acceptance:** all met. `grep` for `OMDS|OpenMined Design|brand-version.txt` in the card returns
  only the two deliberate historical mentions ("this REPLACED the OpenMined Design System in
  `OME-716`", "Do not reintroduce OMDS"); the dead `brand-version.txt` reference is gone.

## Deviations

1. **The first negative-test probe was silently inert.** It was placed at `src/app/_probe/`, and
   Next treats a leading-underscore folder as a **private folder** excluded from routing — so it
   was never compiled and the build passed. Only the missing `/_probe` entry in the printed route
   table revealed it; re-run at `src/app/probe/` it failed immediately. A negative test that passes
   for the wrong reason is worse than no negative test.

2. **A stale `.next/types/validator.ts` then failed `typecheck`** after the probe was deleted — the
   generated route validator still imported `../../src/app/probe/page.js`. `rm -rf .next` cleared
   it. Worth knowing: **`npm run typecheck` reads build-generated types**, so it can fail on a route
   that no longer exists. An ordering coupling between the `build` and `typecheck` gates, not a code
   error.

3. **No RED-first cycle**, by nature: the unit changes a gate list and prose, not code. The
   behavioural verification above stands in for it.

4. **Concurrent-session collision mid-unit.** The working tree was switched to another branch
   (`OME-738-public-docs-ci-lane`) while these edits were uncommitted; git carried them across
   because they did not conflict. Nothing was lost — the branch, the reconciliation commit and the
   edits all survived — but the edits were briefly sitting on an unrelated unit's branch. Recovered
   by checking out this branch again and committing immediately. **Lesson: commit early when more
   than one session shares a checkout**; uncommitted work is the only thing a branch switch can
   silently relocate.
