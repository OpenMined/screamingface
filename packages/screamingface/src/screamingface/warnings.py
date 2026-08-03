"""Public warning categories for completed Evaluations with degraded quality."""


class EvaluationWarning(UserWarning):
    """An Evaluation completed, but a reported quality condition needs attention."""


class CoverageWarning(EvaluationWarning):
    """A Benchmark score was computed from less grading coverage than its declared target."""


__all__ = ["CoverageWarning", "EvaluationWarning"]
