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

Client side of the OME-796 design resolution (stages 0+2 of the one-PR plan): PR #571
review-findings pre-cleanup (duplicate-member-name paid-run bug, unified topology walker,
rendered-surface linker guard, dead-code removal); `sf.CorrectiveLoop(members, judge=,
max_rounds=3)` + `sf.SelfCorrective(model, max_rounds=3)` compiling the whole loop into ONE
`$candidate` against manifest `check_surface` routes; preflight fail-before-spend;
`stop_reason`/`rounds_executed` reporting; notebook 07 2×2 grid + DRACO/HealthBench
corrective cells.

Design source: OME-796 issue body ("Design resolution 2026-08-14") + attached diagrams.
Ledger: `docs/work/2026-08-14-OME-796-corrective-loop-generalization.md`
