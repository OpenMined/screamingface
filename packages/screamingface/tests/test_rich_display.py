from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

import screamingface as sf
from screamingface._url4_format import _pretty_url4

DIGEST = f"sha256:{'a' * 64}"
_FABRICATED = ("context window", "ability", "tok/s", "tokens/s", "$/m", "price")


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    client = sf.Client(engine_url="https://engine.example")
    client._http.close()  # type: ignore[attr-defined]
    client._http = httpx.Client(  # type: ignore[attr-defined]
        base_url="https://engine.example",
        transport=httpx.MockTransport(handler),
    )
    return client


def _models(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [
                {"id": "anthropic/claude-opus-4.8", "owned_by": "anthropic"},
                {"id": "openrouter/openai/gpt-5.5", "owned_by": "openrouter"},
            ],
        },
    )


def _benchmarks(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "benchmarks": [
                {
                    "name": "draco-lite",
                    "id": "draco-lite",
                    "title": "DRACO <Lite>",
                    "manifest_digest": DIGEST,
                    "case_count": 1,
                    "primary_metric": "normalized_score",
                    "score_direction": "maximize",
                }
            ]
        },
    )


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return _models(request)
    if request.url.path == "/v1/benchmarks":
        return _benchmarks(request)
    return httpx.Response(404)


def _walk(widget: Any) -> tuple[Any, ...]:
    children = getattr(widget, "children", ())
    return (widget, *(item for child in children for item in _walk(child)))


def test_catalogues_are_compact_immutable_sequences_with_static_html() -> None:
    with _client(_handler) as client:
        models = client.models.list()
        benchmarks = client.benchmarks.list()

    assert models == (
        sf.ModelInfo(id="anthropic/claude-opus-4.8", provider="anthropic"),
        sf.ModelInfo(id="openrouter/openai/gpt-5.5", provider="openrouter"),
    )
    assert benchmarks[0].id == "draco-lite"
    assert len(models) == 2
    assert tuple(model.id for model in models) == (
        "anthropic/claude-opus-4.8",
        "openrouter/openai/gpt-5.5",
    )
    assert repr(models) == "Models(2)"
    assert repr(benchmarks) == "Benchmarks(1)"

    model_html = cast(Any, models)._repr_html_()
    benchmark_html = cast(Any, benchmarks)._repr_html_()
    assert "anthropic/claude-opus-4.8" in model_html
    assert "openrouter" in model_html
    assert "DRACO &lt;Lite&gt;" in benchmark_html
    assert "1 case" in benchmark_html
    assert "normalized_score" in benchmark_html
    assert "<details" in benchmark_html
    assert DIGEST in benchmark_html


def test_catalogue_notebook_search_filters_presentation_not_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    widgets = pytest.importorskip("ipywidgets")
    display_module = pytest.importorskip("IPython.display")

    with _client(_handler) as client:
        models = client.models.list()

    shown: list[object] = []
    monkeypatch.setattr(display_module, "display", shown.append)
    cast(Any, models)._ipython_display_()

    assert len(shown) == 1
    root = shown[0]
    search = next(item for item in _walk(root) if isinstance(item, widgets.Text))
    search.value = "gpt"
    body = "\n".join(
        item.value
        for item in _walk(root)
        if isinstance(item, widgets.HTML) and isinstance(item.value, str)
    )

    assert "openrouter/openai/gpt-5.5" in body
    assert "anthropic/claude-opus-4.8" not in body
    assert len(models) == 2


def test_catalogue_notebook_display_falls_back_to_static_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    display_module = pytest.importorskip("IPython.display")
    with _client(_handler) as client:
        models = client.models.list()

    def unavailable(_: object) -> object:
        raise ImportError("ipywidgets unavailable")

    shown: list[object] = []
    monkeypatch.setattr(type(models), "_widget", unavailable)
    monkeypatch.setattr(display_module, "display", shown.append)
    cast(Any, models)._ipython_display_()

    assert len(shown) == 1
    assert isinstance(shown[0], display_module.HTML)
    assert "anthropic/claude-opus-4.8" in cast(Any, shown[0]).data


def test_model_card_renders_only_real_escaped_authoring_fields() -> None:
    model = sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        name="opus <script>",
        instructions="<script>alert(1)</script>",
        temperature=0.2,
        reasoning="low",
        max_output_tokens=8192,
    )

    html = cast(Any, model)._repr_html_()

    assert "opus &lt;script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "openrouter/anthropic/claude-opus-4.8" in html
    assert "temperature" in html and "0.2" in html
    assert "reasoning" in html and "low" in html
    assert "max output tokens" in html and "8192" in html
    for banned in _FABRICATED:
        assert banned not in html.lower()


