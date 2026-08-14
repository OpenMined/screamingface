---
id: OME-827
linear_url: https://linear.app/openmined/issue/OME-827/lift-corrective-loop-substrate-into-generic-ensemble-module-behind-a
status: In Progress
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-14
parent: OME-796
---

# Lift corrective-loop substrate into generic ensemble module behind a check-surface port

Engine side of the OME-796 design resolution (stages 1+3+4 of the one-PR plan): move the
loop machinery from `benchmarks/ifeval/` into generic `benchmarks/ensemble/`; define the
check-surface port (`check(answer) → {passed, feedback, satisfaction}`); advertise
`check_surface` in the `screamingface.benchmark.v1` manifest; retire the
`ifeval/lanl-ensemble` + `ifeval/self-corrective` registry variants; ship the IFEval
(`deterministic_check`), DRACO (`draco-pass.v1`), and HealthBench adapters, extracting the
`rubric_check` registry component at the third customer (deletion test: args only).

Design source: OME-796 issue body ("Design resolution 2026-08-14") + attached diagrams.
Ledger: `docs/work/2026-08-14-OME-796-corrective-loop-generalization.md`
