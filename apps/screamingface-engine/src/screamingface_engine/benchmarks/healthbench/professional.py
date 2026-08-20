"""The full HealthBench Professional exam — all 525 Cases, the official clipped score.

FEATURE: a HealthBench board whose number reads the same way as a published HealthBench
number, so a fan can put our leaderboard beside a paper and the comparison is fair.

This board is a second SELECTION over the answer key the image already bakes, not a second
bake: ``prepare.py`` emits every professional row as Case ids 1..525, and the worst-30%
board (``definition.py``) is itself only a filter over that same file. The two differ in
exactly two places — which Cases they serve, and whether the exam-level mean is clipped —
and share everything else through ``pins.py`` and ``exam.py``.

References:
    - simple-evals (protocol authority): https://github.com/openai/simple-evals
    - Dataset: https://huggingface.co/datasets/openai/healthbench
    - Paper: https://arxiv.org/abs/2505.08775 (HealthBench, Arora et al., 2025)
"""

from __future__ import annotations

from screamingface_engine.benchmarks.healthbench.exam import case_ids_sha, healthbench_benchmark
from screamingface_engine.benchmarks.healthbench.scoring import clipped_mean

BENCHMARK_ID = "healthbench-professional"
# INVARIANT: the pinned dataset revision holds exactly this many professional rows, and
# ``prepare.emit`` refuses to bake anything else — a dataset that grew or shrank would
# otherwise ship a differently-sized exam under this identity.
CASE_COUNT = 525
# WHY a contiguous range: Engine Case ids ARE the 1-based positions prepare.py numbers by,
# so "the whole exam" is every position. A gap here would silently make this a subset.
CASE_IDS = tuple(range(1, CASE_COUNT + 1))
PROTOCOL_REVISION = "professional-per-item-v1"
SCORING = "official-clipped-mean-v1"

PROFESSIONAL_EXAM, HEALTHBENCH_PROFESSIONAL = healthbench_benchmark(
    id=BENCHMARK_ID,
    title="HealthBench Professional",
    description=(
        "The complete 525-conversation HealthBench Professional exam. An AI judge grades "
        "each answer against a physician-written rubric; safety mistakes subtract points, "
        "so an individual case can score below zero. Benchmark score = the official "
        "HealthBench metric — the average of the 525 case scores, floored at 0 — so it "
        "lines up with published HealthBench numbers."
    ),
    case_ids=CASE_IDS,
    protocol_revision=PROTOCOL_REVISION,
    scoring=SCORING,
    mean=clipped_mean,
    # WHY the Case ids, not dataset row ids: this board's selection IS "every position in
    # the baked file", so the id list is the honest fingerprint of what it serves.
    selection_sha=case_ids_sha(CASE_IDS),
)

REVISION = PROFESSIONAL_EXAM.revision

__all__ = [
    "BENCHMARK_ID",
    "CASE_COUNT",
    "CASE_IDS",
    "HEALTHBENCH_PROFESSIONAL",
    "PROFESSIONAL_EXAM",
    "PROTOCOL_REVISION",
    "REVISION",
    "SCORING",
]
