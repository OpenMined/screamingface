"""Public warning categories for completed Evaluations with degraded quality."""


class EvaluationWarning(UserWarning):
    """An Evaluation completed, but a reported quality condition needs attention."""


__all__ = ["EvaluationWarning"]
