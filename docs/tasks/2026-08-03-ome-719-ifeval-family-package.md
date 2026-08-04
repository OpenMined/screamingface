---
ticket: OME-719
linear_url: https://linear.app/openmined/issue/OME-719/add-ifeval-family-package-to-url4-cloud-r0-deterministic-verifier-no
status: done
type: feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-03
closed:
---

# Add the IFEval benchmark family to url4-cloud — 541 instruction-following prompts graded by deterministic verifier code, no judge, $0 grading (R0)

New `benchmarks/ifeval/` package following draco's anatomy at `b6cc2a97`: definition
(content-hash REVISION, judge-free 2-level DAG, `required_models=()`), prepare (HF
`google/IFEval` @ pinned revision + offline NLTK corpus as asset), runtime, grading
(strict + loose over the vendored verifier), aggregate, vendored josejg verifier @
`0c495b2f` (Apache-2.0). Score = prompt-level strict accuracy; every case scored;
`failures=[]` always. Parent epic: `OME-718`.
