"""Pinned answer, synthesis, and judge instructions for DRACO."""

ANSWER_INSTRUCTIONS = """Answer the research question completely.
Compare the estimators and their assumptions precisely, address pre-trend testing, and cite
specific papers and evidence where useful."""

SYNTHESIS_INSTRUCTIONS = """Synthesize one comprehensive answer to the research question from
the panel answers. Preserve the strongest specific claims, evidence, citations, and arguments;
resolve disagreements in favor of the better-supported claim; cover details contributed by only
one member; and do not introduce facts that no panel member supplied. Return only the unified
prose answer."""

JUDGE_INSTRUCTIONS = """You are evaluating a response for a given query against a single \
criterion.

You will receive the response to evaluate, a single criterion to check, and a \
<criterion_type> field indicating if the criterion is positive or negative.

For both criterion types, determine whether the thing described is present in the response:
- Positive criterion: MET means the desired requirement is satisfied.
- Negative criterion: MET means the described error is present. A warning against the error is \
UNMET.

Be strict about factual accuracy but flexible about wording. Accept a requirement satisfied by \
clear implication. When a criterion requires an immediate or unconditional action, a conditional \
recommendation does not satisfy it.

Return only raw JSON in this exact shape:
{"explanation":"Brief evidence for the verdict.","criterion_status":"MET"}

criterion_status must be exactly "MET" or "UNMET". Do not use Markdown fences or add prose \
outside the JSON object."""

__all__ = ["ANSWER_INSTRUCTIONS", "JUDGE_INSTRUCTIONS", "SYNTHESIS_INSTRUCTIONS"]
