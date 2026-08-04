"""Rich benchmark discovery — catalog values and case browsing.

FEATURE: benchmark researcher discovery (OME-722/OME-724) — a researcher learns what a
benchmark is (title, description, size, real prompts) through `sf.*` calls before
spending money evaluating.
STORY: as a researcher, `sf.benchmarks.list()` → `get("ifeval")` → `.cases(limit=5)`
shows me the actual exam, then I evaluate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

import screamingface as sf
from screamingface import _default_client

_CATALOG = {
    "object": "list",
    "default": "draco",
    "data": [
        {
            "object": "benchmark",
            "id": "draco",
            "title": "DRACO",
            "description": "The 100-task DRACO deep-research benchmark.",
            "href": "/v1/benchmarks/draco",
        },
        {
            "object": "benchmark",
            "id": "ifeval",
            "title": "IFEval",
            "description": "541 instruction-following prompts graded by code.",
            "href": "/v1/benchmarks/ifeval",
        },
    ],
}

_SUMMARIES = {
    "draco": {
        "schema": "screamingface.benchmark.v1",
        "id": "draco",
        "revision": "dracorev00000000",
        "case_count": 1,
        "total_case_count": 100,
        "required_models": ["openrouter/google/gemini-3.1-pro-preview"],
        "url4": "(ignored-by-discovery)",
    },
    "ifeval": {
        "schema": "screamingface.benchmark.v1",
        "id": "ifeval",
        "revision": "ifevalrev0000000",
        "case_count": 1,
        "total_case_count": 541,
        "required_models": [],
        "url4": "(ignored-by-discovery)",
    },
}


def _cases_page(benchmark_id: str, limit: int, offset: int) -> dict[str, object]:
    total = 541 if benchmark_id == "ifeval" else 100
    rows = [
        {"id": index + 1, "input": f"{benchmark_id} prompt {index + 1}"}
        for index in range(offset, min(offset + limit, total))
    ]
    return {
        "object": "list",
        "benchmark": benchmark_id,
        "revision": _SUMMARIES[benchmark_id]["revision"],
        "total": total,
        "limit": limit,
        "offset": offset,
        "data": rows,
    }


def _engine_body(request: httpx.Request) -> object | None:
    path = request.url.path
    if path.endswith("/cases"):
        benchmark_id = path.removeprefix("/v1/benchmarks/").removesuffix("/cases")
        if benchmark_id not in _SUMMARIES:
            return None
        limit = int(request.url.params.get("limit", "50"))
        offset = int(request.url.params.get("offset", "0"))
        return _cases_page(benchmark_id, limit, offset)
    static: dict[str, object] = {"/v1/benchmarks": _CATALOG}
    for benchmark_id, summary in _SUMMARIES.items():
        static[f"/v1/benchmarks/{benchmark_id}"] = summary
    return static.get(path)


def _engine_handler(request: httpx.Request) -> httpx.Response:
    body = _engine_body(request)
    if body is None:
        return httpx.Response(
            404,
            json={
                "type": "about:blank",
                "title": "Unknown benchmark",
                "status": 404,
                "detail": "no",
            },
        )
    return httpx.Response(200, json=body)


def _sync_client(
    handler: Callable[[httpx.Request], httpx.Response] = _engine_handler,
) -> sf.Client:
    return sf.Client(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(handler),
    )


def _async_client(
    handler: Callable[[httpx.Request], httpx.Response] = _engine_handler,
) -> sf.AsyncClient:
    return sf.AsyncClient(
        engine_url="https://engine.example",
        http_transport=httpx.MockTransport(handler),
    )


def test_list_returns_rich_benchmark_values() -> None:
    with _sync_client() as client:
        catalog = client.benchmarks.list()

    assert [benchmark.id for benchmark in catalog] == ["draco", "ifeval"]
    ifeval = catalog[1]
    assert ifeval.title == "IFEval"
    assert ifeval.description == "541 instruction-following prompts graded by code."
    assert ifeval.revision == "ifevalrev0000000"
    assert ifeval.case_count == 541


def test_get_returns_one_benchmark_value() -> None:
    with _sync_client() as client:
        benchmark = client.benchmarks.get("ifeval")

    assert (benchmark.id, benchmark.title, benchmark.case_count) == ("ifeval", "IFEval", 541)
    assert benchmark.revision == "ifevalrev0000000"


def test_get_unknown_benchmark_is_a_typed_planning_error() -> None:
    with _sync_client() as client, pytest.raises(sf.PlanningError) as exc_info:
        client.benchmarks.get("nope")

    assert exc_info.value.code == "unknown_benchmark"


def test_cases_pages_real_prompts_and_forwards_paging_params() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return _engine_handler(request)

    with _sync_client(handler) as client:
        benchmark = client.benchmarks.get("ifeval")
        page = benchmark.cases(limit=3, offset=100)

    assert [case.id for case in page] == [101, 102, 103]
    assert page[0].input == "ifeval prompt 101"
    assert page.total == 541
    assert page.limit == 3
    assert page.offset == 100
    assert any(
        "/v1/benchmarks/ifeval/cases" in url and "limit=3" in url and "offset=100" in url
        for url in seen
    )


def test_case_rows_are_case_info_values() -> None:
    with _sync_client() as client:
        page = client.benchmarks.get("draco").cases(limit=2)

    assert page[0] == sf.CaseInfo(id=1, input="draco prompt 1")


def test_cases_engine_unreachable_is_typed() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with _sync_client() as client:
        benchmark = client.benchmarks.get("ifeval")
    # WHY: the page fetch happens lazily on .cases() — swap the transport for a dead one
    # by building a fresh client whose catalog never loads is impossible here, so this
    # test drives the adapter surface directly instead.
    with _sync_client(unreachable) as dead:
        with pytest.raises(sf.EngineUnavailableError):
            dead.benchmarks.cases("ifeval", limit=1, offset=0)
    assert benchmark.id == "ifeval"


def test_cases_5xx_is_a_non_permanent_planning_error() -> None:
    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cases"):
            return httpx.Response(503, json={"status": 503, "code": "benchmark_unavailable"})
        return _engine_handler(request)

    with _sync_client(flaky) as client, pytest.raises(sf.PlanningError) as exc_info:
        client.benchmarks.get("ifeval").cases(limit=1)

    assert exc_info.value.permanent is False


@pytest.mark.parametrize(
    "body",
    [
        {"object": "wrong"},
        {
            "object": "list",
            "benchmark": "ifeval",
            "total": 1,
            "limit": 1,
            "offset": 0,
            "data": "wrong",
        },
        {
            "object": "list",
            "benchmark": "ifeval",
            "total": 1,
            "limit": 1,
            "offset": 0,
            "data": [{"id": 1}],
        },
    ],
)
def test_malformed_case_pages_are_rejected(body: object) -> None:
    def malformed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cases"):
            return httpx.Response(200, json=body)
        return _engine_handler(request)

    with _sync_client(malformed) as client, pytest.raises(sf.PlanningError) as exc_info:
        client.benchmarks.get("ifeval").cases(limit=1)

    assert exc_info.value.permanent is True


@pytest.mark.asyncio
async def test_async_client_mirrors_the_browsing_surface() -> None:
    async with _async_client() as client:
        catalog = await client.benchmarks.list()
        benchmark = await client.benchmarks.get("ifeval")
        page = await client.benchmarks.cases("ifeval", limit=2, offset=0)

    assert catalog[1].title == "IFEval"
    assert benchmark.case_count == 541
    assert [case.id for case in page] == [1, 2]


@pytest.mark.asyncio
async def test_async_built_value_redirects_sync_cases_calls() -> None:
    async with _async_client() as client:
        benchmark = await client.benchmarks.get("ifeval")

    with pytest.raises(sf.PlanningError, match="client.benchmarks.cases"):
        benchmark.cases(limit=1)


def test_benchmark_value_renders_a_card() -> None:
    with _sync_client() as client:
        benchmark = client.benchmarks.get("ifeval")

    html = benchmark._repr_html_()
    assert "IFEval" in html
    assert "541" in html


def test_case_catalog_renders_rows_and_escapes_prompt_text() -> None:
    def hostile(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cases"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "benchmark": "ifeval",
                    "revision": "ifevalrev0000000",
                    "total": 1,
                    "limit": 1,
                    "offset": 0,
                    "data": [{"id": 1, "input": "<script>alert(1)</script>"}],
                },
            )
        return _engine_handler(request)

    with _sync_client(hostile) as client:
        page = client.benchmarks.get("ifeval").cases(limit=1)

    html = page._repr_html_()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_module_get_delegates_to_the_lazy_default_client(monkeypatch: Any) -> None:
    class Benchmarks:
        def get(self, benchmark_id: str) -> str:
            return f"got:{benchmark_id}"

    class FakeClient:
        benchmarks = Benchmarks()

    monkeypatch.setattr(_default_client, "_client", FakeClient())
    try:
        assert sf.benchmarks.get("ifeval") == "got:ifeval"
        assert sf.benchmarks.get("ifeval-iterative-correction") == "got:ifeval-iterative-correction"
    finally:
        monkeypatch.setattr(_default_client, "_client", None)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"id": 0, "input": "x"}, ValueError),
        ({"id": True, "input": "x"}, ValueError),
        ({"id": 1, "input": "  "}, ValueError),
        ({"id": 1, "input": 3}, TypeError),
    ],
)
def test_case_info_rejects_invalid_values(kwargs: dict[str, Any], error: type[Exception]) -> None:
    with pytest.raises(error):
        sf.CaseInfo(**kwargs)


def test_benchmark_value_rejects_a_non_positive_case_count() -> None:
    with pytest.raises(ValueError, match="case_count"):
        sf.Benchmark(
            id="x",
            family="x",
            variant="canonical",
            title="X",
            description="d",
            revision="r",
            case_count=0,
            _fetch_cases=lambda limit, offset: None,  # type: ignore[arg-type,return-value]
        )


def test_summary_without_a_valid_total_is_rejected() -> None:
    def broken_summary(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks/ifeval":
            return httpx.Response(200, json={"revision": "r", "total_case_count": "many"})
        return _engine_handler(request)

    with _sync_client(broken_summary) as client, pytest.raises(sf.PlanningError) as exc_info:
        client.benchmarks.get("ifeval")

    assert exc_info.value.code == "invalid_catalogue"


@pytest.mark.parametrize(
    "body",
    [
        {"object": "list", "benchmark": "b", "total": 1, "limit": 0, "offset": 0, "data": []},
        {
            "object": "list",
            "benchmark": "b",
            "total": 1,
            "limit": 1,
            "offset": 0,
            "data": [{"id": "one", "input": "x"}],
        },
        {
            "object": "list",
            "benchmark": "b",
            "total": 1,
            "limit": 1,
            "offset": 0,
            "data": [{"id": 1, "input": "   "}],
        },
    ],
)
def test_case_pages_with_invalid_counters_or_rows_are_rejected(body: object) -> None:
    def malformed(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cases"):
            return httpx.Response(200, json=body)
        return _engine_handler(request)

    with _sync_client(malformed) as client, pytest.raises(sf.PlanningError):
        client.benchmarks.get("ifeval").cases(limit=1)


def test_an_empty_case_page_renders_and_reprs_gracefully() -> None:
    def empty(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cases"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "benchmark": "ifeval",
                    "revision": "r",
                    "total": 541,
                    "limit": 3,
                    "offset": 600,
                    "data": [],
                },
            )
        return _engine_handler(request)

    with _sync_client(empty) as client:
        page = client.benchmarks.get("ifeval").cases(limit=3, offset=600)

    assert repr(page) == "Cases(0 of 541, offset=600)"
    assert "No cases match" in page._repr_html_()


def test_case_search_text_feeds_the_widget_filter() -> None:
    widgets = pytest.importorskip("ipywidgets")

    with _sync_client() as client:
        page = client.benchmarks.get("ifeval").cases(limit=2)

    def walk(widget: Any) -> tuple[Any, ...]:
        children = getattr(widget, "children", ())
        return (widget, *(item for child in children for item in walk(child)))

    root = page._widget()
    search = next(item for item in walk(root) if isinstance(item, widgets.Text))
    search.value = "prompt 2"
    body = "\n".join(
        item.value
        for item in walk(root)
        if isinstance(item, widgets.HTML) and isinstance(item.value, str)
    )

    assert "ifeval prompt 2" in body
    assert "case 1<" not in body
