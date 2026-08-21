"""Partial-score advisory policy at the Scoreboard write boundary."""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

from screamingface._environment import running_in_notebook
from screamingface._notices import PARTIAL_SUBMISSION_NOTICE, ClientNotice
from screamingface._ui.notice_view import display_notebook_notice
from screamingface.report import CandidateResult
from screamingface.warnings import EvaluationWarning

_SDK_PACKAGE_ROOT = str(Path(__file__).resolve().parents[1])


def prepare_submission_notice(candidate_result: CandidateResult) -> ClientNotice | None:
    """Warn before a headless write, or reserve rich output until a notebook write succeeds."""

    if not _is_partial_submission(candidate_result):
        return None
    if running_in_notebook():
        return PARTIAL_SUBMISSION_NOTICE
    warnings.warn(
        PARTIAL_SUBMISSION_NOTICE.message,
        EvaluationWarning,
        skip_file_prefixes=(_SDK_PACKAGE_ROOT,),
    )
    return None


def display_submission_notice(notice: ClientNotice | None) -> None:
    """Publish a reserved notebook notice after the Scoreboard confirms the write."""

    if notice is not None:
        try:
            display_notebook_notice(notice)
        except Exception:
            # INVARIANT: presentation happens after persistence and therefore cannot raise;
            # losing the returned score id would leave the caller unable to recover the write.
            print(notice.message, file=sys.stderr)


def _is_partial_submission(candidate_result: CandidateResult) -> bool:
    # INVARIANT: coverage measures grading within selected Cases, so a limited Evaluation
    # can have coverage=1.0 while still omitting most of its Benchmark.
    return (
        len(candidate_result.cases) != candidate_result.benchmark.case_count
        or candidate_result.coverage < 1.0
    )


__all__: list[str] = []