def test_fusion_card_keeps_members_and_synthesis_visible() -> None:
    opus = sf.Model("provider/opus", name="opus")
    gpt = sf.Model("provider/gpt", name="gpt")
    fusion = sf.Fusion(
        "frontier <pair>",
        members=[opus, gpt],
        reducer=sf.reducers.Synthesis(
            "provider/judge",
            instructions="Combine <carefully>.",
            max_output_tokens=4096,
        ),
    )

    html = cast(Any, fusion)._repr_html_()

    assert "frontier &lt;pair&gt;" in html
    assert ">members<" in html
    assert "provider/opus" in html
    assert "provider/gpt" in html
    assert ">synthesis<" in html
    assert "provider/judge" in html
    assert "Combine &lt;carefully&gt;." in html
    assert "sf-card__accent" in html
    assert "sf-gain-grad" in html


def test_catalogue_surface_has_no_duplicate_view_operation() -> None:
    assert not hasattr(sf.models, "view")
    assert not hasattr(sf.benchmarks, "view")


def test_catalogue_sequence_edges_and_empty_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    widgets = pytest.importorskip("ipywidgets")
    display_module = pytest.importorskip("IPython.display")
    with _client(_handler) as client:
        models = client.models.list()
        same_models = client.models.list()
        benchmarks = client.benchmarks.list()

    assert models == same_models
    assert models[:] == tuple(models)
    assert models != object()

    shown: list[object] = []
    monkeypatch.setattr(display_module, "display", shown.append)
    cast(Any, models)._ipython_display_()
    search = next(item for item in _walk(shown[0]) if isinstance(item, widgets.Text))
    search.value = "does-not-exist"
    body = "\n".join(
        item.value
        for item in _walk(shown[0])
        if isinstance(item, widgets.HTML) and isinstance(item.value, str)
    )
    assert "No models match." in body

    shown.clear()
    cast(Any, benchmarks)._ipython_display_()
    benchmark_search = next(item for item in _walk(shown[0]) if isinstance(item, widgets.Text))
    benchmark_search.value = "does-not-exist"
    benchmark_body = "\n".join(
        item.value
        for item in _walk(shown[0])
        if isinstance(item, widgets.HTML) and isinstance(item.value, str)
    )
    assert "No benchmarks match." in benchmark_body


def test_cards_cover_defaults_long_text_nested_fusions_and_unknown_reducers() -> None:
    long_instructions = "Explain the evidence carefully. " * 8
    model_html = cast(
        Any,
        sf.Model("model-without-provider", instructions=long_instructions),
    )._repr_html_()
    default_model_html = cast(Any, sf.Model("provider/model"))._repr_html_()
    assert "<details" in model_html
    assert f"{len(long_instructions)} chars" in model_html
    assert "provider" in default_model_html
    assert "default" in default_model_html

    class CustomReducer(sf.Reducer):
        @property
        def _reducer_marker(self) -> None:
            return None

        def __repr__(self) -> str:
            return "CustomReducer(<safe>)"

    inner = sf.Fusion(
        "inner",
        members=[sf.Model("provider/a"), sf.Model("provider/b")],
        reducer=sf.reducers.Synthesis("provider/judge"),
    )
    outer = sf.Fusion(
        "outer",
        members=[inner, sf.Model("provider/c")],
        reducer=CustomReducer(),
    )
    fusion_html = cast(Any, outer)._repr_html_()
    assert "nested fusion" in fusion_html
    assert "CustomReducer(&lt;safe&gt;)" in fusion_html

    default_fusion = sf.Fusion(
        "default-synthesis",
        members=[sf.Model("provider/d"), sf.Model("provider/e")],
        reducer=sf.reducers.Synthesis("provider/judge"),
    )
    assert "default instructions" in cast(Any, default_fusion)._repr_html_()


def test_url4_reflow_handles_empty_structures_commas_spaces_and_escaped_quotes() -> None:
    pretty = _pretty_url4("(a:{}, b:())!'Keep \\'quotes\\', commas, and (parens).'")

    assert "a:{}" in pretty
    assert "b:()" in pretty
    assert "\n" in pretty
    assert "Keep \\'quotes\\', commas, and (parens)." in pretty
