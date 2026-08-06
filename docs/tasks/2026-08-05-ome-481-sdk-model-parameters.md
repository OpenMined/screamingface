---
id: OME-481
linear_url: https://linear.app/openmined/issue/OME-481
status: blocked
type: feature
priority:
labels: [screamingface-client, autonomous, agentic]
created: 2026-08-05
closed:
---

# OME-481 — typed model parameters and Evaluation preflight

The SDK reads the Engine's model summaries and profile-bound parameter contracts. Researchers can
inspect a model before composing a Candidate, while an Evaluation with explicit generation
parameters fails before execution when a value is unavailable or invalid for that model/profile.

## Scope

- Preserve `supported_parameters` and `supported_tools` in `models.list()`.
- Add typed synchronous, asynchronous, and lazy-default `models.get(model_id)`.
- Decode the versioned AI Gateway parameter document into immutable SDK values.
- Preflight only explicit Model/Fusion parameter overrides, once per distinct model.
- Keep Recipe values network-free and Benchmark-independent.

## Out of scope

- AI Gateway, URL4 Cloud, URL4, Benchmark, provider, or profile-policy changes.
- A second SDK parameter schema or a model-specific allowlist.
- Structured Candidate parameter values; the current URL4 parameter surface remains scalar-only.

Spec: `docs/spec/2026-08-05-OME-481-sdk-model-parameters.md`

Plan: `docs/plan/2026-08-05-OME-481-sdk-model-parameters.md`

Ledger: `docs/work/2026-08-05-OME-481-sdk-model-parameters.md`
