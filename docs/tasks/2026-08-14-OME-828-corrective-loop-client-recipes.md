---
id: OME-828
linear_url: https://linear.app/openmined/issue/OME-828/add-correctiveloop-and-selfcorrective-client-recipes-compiling-against
status: In Progress
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-14
parent: OME-796
blocked_by: [OME-827]
---

# Add CorrectiveLoop and SelfCorrective client recipes compiling against the check surface

Client side of the OME-796 design resolution (stage 2 in PR #598; prerequisite cleanup
landed separately in PR #597): `sf.CorrectiveLoop(members, judge=,
max_rounds=3)` + `sf.SelfCorrective(model, max_rounds=3)` compiling the whole loop into ONE
`$candidate` against manifest `check_surface` routes; preflight fail-before-spend;
editable replay and fail-closed topology validation; and the notebook 07 2×2 grid.
The remaining Client-side acceptance item is strict parsing, immutable values, export,
and report display for per-case `stop_reason` and `rounds_executed`, carried through the
shared Candidate execution-provenance contract rather than Recipe-specific result code.

Design source: OME-796 issue body ("Design resolution 2026-08-14") + attached diagrams.
Ledger: `docs/work/2026-08-14-OME-828-corrective-loop-client-recipes.md`
