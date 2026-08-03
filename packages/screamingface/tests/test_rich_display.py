from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import httpx
import pytest

import screamingface as sf
from screamingface._url4_format import _pretty_url4

_FABRICATED = ("context window", "ability", "tok/s", "tokens/s", "$/m", "price")


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    return sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(handler),
    )


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
            "object": "list",
            "default": "draco-<lite>",
            "data": [
                {
                    "id": "draco-<lite>",
                    "object": "benchmark",
                    "title": "DRACO <lite>",
                    "description": "A tiny probe tier.",
                }
            ],
        },
    )


def _lite_summary(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "schema": "screamingface.benchmark.v1",
            "id": "draco-<lite>",
            "revision": "rev0000000000000",
            "case_count": 1,
            "total_case_count": 30,
            "required_models": [],
            "url4": "(ignored)",
        },
    )


def _handler(request: httpx.Request) -> httpx.Response:
    routes = {
        "/v1/models": _models,
        "/v1/benchmarks": _benchmarks,
        "/v1/benchmarks/draco-<lite>": _lite_summary,
    }
    route = routes.get(request.url.path)
    return route(request) if route else httpx.Response(404)


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
    assert benchmarks[0].id == "draco-<lite>"
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
    assert "draco-&lt;lite&gt;" in benchmark_html


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
        prompt="Use <primary> evidence.",
        params={"temperature": 0.2},
    )

    html = cast(Any, model)._repr_html_()

    assert "opus &lt;script&gt;" in html
    assert "openrouter/anthropic/claude-opus-4.8" in html
    assert "Use &lt;primary&gt; evidence." in html
    assert "temperature=0.2" in html
    assert "instructions" not in html
    assert "reasoning" not in html
    assert "max output tokens" not in html
    for banned in _FABRICATED:
        assert banned not in html.lower()


def test_fusion_card_keeps_only_benchmark_independent_topology_visible() -> None:
    opus = sf.Model("provider/opus", name="opus")
    gpt = sf.Model("provider/gpt", name="gpt")
    fusion = sf.Fusion(
        [opus, gpt],
        name="frontier <pair>",
        synthesizer="provider/synth",
        prompt="Resolve <conflicts>.",
        params={"reasoning": "high"},
    )

    html = cast(Any, fusion)._repr_html_()

    assert "frontier &lt;pair&gt;" in html
    assert ">members<" in html
    assert "provider/opus" in html
    assert "provider/gpt" in html
    assert ">synthesis<" in html
    assert "provider/synth" in html
    assert "Resolve &lt;conflicts&gt;." in html
    assert "reasoning=high" in html
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


def test_cards_cover_provider_fallback_and_nested_fusions() -> None:
    model_html = cast(Any, sf.Model("model-without-provider"))._repr_html_()
    assert "—" in model_html
    inner = sf.Fusion(
        [sf.Model("provider/a"), sf.Model("provider/b")],
        name="inner",
    )
    outer = sf.Fusion(
        [inner, sf.Model("provider/c")],
        name="outer",
    )
    fusion_html = cast(Any, outer)._repr_html_()
    assert "nested fusion" in fusion_html


def test_url4_reflow_handles_empty_structures_commas_spaces_and_escaped_quotes() -> None:
    pretty = _pretty_url4("(a:{}, b:())!'Keep \\'quotes\\', commas, and (parens).'")

    assert "a:{}" in pretty
    assert "b:()" in pretty
    assert "\n" in pretty
    assert "Keep \\'quotes\\', commas, and (parens)." in pretty
