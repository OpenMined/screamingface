# Candidate shapes required by HealthBench, IFEval, and DRACO

Date: 2026-08-10

Scope: first-party implementation sources from
[PR 523](https://github.com/OpenMined/screamingface/pull/523) at
`5793efa2ee18efe707509966dde2b51ef9bb4edb`,
[PR 528](https://github.com/OpenMined/screamingface/pull/528) at
`c5e6142b3b2e6776794cc8aa9067643e49a8943d`, and the current client/DRACO tree at
`9c542563600396e09fe2c759cbf8d0b0f4965825`. The two PR heads were cloned under
`/tmp/sf-pr523-repo` and `/tmp/sf-pr528-repo`; the active worktree was not switched or modified.

## Conclusion

The benchmarks require two Candidate execution shapes, not two public Candidate abstractions:

1. **Whole Candidate:** invoke a `Model` once, or invoke a complete `Fusion` by running its
   members and then its synthesizer. Canonical IFEval, HealthBench, and DRACO use this shape.
2. **Structural Fusion:** invoke direct members separately and reuse the configured synthesizer
   model in a benchmark-owned selector/coaching role. IFEval LANL uses this shape.

The clean client surface can therefore remain:

```python
answerer = sf.Model("provider/answerer", prompt="...", params={...})
synthesizer = sf.Model("provider/synthesizer", prompt="...", params={...})
candidate = sf.Fusion([answerer, ...], synthesizer=synthesizer)
report = sf.evaluate(candidate, benchmark="...")
```

A string should remain convenient shorthand for `sf.Model(route)`, immediately normalized to a
`Model`. `Fusion` does not need its own `prompt=` or `params=` fields, and a separate public
`Judge` class would blur Candidate execution with benchmark grading.

The important semantic rule is role-specific prompt ownership:

- A member Model's answer prompt and parameters are Candidate-owned.
- A synthesizer Model's prompt is Candidate-owned when the whole Fusion synthesizes an answer.
- When a structural Benchmark binds that model as its selector/coaching synthesizer, the
  Benchmark owns the role instructions and does not reuse the ordinary synthesis prompt. The
  Candidate still supplies the model route and compatible generation parameters.
- A benchmark grading Judge is wholly Benchmark-owned: route, prompt, parameters, retries, and
  scoring. It is not the Fusion synthesizer.

That is not a special case for a named benchmark; it is a general projection rule selected from
the placeholders in a versioned Benchmark resource: `$candidate`, `$candidate_members`, and
`$candidate_synthesizer`.

## Evidence by benchmark

| Benchmark | Candidate execution | Prompt/model ownership | Grading |
|---|---|---|---|
| `healthbench/worst30` and `/smoke` | Invokes the whole Candidate once per Case, then fans the answer out over rubric items. A Model or complete Fusion therefore works. | Candidate answer/synthesis policy is researcher-owned. The Engine separately pins GPT-5.4, its vendored grader prompt, retrieval-off/max-token parameters, and malformed-reply retries. | One LLM Judge call per rubric item, then per-Case scoring and an unclipped mean. |
| `ifeval` | Invokes the whole Candidate once. A Fusion blends its member drafts and only that final answer is checked. | Candidate owns ordinary answer/synthesis prompts and model parameters; the Benchmark disables retrieval. | Deterministic strict and loose instruction checkers; no LLM grading Judge. |
| `ifeval/self-corrective` | Re-invokes the complete Candidate for answers and for self-authored coaching across a bounded three-attempt loop. | Candidate model policy remains active; the Benchmark supplies the retry/coaching task context and disables retrieval. | Same deterministic checker; aggregation selects the earliest strict-passing attempt. |
| `ifeval/lanl-ensemble` | Requires a Fusion with 2..4 direct Model members plus an explicit direct Model synthesizer. It invokes each member separately; the synthesizer is called only for a multi-passer tie, no-pass coaching, or a final exact tie. Selected output is always a member answer verbatim. | Member answer prompts/params remain Candidate-owned. The synthesizer contributes model route/params, while LANL owns its tie-break and coaching instructions; the ordinary blending prompt is irrelevant in this role. | Each draft is checked deterministically. A strict passer causes early exit; never-pass uses maximal strict-satisfaction with Judge tie-break only on exact ties. |
| `draco`, `/lite`, `/smoke` | Invokes the whole Candidate once per Case, then grades that answer. | Candidate owns answer/synthesis policy. DRACO independently pins its grading Judge model, prompt, retrieval policy, temperature, token cap, and per-pass seeds. | Benchmark-owned LLM Judge, per criterion and per configured pass, followed by deterministic aggregation. |

HealthBench's builder documents the exact whole-Candidate-then-Judge pipeline and invokes
`candidate(...)` once at the rubric fan-out boundary
([source](https://github.com/OpenMined/screamingface/blob/5793efa2ee18efe707509966dde2b51ef9bb4edb/apps/url4-cloud/src/url4_cloud/benchmarks/healthbench/definition.py#L137-L220)).
Its judge route and parameters are revision inputs
([source](https://github.com/OpenMined/screamingface/blob/5793efa2ee18efe707509966dde2b51ef9bb4edb/apps/url4-cloud/src/url4_cloud/benchmarks/healthbench/definition.py#L35-L74)).
The accompanying notebook explicitly calls the synthesis prompt the researcher's experiment
surface rather than part of the exam protocol
([source](https://github.com/OpenMined/screamingface/blob/5793efa2ee18efe707509966dde2b51ef9bb4edb/packages/screamingface/scripts/build_notebooks.py#L695-L728)).

Canonical IFEval invokes the whole Candidate once and declares deterministic strict/loose grading
([source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/definition.py#L47-L113)).
The LANL implementation instead binds each member expression separately
([source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L215-L292)),
passes benchmark-owned task instructions to `$candidate_synthesizer` for tie-breaking and coaching
([tie-break source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L295-L334),
[coaching source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L392-L468)),
and validates the 2..4 direct-member plus explicit-synthesizer shape before executing Cases
([source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/iterative_correction.py#L471-L538)).
The role prompts themselves are hashed protocol constants because the cited paper did not publish
them
([source](https://github.com/OpenMined/screamingface/blob/c5e6142b3b2e6776794cc8aa9067643e49a8943d/apps/url4-cloud/src/url4_cloud/benchmarks/ifeval/corrective_policy.py#L17-L86)).

Current DRACO similarly owns a separate grading Judge and its generation policy
([source](https://github.com/OpenMined/screamingface/blob/9c542563600396e09fe2c759cbf8d0b0f4965825/apps/url4-cloud/src/url4_cloud/benchmarks/draco/definition.py#L25-L75)),
then invokes the whole Candidate independently of those Judge calls
([source](https://github.com/OpenMined/screamingface/blob/9c542563600396e09fe2c759cbf8d0b0f4965825/apps/url4-cloud/src/url4_cloud/benchmarks/draco/definition.py#L174-L245)).

## Client implications

### Keep the domain concepts separate

- **Model**: immutable route plus answer/synthesis prompt and generation parameters.
- **Fusion**: ordered members plus an optional synthesizer Model.
- **Synthesizer**: a Candidate component. It normally writes a whole-Fusion answer, but a
  structural Benchmark may invoke its model in a benchmark-defined selection/coaching role.
- **Benchmark Judge**: an Engine-owned grading operation. Users do not configure it through the
  Candidate.

Calling the LANL component a public `judge=` would make HealthBench/DRACO's actual grading Judges
ambiguous. Keeping `synthesizer=` is therefore the cleaner cross-benchmark name.

### Preserve role projections in compilation

The client should compile a Fusion into reusable projections:

```text
$candidate              whole Fusion; member calls + synthesizer answer-writing prompt/params
$candidate_members      ordered direct members; each member's own prompt/params
$candidate_synthesizer  synthesizer route/params under Benchmark-owned role instructions
```

The current client already establishes the structural invariant that generation parameters are
retained but the blending prompt is removed from `$candidate_synthesizer`
([compiler](https://github.com/OpenMined/screamingface/blob/9c542563600396e09fe2c759cbf8d0b0f4965825/packages/screamingface/src/screamingface/_evaluation/candidate.py#L125-L156),
[contract test](https://github.com/OpenMined/screamingface/blob/9c542563600396e09fe2c759cbf8d0b0f4965825/packages/screamingface/tests/test_shape_adaptive_linking.py#L59-L76)).
Porting `Fusion.synthesizer` from `str` to normalized `Model` should preserve this behavior rather
than forwarding `synthesizer.prompt` blindly into every structural role.

### Make adaptation visible and fail before spend

The interface need not expose benchmark-specific knobs, but evaluation inspection should report:

- whether the Benchmark consumes the whole Candidate or structural Fusion components;
- whether the synthesizer is writing an answer or serving a Benchmark-owned role;
- which Candidate prompt is active or replaced;
- member count/type restrictions (LANL: 2..4 direct Models);
- Benchmark-enforced retrieval policy and Benchmark-owned Judge operations.

Shape mismatch, missing synthesizer, unsupported params, or unavailable Benchmark Judge models
should fail during planning/preflight, before any paid member call. Reports should then retain the
actual linked URL4 and operation metadata for reproducibility.

## Recommended invariant

**Researchers own Candidate policy; Benchmarks own evaluation protocol.** Candidate policy includes
the prompts and parameters used when Models answer or a Fusion synthesizes. Evaluation protocol
includes whether components are invoked whole or structurally, any role-specific selector/coaching
instructions, retrieval constraints, grading Judges, and scoring. A Benchmark may adapt a
configured synthesizer Model into a protocol role, but that adaptation must be deterministic,
revisioned, inspectable, and validated before spend.
