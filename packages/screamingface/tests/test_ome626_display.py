"""OME-626 — widget-like reprs for Model/Fusion/Benchmark and catalog views.

FEATURE: notebook rich display for the core SDK objects and engine catalog.
STORY: as a researcher, I evaluate a Model/Fusion/Benchmark in a cell (or call
sf.models.view()/sf.benchmarks.view()) and see a branded card/catalog instead of a bare repr.
INVARIANT: cards render only real advertised fields — never fabricated price/context/ability.
"""

from __future__ import annotations

import json
from html import escape

import ipywidgets as widgets
import pytest

import screamingface as sf
from screamingface import _profile

# Metric words the design mock shows but the engine does NOT advertise. They must never
# appear in real output — displaying them would fabricate data (INVARIANT above).
_FABRICATED = ("context window", "ability", "tok/s", "tokens/s", "$/m", "price")


def _registry() -> dict[str, object]:
    return {
        "schema": "screamingface.registry.v1",
        "response_schemas": [
            "screamingface.recipe-result.v1",
            "screamingface.case-grade.v1",
            "screamingface.report.v1",
        ],
        "limits": {"max_request_target_bytes": 61440},
        "providers": [
            {"id": "codex", "display_name": "OpenAI Codex", "auth_methods": ["oauth"]},
            {"id": "gemini", "display_name": "Google Gemini", "auth_methods": ["api_key"]},
        ],
        "models": [
            {
                "id": "codex/gpt-5.5",
                "provider": "codex",
                "supported_tools": [],
                "required_connections": [],
            },
            {
                "id": "gemini/2.5-flash",
                "provider": "gemini",
                "supported_tools": ["web_search", "web_fetch"],
                "required_connections": [],
            },
        ],
        "benchmarks": [
            {
                "id": "gpqa@1",
                "title": "GPQA Diamond",
                "cases_route": "/benchmarks/gpqa/1/cases",
                "grader": {"kind": "exact_choice", "route": "/graders/exact-choice/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": [],
                "max_tool_calls": None,
                "tool_policy_route": None,
                "candidate_route": None,
                "candidate_aggregator_route": None,
            },
            {
                "id": "draco@1",
                "title": "DRACO",
                "cases_route": "/benchmarks/draco/1/cases",
                "grader": {"kind": "exact_choice", "route": "/graders/exact-choice/1"},
                "aggregator": {"kind": "mean", "route": "/aggregators/mean/1"},
                "tools": ["web_search", "web_fetch"],
                "max_tool_calls": 12,
                "tool_policy_route": "/benchmarks/draco/1/tool-policy",
                "candidate_route": None,
                "candidate_aggregator_route": None,
            },
        ],
        "reducers": [{"id": "majority_vote", "route": "/reducers/majority-vote/1"}],
    }


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_profile, "_get_text", lambda _path: json.dumps(_registry()))
    sf.config(engine="http://127.0.0.1:4404")


