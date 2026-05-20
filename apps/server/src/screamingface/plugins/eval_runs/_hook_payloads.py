"""TypedDict payload shapes for the four eval-runs lifecycle hooks.

These are the wire contract between emitters (url4-executor, python-runner)
and the subscriber (eval-runs). Defined here because eval-runs owns the
domain — the emitters just produce events that match these shapes.

Hook names (constants below) are imported by both sides to avoid drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

HOOK_RUN_STARTED = "eval.run.started"
HOOK_RUN_FINISHED = "eval.run.finished"
HOOK_RUN_FAILED = "eval.run.failed"
HOOK_QUESTION_CHECKED = "eval.question.checked"


class RunStartedPayload(TypedDict):
    run_id: str
    spec_name: str
    url4_expression: str
    started_at: datetime


class RunFinishedPayload(TypedDict):
    run_id: str
    finished_at: datetime


class RunFailedPayload(TypedDict):
    run_id: str
    finished_at: datetime
    error: str


class QuestionCheckedPayload(TypedDict):
    run_id: str
    question: str
    expected: str
    predicted: str | None
    correct: bool | None
    raw_output: str | None
    error: str | None
