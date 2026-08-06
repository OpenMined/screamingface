---
id: OME-712
linear_url: https://linear.app/openmined/issue/OME-712/run-draco-end-to-end-as-a-url4-expression-on-the-runner-path
status: Todo
type: feature
priority: P2
labels: [url4-cloud, autonomous, agentic]
created: 2026-07-31
closed:
---

# Run DRACO end to end as a URL4 expression on the Runner path

Run DRACO as an ordinary URL4 expression through a Kubernetes Runner Job, AI Gateway, and the
provider. The judge is an explicit URL4 model call; deterministic Aggregation never calls a model.
Benchmark artifacts are addressable inside the Runner world, weighted rubrics stay private to the
benchmark image, and the control plane remains dataset-free.

The live issue explicitly separates this URL4-native path from the SDK/Engine registry architecture
and leaves convergence as an owner decision. Its acceptance contract is a hand-checked scored
`CandidateResult` plus fail-closed behavior when no score can be established. Any paid live run
requires explicit budget approval immediately before execution.

As of 2026-08-04 Linear is the status authority and reports **Pick Immediately**. Draft PR
[#464](https://github.com/OpenMined/screamingface/pull/464) is attached, but its head also contains
architecture convergence, provider discovery, cancellation, Gateway bootstrap, and deployment work
outside the issue's stated landing.

The local certification verdict is **blocked, not merge-ready**. Zero scored Cases currently return
success; Candidate code can reach Benchmark-private routes and unrestricted absolute-URL I/O; the
derived ACR Benchmark image is not published; and no hand-checked deployed scored result exists.
This does not change Linear status by itself. The certification and proposed split are recorded in:

- `docs/spec/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/plan/2026-08-04-OME-712-benchmark-runtime-certification.md`
- `docs/work/2026-08-04-OME-712-benchmark-runtime-certification.md`

Local remediation after certification fixes the zero-Case false success and dev ACR Benchmark-image
publication. Those changes remain uncommitted and are not yet present on PR #464.
