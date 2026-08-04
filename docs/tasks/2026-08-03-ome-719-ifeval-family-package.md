---
ticket: OME-719
linear_url: https://linear.app/openmined/issue/OME-719/add-ifeval-family-package-to-url4-cloud-r0-deterministic-verifier-no
status: in_progress
type: feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-03
closed:
---

# Add ifeval family package to url4-cloud (R0: deterministic verifier, no judge)

New `benchmarks/ifeval/` package following draco's anatomy at `b6cc2a97`: definition
(content-hash REVISION, judge-free 2-level DAG, `required_models=()`), prepare (HF
`google/IFEval` @ pinned revision + offline NLTK corpus as asset), runtime, grading
(strict + loose over the vendored verifier), aggregate, vendored josejg verifier @
`0c495b2f` (Apache-2.0). Score = prompt-level strict accuracy when every selected Case
produces a valid verifier record. A recordless Case aborts scoring with its positional
identity and sanitized in-band error; successful results carry `failures=[]` until the
SDK supports typed partial failures. Parent epic: `OME-718`.
