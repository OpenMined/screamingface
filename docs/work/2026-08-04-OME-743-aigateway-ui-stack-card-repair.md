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

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:**
