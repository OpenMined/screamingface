---
id: OME-743
linear_url: https://linear.app/openmined/issue/OME-743/complete-and-correct-the-aigateway-ui-stack-card-gates
status: planned
type: task
priority: P2
labels: [repo, autonomous, agentic]
created: 2026-08-04
closed:
---

# OME-743 — complete and correct the `aigateway-ui` stack card

Back-filled mirror. This unit was planned in a session without Linear MCP auth and carried
`ticket: UNFILED`; the issue, ledger filename, branch and this mirror were reconciled on
2026-08-04 from a session holding auth.

**Implementation status:** both edits are already made in the working tree but **uncommitted** —
the branch carries no commits beyond this reconciliation. They were left that way deliberately:
they belong to the session that authored them, and the ledger's acceptance includes a negative
test not yet run (a deliberately broken build must fail on `npm run build` specifically, and not
on the other five gates).

## Two independent problems with the `aigateway-ui` entry in `.claude/sdlc.local.md`

**1 — the gate set is incomplete.** `aigateway-ui-tests.yml` has two jobs; the card mirrors one:

| CI job | steps | in the card |
|---|---|---|
| `test` | `npm ci` · `lint` · `lint:css` · `typecheck` · `test:ci` | all five |
| `Build the app` | `npm ci` · **`npm run build`** | **missing** |

A build-only failure — bad Turbopack root, a server/client boundary violation, an unserializable
prop crossing into a Server Component — passes every local gate and first surfaces in CI, or
later on a release tag in the image build. `tsc --noEmit` does not cover it: it never exercises
Turbopack module resolution, static generation, or the `output: "standalone"` bundle the
Dockerfile depends on.

Confirmed rather than theoretical: **`OME-736` ran `npm run build` by hand** and recorded it as a
separate acceptance bullet, precisely because the gate set would not run it.

**2 — the card describes the pre-`OME-716` world.** #462 (merged 2026-08-03) moved the console
from the OpenMined Design System to SFDS v2. The card was never updated, so it contradicts
`apps/aigateway-ui/CLAUDE.md` ("Do not reintroduce OMDS") and cites `src/brand/brand-version.txt`,
which that unit deleted. Knock-on: `OME-736`'s PR description repeated the stale OMDS line
straight from this card — a wrong card propagates.

## Scope

- `.claude/sdlc.local.md` — add `npm run build` **after `typecheck`, before `test:ci`**
  (fail-fast: build ~5 s vs `test:ci` ~60 s, and the runner stops at the first red gate);
  retarget the `lint:css` comment to SFDS v2; rewrite the brand-law bullet; drop the dead
  `brand-version.txt` reference.
- `apps/aigateway-ui/README.md` — correct the "step for step" claim.

## Not in this unit

The missing **a11y gate** (`OME-736`'s recorded defect, `sdlc-react` rule 7) — not a card edit,
since `aigateway-ui` has no axe/jest-axe dependency and no `test:a11y` script. Needs its own
ticket. Also out: the `working-in-this-repo` routing table's inverted brand-law line, and the
"OMDS token gate" step name at `aigateway-ui-tests.yml:47`.

Ledger: `docs/work/2026-08-04-OME-743-aigateway-ui-stack-card-repair.md`
