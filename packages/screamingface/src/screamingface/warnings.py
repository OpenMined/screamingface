"""Public warning categories for completed Evaluations with degraded quality."""


class EvaluationWarning(UserWarning):
    """An Evaluation planning or result condition needs the caller's attention."""


__all__ = ["EvaluationWarning"]
