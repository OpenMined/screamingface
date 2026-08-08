"""The live evaluate() panel: the Event fold and the HTML it renders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import screamingface as sf
from screamingface._ui.evaluation_state import _EvaluationProgress
from screamingface._ui.evaluation_view import (
    _compact,
    _duration,
    _money,
    evaluation_panel_html,
)

_START = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def envelope(sequence: int = 1, *, run_id: str = "run_1", offset: float = 0.0) -> dict[str, Any]:
    return {
        "id": f"event_{sequence}",
        "run_id": run_id,
        "sequence": sequence,
        "timestamp": _START + timedelta(seconds=offset),
        "source": f"/trace/{run_id}/node/root",
    }


def model_span(sequence: int, **overrides: Any) -> sf.events.Span:
    values: dict[str, Any] = {
        "name": "chat",
        "operation": "chat",
        "start": _START,
        "end": _START + timedelta(seconds=2),
        "request_model": "anthropic/claude-opus-4.8",
        "input_tokens": 1_000,
        "output_tokens": 250,
    }
    values.update(overrides)
    return sf.events.Span(**envelope(sequence), **values)


def test_structural_spans_never_count_as_model_work() -> None:
    progress = _EvaluationProgress(total_candidates=1)

    progress.observe(
        sf.events.Span(
            **envelope(1),
            name="TextNode",
            operation="TextNode",
            start=_START,
            end=_START + timedelta(seconds=1),
        )
    )

    assert progress.model_calls == 0
    assert progress.have_tokens is False


def test_model_spans_accumulate_calls_tokens_and_failures() -> None:
    progress = _EvaluationProgress(total_candidates=1)

    progress.observe(model_span(1))
    progress.observe(model_span(2, status="error", input_tokens=10, output_tokens=0))
    progress.observe(model_span(3, refusal="declined"))

    assert progress.model_calls == 3
    assert progress.failed_calls == 1
    assert progress.refusals == 1
    assert progress.input_tokens == 2_010
    assert progress.output_tokens == 500


def test_subtree_usage_is_ignored_so_cost_is_not_double_counted() -> None:
    progress = _EvaluationProgress(total_candidates=1)

    progress.observe(
        sf.events.Usage(
            **envelope(1),
            scope="self",
            provider="openrouter",
            model="m",
            pricing_version="v1",
            usage=sf.Usage(cost_usd=Decimal("0.25")),
        )
    )
    progress.observe(
        sf.events.Usage(
            **envelope(2),
            scope="subtree",
            provider="openrouter",
            model="m",
            pricing_version="v1",
            usage=sf.Usage(cost_usd=Decimal("99.00")),
        )
    )

    assert progress.cost_usd == Decimal("0.25")


def test_progress_tracks_candidates_and_reports_the_worst_terminal_status() -> None:
    progress = _EvaluationProgress(total_candidates=2)

    progress.observe(sf.events.Terminated(**envelope(1, run_id="run_1"), status="succeeded"))
    assert progress.running is True
    assert progress.status == "running"
    assert progress.fraction == 0.5

    progress.observe(sf.events.Terminated(**envelope(2, run_id="run_2"), status="failed"))

    assert progress.finished is True
    # A single failure must not be hidden by a sibling candidate that succeeded.
    assert progress.status == "failed"
    assert progress.fraction == 1.0


def test_elapsed_comes_from_event_timestamps_not_the_wall_clock() -> None:
    progress = _EvaluationProgress(total_candidates=1)

    progress.observe(sf.events.Started(**envelope(1, offset=0), url4="(@)!'hi'"))
    progress.observe(sf.events.Terminated(**envelope(2, offset=90), status="succeeded"))

    assert progress.elapsed_seconds == 90.0


def test_unknown_total_never_renders_a_fabricated_percentage() -> None:
    progress = _EvaluationProgress(total_candidates=None)
    progress.observe(model_span(1))

    assert progress.fraction is None
    assert progress.finished is False

    html = evaluation_panel_html(progress)

    assert "sf-eval__fill--sweep" in html
    assert "%'" not in html.split("sf-eval__track")[1].split("</div>")[0]


def test_panel_renders_live_totals_and_escapes_untrusted_text() -> None:
    progress = _EvaluationProgress(total_candidates=2)
    progress.observe(model_span(1, request_model="<script>alert(1)</script>"))
    progress.observe(
        sf.events.Usage(
            **envelope(2),
            scope="self",
            provider="openrouter",
            model="m",
            pricing_version="v1",
            usage=sf.Usage(cost_usd=Decimal("1.5")),
        )
    )

    html = evaluation_panel_html(progress, "GPQA <Diamond>")

    assert "Evaluating" in html
    assert "0/2 candidates" in html
    assert "1.0k / 250" in html
    assert "$1.50" in html
    assert "GPQA &lt;Diamond&gt;" in html
    assert "<script>" not in html


def test_panel_switches_to_a_completed_heading_and_surfaces_the_error() -> None:
    progress = _EvaluationProgress(total_candidates=1)
    progress.observe(
        sf.events.Terminated(
            **envelope(1),
            status="failed",
            error=sf.events.TerminationError(code="boom", message="engine exploded"),
        )
    )

    html = evaluation_panel_html(progress, "GPQA")

    assert "Evaluation complete" in html
    assert "sf-eval__state failed" in html
    assert "engine exploded" in html


def test_the_clock_advances_between_events_not_only_on_them() -> None:
    """A long model call emits no Events; a frozen clock would read as a hang."""

    from screamingface._ui.evaluation_view import _NotebookEvaluationView

    now = [100.0]
    view = _NotebookEvaluationView(1, "GPQA", clock=lambda: now[0], tick=False)
    view(sf.events.Started(**envelope(1), url4="(@)!'hi'"))
    first = view._html.value

    now[0] += 45.0  # time passes; no Event arrives
    view._html.value = view._render()

    assert "0.0s" in first
    assert "45.0s" in view._html.value


def test_a_finished_run_reports_the_span_it_took_not_the_wall_clock() -> None:
    from screamingface._ui.evaluation_view import _NotebookEvaluationView

    now = [100.0]
    view = _NotebookEvaluationView(1, "GPQA", clock=lambda: now[0], tick=False)
    view(sf.events.Started(**envelope(1, offset=0), url4="(@)!'hi'"))
    view(sf.events.Terminated(**envelope(2, offset=12), status="succeeded"))

    now[0] += 900.0  # the notebook sits open long after the run ended

    assert "12.0s" in view._render()


def test_live_figure_formatters_cover_large_small_and_long_running_values() -> None:
    """The panel stays compact without hiding sub-cent cost or long elapsed time."""

    assert _compact(2_000_000) == "2.0M"
    assert _money(Decimal("0.005")) == "$0.0050"
    assert _duration(65) == "1m 05s"
    assert _duration(3_665) == "1h 01m"


def test_panel_surfaces_failed_calls_and_subcent_cost() -> None:
    progress = _EvaluationProgress(total_candidates=1)
    progress.observe(model_span(1, status="error", input_tokens=2_000_000))
    progress.observe(
        sf.events.Usage(
            **envelope(2),
            scope="self",
            provider="openrouter",
            model="m",
            pricing_version="v1",
            usage=sf.Usage(cost_usd=Decimal("0.005")),
        )
    )

    html = evaluation_panel_html(progress)

    assert "1 · 1 failed" in html
    assert "2.0M / 250" in html
    assert "$0.0050" in html
