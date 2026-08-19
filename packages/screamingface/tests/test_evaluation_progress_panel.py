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


def test_panel_renders_separate_benchmark_native_progress_for_each_candidate() -> None:
    first_url = "(@)!'first'"
    second_url = "(@)!'second'"
    progress = _EvaluationProgress(
        total_candidates=2,
        case_count=157,
        candidate_urls=frozenset({first_url, second_url}),
        candidate_names_by_url={first_url: "panel", second_url: "solo"},
    )
    progress.observe(sf.events.Started(**envelope(1, run_id="run_1"), url4=first_url))
    progress.observe(sf.events.Started(**envelope(1, run_id="run_2"), url4=second_url))
    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2, run_id="run_1"),
            benchmark_id="healthbench-worst30",
            benchmark_revision="revision",
            total_cases=157,
            queued_cases=112,
            running_candidate_cases=2,
            grading_cases=3,
            complete_cases=40,
            scored_cases=40,
            coverage=0.2548,
            provisional_score=-0.42,
        )
    )

    first_html = evaluation_panel_html(progress, "healthbench-worst30")
    assert "panel" in first_html and "solo" in first_html
    assert first_html.count("0/157 complete · 157 queued · 0 scored") == 1
    assert "sf-eval__case-fill" in first_html

    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2, run_id="run_2"),
            benchmark_id="healthbench-worst30",
            benchmark_revision="revision",
            total_cases=157,
            queued_cases=143,
            running_candidate_cases=1,
            grading_cases=1,
            complete_cases=12,
            scored_cases=12,
            coverage=0.0764,
            provisional_score=0.11,
        )
    )

    html = evaluation_panel_html(progress, "healthbench-worst30")

    assert "panel" in html and "solo" in html
    assert "40/157 complete · 2 running Candidate · 3 grading · 112 queued · 40 scored" in html
    assert "12/157 complete · 1 running Candidate · 1 grading · 143 queued · 12 scored" in html
    assert "score so far · -0.42" in html
    assert "score so far · 0.11" in html
    assert "coverage · 25.5%" in html
    assert "55/314" not in html


def test_no_progress_events_preserve_the_existing_candidate_level_fallback() -> None:
    url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=1,
        case_count=10,
        candidate_urls=frozenset({url4}),
        candidate_names_by_url={url4: "candidate"},
    )
    progress.observe(sf.events.Started(**envelope(1), url4=url4))

    html = evaluation_panel_html(progress, "ifeval")

    assert "sf-eval__track" in html
    assert "<div class='sf-eval__candidates'>" not in html


def test_case_progress_styles_support_light_and_dark_notebook_themes() -> None:
    progress = _EvaluationProgress(
        total_candidates=1,
        case_count=1,
        candidate_urls=frozenset({"(@)!'candidate'"}),
        candidate_names_by_url={"(@)!'candidate'": "candidate"},
    )
    progress.observe(sf.events.Started(**envelope(1), url4="(@)!'candidate'"))
    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2),
            benchmark_id="ifeval",
            benchmark_revision="revision",
            total_cases=1,
            queued_cases=1,
            running_candidate_cases=0,
            grading_cases=0,
            complete_cases=0,
            scored_cases=0,
            coverage=0.0,
            provisional_score=None,
        )
    )

    html = evaluation_panel_html(progress, "ifeval")

    assert ".vscode-dark .sf-ui" in html
    assert ".vscode-light .sf-ui" in html
    assert "sf-eval__case-fill" in html


def test_panel_renders_no_fabricated_score_before_a_case_is_gradeable() -> None:
    url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=1,
        candidate_urls=frozenset({url4}),
        candidate_names_by_url={url4: "candidate"},
    )
    progress.observe(sf.events.Started(**envelope(1), url4=url4))
    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2),
            benchmark_id="ifeval",
            benchmark_revision="revision",
            total_cases=2,
            queued_cases=1,
            running_candidate_cases=1,
            grading_cases=0,
            complete_cases=0,
            scored_cases=0,
            coverage=0.0,
            provisional_score=None,
        )
    )

    html = evaluation_panel_html(progress, "ifeval")

    assert "score · awaiting first grade" in html
    assert "score so far · 0" not in html
    assert "sf-eval__case-active" in html
    assert "prefers-reduced-motion:reduce" in html


def test_panel_calls_out_grading_before_the_first_case_grade_is_available() -> None:
    url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=1,
        candidate_urls=frozenset({url4}),
        candidate_names_by_url={url4: "candidate"},
    )
    progress.observe(sf.events.Started(**envelope(1), url4=url4))
    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2),
            benchmark_id="draco",
            benchmark_revision="revision",
            total_cases=1,
            queued_cases=0,
            running_candidate_cases=0,
            grading_cases=1,
            complete_cases=0,
            scored_cases=0,
            coverage=0.0,
            provisional_score=None,
        )
    )

    html = evaluation_panel_html(progress, "draco")

    assert "score · grading in progress" in html
    assert "score · awaiting first grade" not in html


