---
title: Leaderboard submissions board — ranked rows, core columns, mark column
status: accepted
created: 2026-08-12
author: Filip Boltuzic + Claude (Sonnet 5)
related:
  - OME-769 (this unit)
  - OME-768 (the shell this fills — merged)
  - OME-770 (cost & Pareto — shares the mark column)
  - OME-771 (Reproducible/All toggle + Status — receives the descoped SOTA medal)
  - OME-772 (the backend-gap catalogue these omissions trace to)
---

# Submissions board — spec

> **Provenance note.** These decisions were made before implementation and originally recorded
> inline in this unit's work ledger. They are consolidated here because the repo requires a
> `docs/spec/` artifact (CLAUDE.md rule 3) and PR #569's review correctly flagged its absence —
> the approved scope has to be auditable from the docs tree, not only from a ledger. Decision
> numbering matches the ledger.

## Context

`OME-768` landed the per-benchmark page as a shell: tab strip, title, and an empty table
structure. This unit fills that table. Three of the columns the ticket asks for cannot be built
from the current API, and the SOTA medal turned out to be unbuildable *correctly* — both are
resolved by rendering only what the data supports rather than fabricating the rest.

## Decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Row order | Accuracy descending — already the shell's default sort state. |
| D2 | SOTA definition | Top accuracy among reproducible entries only, isolated in a pure function. **Superseded in review — see D13.** |
| D3 | Mark slot | Its own narrow column, not a span in the spec cell. **Revised during implementation:** an in-cell fixed-width slot was built first and broke the alignment it existed for, because the enhanced badge renders wider than its text form and grew the slot on one row only. A column cannot drift. |
| D4 | Medal visual | Vendor the design system's animated wave-mark, text `SOTA` as the progressive-enhancement baseline. **Superseded in review — see D13;** the vendored assets were removed with the medal. |
| D5 | Accuracy cell | Reuse the vendored `.score-cell` / `.score-track` / `.score-fill` recipe. Bar width is accuracy relative to the maximum on screen, so the widest bar is always full. |
| D6 | `Name` column | Keep the existing `Spec` header holding `spec_id`. No name field exists on `Score` or `LeaderboardEntry`, so labelling it "Name" would promise a human-readable name and deliver a technical key. |
| D7 | `Models` column | Not built. The payload carries only `ran_with_providers` (provider names) and free-text `url4_expression`; per-member model names do not exist, and `providers.length > 1` is not a valid fusion/solo test. |
| D8 | Accuracy range whisker | Not built. No min/max/stddev/CI exists anywhere in the schema. The cell is structured so one can be added later without reflowing it. |
| D9 | Summary strip | Keep the three existing stats. No fusion count — fusion vs solo is not derivable (D7). **Revised in review:** the fourth reproducible-SOTA stat was removed with the medal, which also restored `.stats`' three-column grid and left a single `.gain` win colour on the page. |
| D10 | Testing | The load-bearing judgements extracted as pure functions and unit-tested. **Improved during implementation:** Node ships `node:test`, so real RED-first tests landed with zero new dependencies — no `package.json`, no vitest. Wiring them into CI is `OME-798`. |
| D11 | `Questions` column | Removed. Adding Author and the mark column pushed the table past its container, putting the url4 copy button — the board's primary action — behind a horizontal scroll. Questions is absent from this ticket's column list and remains on each spec's detail page. |
| D12 | Row highlight wording | The gold row marks the **highest accuracy on screen** and its accessible text says so. It is not a reproduction claim: SFDS defines gain as the leading-row colour, but the leader is frequently unverified, so the earlier "(state of the art, independently reproduced)" wording would have been false. |
| D13 | **SOTA medal descoped — decided in review of PR #569** | The medal must name the best reproduced run. `/v1/leaderboard` builds `entries` with `RowNumber().over(spec_id).orderby(accuracy DESC, submitted_at DESC)` — one row per spec, verification never consulted. So a spec with a verified 0.80 and an unverified 0.90 returns only the 0.90, and the verified run is invisible to any client. Deriving the medal from that projection can badge a lower verified spec, or none. It is also not fixable by adding a server-computed SOTA field alone: if the winner is a row the table does not contain, there is no truthful row to badge. `OME-771` filters the pool in the **query**, which makes the verified run a real row — the medal belongs there. |

## Out of scope

- Cost column, frontier marks, cost-vs-accuracy chart (`OME-770`).
- Reproducible/All pool toggle, three-way Status column, and the SOTA medal (`OME-771`).
- Any change to the Python backend or API contracts — this unit is portal-only.
