"""HealthBench worst-30% as an Engine-owned Benchmark definition.

FEATURE: the entry challenge — open-source Fusions try to beat our open-fusion baseline
on the 157 hardest HealthBench Professional rows. Protocol authority is OpenAI
simple-evals ``healthbench_eval.py`` (per-rubric-item LLM judging); scoring is the
challenge metric (UNCLIPPED mean), deliberately not the official clipped HealthBench
score — every description below says so. The board that DOES report the official score is
``professional.py``; what the two share lives in ``pins.py`` and ``exam.py``.

References:
    - simple-evals (protocol authority): https://github.com/openai/simple-evals
    - Dataset: https://huggingface.co/datasets/openai/healthbench
    - Paper: https://arxiv.org/abs/2505.08775 (HealthBench, Arora et al., 2025)
"""

from __future__ import annotations

from screamingface_engine.benchmarks.healthbench.exam import healthbench_benchmark
from screamingface_engine.benchmarks.healthbench.scoring import unclipped_mean
from screamingface_engine.benchmarks.healthbench.subset import WORST30_CASE_IDS, subset_sha

BENCHMARK_ID = "healthbench-worst30"
CASE_COUNT = len(WORST30_CASE_IDS)
PROTOCOL_REVISION = "worst30-per-item-v2"  # v2: aggregate intent carries the selected count
SCORING = "unclipped-mean-v1"

WORST30_EXAM, HEALTHBENCH_WORST30 = healthbench_benchmark(
    id=BENCHMARK_ID,
    title="HealthBench Worst-30% Challenge",
    description=(
        "The 157 hardest conversations from HealthBench Professional — the 30% that "
        "top models score worst on. An AI judge grades each answer against a "
        "physician-written rubric; safety mistakes subtract points, so per-case scores "
        "can be negative. Challenge score = plain average of the 157 case scores, "
        "negatives kept (the official HealthBench score floors negative averages at 0, "
        "which would flatten this hard subset to all-zeros)."
    ),
    case_ids=WORST30_CASE_IDS,
    protocol_revision=PROTOCOL_REVISION,
    scoring=SCORING,
    mean=unclipped_mean,
    # WHY the HF ids, not the Case ids: this board's identity IS the frozen worst-30%
    # selection out of the dataset, so its fingerprint is taken over the dataset's own
    # stable row ids (subset.py).
    selection_sha=subset_sha(),
)

REVISION = WORST30_EXAM.revision
ROUTE_PREFIX = WORST30_EXAM.routes.prefix
CASES_ROUTE = WORST30_EXAM.routes.cases
TASKS_ROUTE = WORST30_EXAM.routes.tasks
VERDICT_ROUTE = WORST30_EXAM.routes.verdict
RUBRIC_EVALUATION_ROUTE = WORST30_EXAM.routes.rubric_evaluation
CASE_EVALUATION_ROUTE = WORST30_EXAM.routes.case_evaluation
AGGREGATE_ROUTE = WORST30_EXAM.routes.aggregate
CHECK_SURFACE_ROUTE = WORST30_EXAM.routes.check_surface

__all__ = [
    "AGGREGATE_ROUTE",
    "BENCHMARK_ID",
    "CASES_ROUTE",
    "CASE_COUNT",
    "CASE_EVALUATION_ROUTE",
    "CHECK_SURFACE_ROUTE",
    "HEALTHBENCH_WORST30",
    "PROTOCOL_REVISION",
    "REVISION",
    "ROUTE_PREFIX",
    "RUBRIC_EVALUATION_ROUTE",
    "SCORING",
    "TASKS_ROUTE",
    "VERDICT_ROUTE",
    "WORST30_EXAM",
]
