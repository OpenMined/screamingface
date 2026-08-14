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

Engine substrate of the OME-796 design resolution (stage 1, delivered in PR #598): move
the loop machinery from `benchmarks/ifeval/` into generic `benchmarks/ensemble/`; define
the refusal-safe check-surface port
(`check({input, invocation}) → {passed, feedback, satisfaction, answer, invocation}`); advertise
`check_surface` in the `screamingface.benchmark.v1` manifest; retire the
`ifeval/lanl-ensemble` + `ifeval/self-corrective` registry variants; and ship the IFEval
deterministic adapter. DRACO and HealthBench adapters are owned by OME-829 and OME-830.
The remaining Engine-side acceptance item is the shared Candidate execution-provenance
transport that publishes corrective-loop `stop_reason` and `rounds_executed` without
making any Benchmark adapter understand loop control flow.

Design source: OME-796 issue body ("Design resolution 2026-08-14") + attached diagrams.
Ledger: `docs/work/2026-08-14-OME-827-ensemble-module-check-port.md`
