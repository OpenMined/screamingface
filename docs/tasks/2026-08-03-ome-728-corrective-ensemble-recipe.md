---
ticket: OME-728
linear_url: https://linear.app/openmined/issue/OME-728/add-the-correctiveensemble-recipe-to-the-sdk
status: done
type: feature
priority: P1
labels: [py-screamingface, agentic, autonomous]
created: 2026-08-03
closed:
---

# Ship sf.CorrectiveEnsemble — the paper's verifying ensemble (members × attempts, checker feedback, judge tie-break) as a first-class candidate

`sf.CorrectiveEnsemble(members, judge=...)` — the Skurikhin et al. verifying
ensemble as a candidate, compiled against the manifest's `actions` map, run on the
frozen `single_pass` exam. Notebook 07 e2e section. Blocked by `OME-727`.
Parent `OME-718`.
