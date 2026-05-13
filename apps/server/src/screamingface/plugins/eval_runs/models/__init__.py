"""eval_runs Tortoise models."""

from __future__ import annotations

from screamingface.plugins.eval_runs.models.eval_question import (
    BaseEvalQuestion,
    EvalQuestion,
)
from screamingface.plugins.eval_runs.models.eval_run import BaseEvalRun, EvalRun

__all__ = ["BaseEvalQuestion", "BaseEvalRun", "EvalQuestion", "EvalRun"]