def test_transport_success_with_unscored_cases_is_presented_as_incomplete() -> None:
    url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=1,
        candidate_urls=frozenset({url4}),
        candidate_names_by_url={url4: "candidate"},
    )
    progress.observe(sf.events.Started(**envelope(1), url4=url4))
    progress.observe(
        sf.BenchmarkProgress(
            **envelope(2),
            benchmark_id="draco",
            benchmark_revision="revision",
            total_cases=1,
            queued_cases=0,
            running_candidate_cases=0,
            grading_cases=0,
            complete_cases=1,
            scored_cases=0,
            coverage=0.0,
            provisional_score=None,
        )
    )
    progress.observe(sf.events.Terminated(**envelope(3), status="succeeded"))

    html = evaluation_panel_html(progress, "draco")

    assert "Evaluation complete" in html
    assert "sf-eval__state incomplete" in html
    assert "score unavailable" in html
    assert "evaluation incomplete" in html


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


def test_closing_a_failed_evaluation_stops_the_notebook_ticker() -> None:
    from screamingface._ui.evaluation_view import _NotebookEvaluationView

    view = _NotebookEvaluationView(1, "GPQA", tick=False)

    view.close()

    assert view._done.is_set()


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


def test_phase_progress_distinguishes_candidate_work_from_benchmark_grading() -> None:
    candidate_model = "openrouter/anthropic/claude-opus-4.8"
    progress = _EvaluationProgress(
        total_candidates=1,
        candidate_models=frozenset({candidate_model}),
    )

    assert "Starting evaluation" in evaluation_panel_html(progress, "Fixture Benchmark")

    progress.observe(sf.events.Started(**envelope(1), url4="(@)!'hi'"))
    assert progress.activity == "Running candidate"

    progress.observe(model_span(2, request_model=candidate_model))
    assert progress.activity == "Running candidate · 1 model call completed"

    progress.observe(
        model_span(
            3,
            request_model="openrouter/google/gemini-3.1-pro-preview",
        )
    )
    assert progress.activity == "Grading benchmark · 1 model call completed"

    progress.observe(sf.events.Terminated(**envelope(4), status="succeeded"))
    html = evaluation_panel_html(progress, "Fixture Benchmark")

    assert progress.activity == "Evaluation finished"
    assert "phase · Evaluation finished" in html
    assert "evaluation finished" in html


def test_evaluation_only_says_finished_after_every_candidate_terminates() -> None:
    progress = _EvaluationProgress(total_candidates=2)

    progress.observe(sf.events.Terminated(**envelope(1, run_id="run_1"), status="succeeded"))

    assert progress.activity == "Running candidates · 1/2 finished"
    assert all(text != "evaluation finished" for _, _, text in progress.feed)

    progress.observe(sf.events.Terminated(**envelope(2, run_id="run_2"), status="succeeded"))

    assert progress.activity == "Evaluation finished"
    assert progress.feed[0][2] == "evaluation finished"


def test_parallel_candidate_starts_create_one_evaluation_start_entry() -> None:
    progress = _EvaluationProgress(total_candidates=2)

    progress.observe(sf.events.Started(**envelope(1, run_id="run_1"), url4="(@)!'one'"))
    progress.observe(sf.events.Started(**envelope(1, run_id="run_2"), url4="(@)!'two'"))

    assert [text for _, _, text in progress.feed] == ["evaluation started"]


def test_live_feed_uses_arrival_time_when_engine_event_timestamps_do_not_advance() -> None:
    from screamingface._ui.evaluation_view import _NotebookEvaluationView

    now = [100.0]
    view = _NotebookEvaluationView(2, "DRACO", clock=lambda: now[0], tick=False)
    view(sf.events.Started(**envelope(1, run_id="run_1"), url4="(@)!'one'"))

    now[0] += 14
    view(sf.events.Terminated(**envelope(2, run_id="run_1"), status="succeeded"))

    assert "0:14" in view._html.value
    assert "candidate 1/2 finished" in view._html.value


def test_determinate_progress_is_static_and_unavailable_metrics_are_not_zero() -> None:
    progress = _EvaluationProgress(total_candidates=2)
    progress.observe(sf.events.Terminated(**envelope(1), status="succeeded"))

    html = evaluation_panel_html(progress)

    assert "width:50.0%" in html
    assert "sf-eval__fill--live" not in html
    assert "<div class='sf-eval__stat-v'>—</div>" in html


def test_nested_url4_termination_does_not_complete_a_candidate() -> None:
    candidate_url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=1,
        candidate_urls=frozenset({candidate_url4}),
    )
    progress.observe(sf.events.Started(**envelope(1), url4=candidate_url4))
    nested = envelope(2, run_id="run_1")
    nested["source"] = "/trace/run_1/node/nested"

    progress.observe(
        sf.events.Terminated(
            **nested,
            status="succeeded",
        )
    )

    assert progress.completed == 0
    assert progress.fraction == 0.0

    progress.observe(sf.events.Terminated(**envelope(3), status="succeeded"))

    assert progress.completed == 1
    assert progress.finished is True


def test_candidate_completion_surfaces_the_engine_cache_summary() -> None:
    candidate_url4 = "(@)!'candidate'"
    progress = _EvaluationProgress(
        total_candidates=2,
        candidate_urls=frozenset({candidate_url4}),
    )
    progress.observe(sf.events.Started(**envelope(1), url4=candidate_url4))
    progress.observe(
        sf.events.Log(
            **envelope(2),
            severity_number=9,
            severity_text="INFO",
            body="gateway response cache: 21 hit, 0 miss, 0 bypass",
            attributes={"cache.hits": 21, "cache.misses": 0, "cache.bypasses": 0},
        )
    )

    progress.observe(sf.events.Terminated(**envelope(3), status="succeeded"))

    assert progress.feed[0][2] == "candidate 1/2 finished · cache: 21 hits"