def _walk(widget: widgets.Widget) -> tuple[widgets.Widget, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def _html_text(widget: widgets.Widget) -> str:
    return "\n".join(
        item.value
        for item in _walk(widget)
        if isinstance(item, widgets.HTML) and isinstance(item.value, str)
    )


# --- object cards -------------------------------------------------------------------------


def test_model_repr_html_shows_real_fields_and_no_fabricated_metrics() -> None:
    model = sf.Model(
        "gemini/2.5-flash", name="flash-1", prompt="Solve it.", params={"temperature": 0.5}
    )

    html = model._repr_html_()

    assert "class='sf-ui" in html
    assert "gemini/2.5-flash" in html
    assert "flash-1" in html
    assert "Solve it." in html
    assert "temperature" in html and "0.5" in html
    assert "gemini" in html  # provider derived from the route prefix
    assert escape(model.url4) in html  # the recipe is the identity
    lowered = html.lower()
    for banned in _FABRICATED:
        assert banned not in lowered


def test_model_card_escapes_injected_text() -> None:
    model = sf.Model("gemini/2.5-flash", prompt="<script>alert(1)</script>")

    html = model._repr_html_()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_model_repr_text_is_concise() -> None:
    model = sf.Model("gemini/2.5-flash", name="flash-1")

    text = repr(model)

    assert "Model" in text
    assert "gemini/2.5-flash" in text
    assert "<div" not in text  # a text repr, not HTML


def test_fusion_repr_html_shows_members_reducer_and_recipe() -> None:
    a = sf.Model("gemini/2.5-flash", name="a")
    b = sf.Model("codex/gpt-5.5", name="b")
    fusion = sf.Fusion("trio", members=[a, b], reducer=sf.reducers.MajorityVote())

    html = fusion._repr_html_()

    assert "class='sf-ui" in html
    assert "trio" in html
    assert "gemini/2.5-flash" in html
    assert "codex/gpt-5.5" in html
    assert "majority" in html.lower()  # reducer kind, humanized
    assert escape(fusion.url4) in html
    lowered = html.lower()
    for banned in _FABRICATED:
        assert banned not in lowered


def test_fusion_repr_html_labels_nested_fusion() -> None:
    inner = sf.Fusion("inner", members=["gemini/2.5-flash"], reducer=sf.reducers.MajorityVote())
    outer = sf.Fusion("outer", members=[inner, "codex/gpt-5.5"], reducer=sf.reducers.MajorityVote())

    html = outer._repr_html_()

    assert "inner" in html
    assert "outer" in html


def test_benchmark_repr_html_shows_id_title_grader_aggregator_tools() -> None:
    bench = sf.Benchmark(
        "mini@1",
        title="Mini Suite",
        cases=[sf.Case("c1", "2+2?", reference="4")],
        grader=sf.graders.ExactChoice(),
        tools=[sf.tools.WebSearch()],
        max_tool_calls=8,
    )

    html = bench._repr_html_()

    assert "class='sf-ui" in html
    assert "mini@1" in html
    assert "Mini Suite" in html
    assert "exact" in html.lower()  # grader kind
    assert "mean" in html.lower()  # aggregator kind
    assert "web_search" in html
    assert "8" in html  # max_tool_calls
    lowered = html.lower()
    for banned in _FABRICATED:
        assert banned not in lowered


def test_benchmark_repr_text_is_concise() -> None:
    bench = sf.Benchmark(
        "mini@1", cases=[sf.Case("c1", "2+2?", reference="4")], grader=sf.graders.ExactChoice()
    )

    text = repr(bench)

    assert "Benchmark" in text
    assert "mini@1" in text
    assert "<div" not in text


# --- catalog views ------------------------------------------------------------------------


def test_models_view_value_matches_list(engine: None) -> None:
    view = sf.models.view()

    assert view.value == sf.models.list()
    html = view._repr_html_()
    assert "class='sf-ui" in html
    assert "gemini/2.5-flash" in html
    assert "codex/gpt-5.5" in html


def test_models_view_query_matches_list_query(engine: None) -> None:
    assert sf.models.view(query="gemini").value == sf.models.list(query="gemini")
    assert sf.models.view(tools=["web_search"]).value == sf.models.list(tools=["web_search"])


def test_models_view_widget_search_filters_rows_and_value(engine: None) -> None:
    view = sf.models.view()
    root = view.widget()

    search = next(item for item in _walk(root) if isinstance(item, widgets.Text))
    search.value = "codex"

    assert view.value == ["codex/gpt-5.5"]
    body = _html_text(root)
    assert "codex/gpt-5.5" in body
    assert "gemini/2.5-flash" not in body


def test_benchmarks_view_value_matches_list(engine: None) -> None:
    view = sf.benchmarks.view()

    assert view.value == sf.benchmarks.list()
    html = view._repr_html_()
    assert "gpqa@1" in html
    assert "GPQA Diamond" in html
    assert "draco@1" in html


def test_benchmarks_view_query_matches_list_query(engine: None) -> None:
    assert sf.benchmarks.view(query="draco").value == sf.benchmarks.list(query="draco")
    assert sf.benchmarks.view(tools=["web_search"]).value == sf.benchmarks.list(
        tools=["web_search"]
    )


def test_benchmarks_view_widget_search_filters_rows_and_value(engine: None) -> None:
    view = sf.benchmarks.view()
    root = view.widget()

    search = next(item for item in _walk(root) if isinstance(item, widgets.Text))
    search.value = "draco"

    assert view.value == ["draco@1"]
    body = _html_text(root)
    assert "draco@1" in body
    assert "gpqa@1" not in body
