# ScreamingFace

ScreamingFace evaluates candidate Models and Fusions against reproducible research benchmarks.

## Language

**Evaluation**:
The complete process of evaluating one or more Candidates against one Benchmark.
_Avoid_: Run, execution

**Benchmark**:
One independently identified and revisioned Engine-owned evaluation protocol comprising Cases,
Candidate Invocations, Grading, and Aggregation.
_Avoid_: Test, dataset, family

**Benchmark Variant**:
An alternative Benchmark protocol related to a canonical default Benchmark. A Variant has its
own identity and revision even when it shares Cases or Grading material with the default.
_Avoid_: Method, mode, option

**Candidate**:
A Model or Fusion submitted to a Benchmark for evaluation.
_Avoid_: Ensemble when referring to both Models and Fusions

**Candidate Invocation**:
One request by a Benchmark for a Candidate answer; a Case may require multiple ordered Candidate Invocations.
_Avoid_: Model call, because a Candidate may be a Fusion

**Case**:
One Benchmark item containing an input, its grading material, and optional metadata.
_Avoid_: Row, sample

**Case Result**:
The completed record of one Case for one Candidate: its exact input and output, Case Grade,
failures, and non-secret Benchmark metadata.
_Avoid_: Artifact, row result

**Case Grade**:
The Benchmark-produced score, metrics, and ordered Checks for one Case. A failed Case may have no
Case Grade.
_Avoid_: Result when referring specifically to grading

**Check**:
One named grading requirement inspected within a Case Grade, together with the Evidence used to
evaluate it. A DRACO rubric criterion and an IFEval instruction constraint are both Checks.
_Avoid_: Criterion when speaking across Benchmarks

**Evidence**:
One ordered, attributable observation used by a Check, including its normalized outcome and exact
raw output when one exists. Evidence may be produced by a Judge or a deterministic verifier.
_Avoid_: Verdict when speaking across Benchmarks

**Rubric**:
The Case-owned criteria used to grade a Candidate answer.
_Avoid_: Reference when the grading material is specifically a rubric

**Load**:
The phase that obtains the Benchmark Cases selected for an Evaluation.

**Run**:
The phase in which a Candidate produces an answer for each loaded Case.
_Avoid_: Generation when naming the public lifecycle stage

**Grading**:
The phase that judges a Candidate answer against its Case Rubric and produces a Case grade.
_Avoid_: Judging

**Judge**:
A Model called within Grading to produce evidence or verdicts; it is not an Evaluation phase.
_Avoid_: Judge stage

**Benchmark-owned Model**:
A Model fixed by the Benchmark protocol, such as DRACO's grading Judge. Changing it changes the
Benchmark revision.
_Avoid_: Candidate Model, user-selected Judge

**Candidate-owned Model**:
A Model submitted as part of a Candidate, including a Fusion member or synthesizer. Changing it
changes the Candidate rather than the Benchmark.
_Avoid_: Benchmark dependency, pinned Judge

**Aggregation**:
The phase that combines Case grades into a Candidate’s Benchmark metrics.
_Avoid_: Reduction
