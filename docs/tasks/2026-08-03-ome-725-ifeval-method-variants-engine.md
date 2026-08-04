---
ticket: OME-725
linear_url: https://linear.app/openmined/issue/OME-725/merge-corrective-chain-into-ifeval-as-method-variants-engine
status: done
type: feature
priority: P1
labels: [url4-cloud, agentic, autonomous]
created: 2026-08-03
closed:
---

# Fold single-pass and corrective into one two-method ifeval benchmark so the registry stays one exam per entry, each method with its own revision

Owner decision: registry = real benchmarks only (`draco`, `ifeval`). Corrective chain
= ifeval's DEFAULT method (LANL reproduction); `single_pass` = the paper-comparable
variant. Shared `Benchmark` gains an optional methods tuple; manifest gains additive
method fields only when variants exist; REST `?method=`. Parent epic `OME-718`;
reworks `OME-721`'s uncommitted output.
