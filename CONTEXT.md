# ScreamingFace

ScreamingFace evaluates candidate Models and Fusions against reproducible research benchmarks.

## Language

**Evaluation**:
The complete process of evaluating one or more Candidates against one Benchmark.
_Avoid_: Run, execution

**Benchmark**:
An Engine-owned evaluation protocol comprising Cases, Candidate Invocations, Grading, and Aggregation.
_Avoid_: Test, dataset

**Benchmark Family**:
A named group of Benchmark Variants that share research material or deterministic runtime assets; a Family is organizational and is not itself executable.
_Avoid_: Benchmark directory, manifest

**Benchmark Variant**:
One independently identified and revisioned Benchmark protocol within a Benchmark Family. The canonical protocol is also a Variant.
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

**Aggregation**:
The phase that combines Case grades into a Candidate’s Benchmark metrics.
_Avoid_: Reduction
