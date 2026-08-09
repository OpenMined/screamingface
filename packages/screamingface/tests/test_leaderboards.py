from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx
import pytest
from url4 import expr, render, src, text

import screamingface as sf
from screamingface import _default_client
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.model import _compiled_operation

SCOREBOARD_URL = "https://scoreboard.example"
CREATED_AT = "2026-08-01T10:00:00Z"
SUBMITTED_AT = "2026-08-08T12:30:00Z"
IMPORTED_AT = "2026-08-07T09:15:00Z"
BASELINE_ID = "02fd61c7-7db8-4dce-92d7-115813e691ed"
SCORE_ID = "af95892d-7438-4ac3-9b47-5e06f62c8251"


def _linked_url4(*, prompt: str | None = None) -> str:
    candidate = compile_candidate(sf.Model("openrouter/model", prompt=prompt)).url4
    assert candidate is not None
    return render(
        expr(
            src(text(candidate), name="candidate", weight=0.0),
            src(
                "/benchmarks/draco/revision-1/cases",
                name="rows",
                weight=0.0,
            ),
            intent=text("$rows"),
        )
    )


def _benchmark() -> dict[str, object]:
    return {
        "id": "draco",
        "display_name": "DRACO",
        "description": "Deep Research AI Comparison",
        "dataset_url": "https://scoreboard.example/draco.jsonl",
        "created_at": CREATED_AT,
    }


def _list_response() -> dict[str, object]:
    return {"benchmarks": [_benchmark()]}


def _get_response() -> dict[str, object]:
    return {
        "benchmark": _benchmark(),
        "entries": [
            {
                "rank": 1,
                "spec_id": "fusion/alpha",
                "accuracy": 0.82,
                "total_questions": 100,
                "ran_with_providers": ["openrouter", "gemini-cli"],
                "submitted_at": SUBMITTED_AT,
                "submitted_by": "researcher@example.com",
                "verified_by_openmined": True,
                "url4_expression": _linked_url4(),
            }
        ],
        "baselines": [
            {
                "id": BASELINE_ID,
                "benchmark_id": "draco",
                "model_name": "single/model",
                "accuracy": 0.61,
                "source": "published-paper",
                "source_url": "https://example.com/paper",
                "imported_at": IMPORTED_AT,
                "metadata": {"organization": "Example Lab", "tags": ["closed"]},
            }
        ],
    }


def _score_response() -> dict[str, object]:
    return {
        "id": SCORE_ID,
        "version": 1,
        "benchmark_id": "draco",
        "spec_id": "fusion/alpha",
        "url4_expression": _linked_url4(),
        "submitted_by": "researcher@example.com",
        "submitted_at": SUBMITTED_AT,
        "accuracy": 0.5,
        "total_questions": 2,
        "correct_questions": 1,
        "ran_with_providers": ["openrouter", "gemini-cli"],
        "ran_at_local": "2026-08-08T12:00:00Z",
        "client_name": "screamingface",
        "client_version": "0.1.0",
        "client_platform": "darwin",
        "verified_by_openmined": False,
        "metadata": {
            "benchmark_revision": "fixture-revision",
            "candidate_kind": "fusion",
            "run_id": "run-fusion-alpha",
        },
    }


def _case(case_id: int, score: float | None) -> sf.CaseResult:
    return sf.CaseResult(
        case_id=case_id,
        input=f"Question {case_id}",
        output=f"Answer {case_id}",
        finish_reason="stop",
        grade=sf.CaseGrade(method="fixture", score=score, metrics={}, checks=()),
        failures=(),
        metadata={},
    )


def _candidate_result(*, score: float | None = 0.5) -> sf.CandidateResult:
    return sf.CandidateResult(
        benchmark=sf.BenchmarkInfo(
            id="draco",
            revision="fixture-revision",
            case_count=2,
        ),
        run_id="run-fusion-alpha",
        started_at=datetime(2026, 8, 8, 11, 59, tzinfo=UTC),
        completed_at=datetime(2026, 8, 8, 12, tzinfo=UTC),
        name="fusion/alpha",
        kind="fusion",
        url4="(@)!'fusion alpha'",
        models=("openrouter/model-a", "gemini-cli/model-b"),
        operations=(
            _compiled_operation(id="op-a", kind="model", label="a", depends_on=()),
            _compiled_operation(id="op-b", kind="model", label="b", depends_on=()),
        ),
        score=score,
        metrics={} if score is None else {"accuracy": score},
        cases=(_case(1, 1.0), _case(2, 0.0)),
        members=(
            sf.MemberResult(
                operation_id="op-a",
                name="a",
                kind="model",
                models=("openrouter/model-a",),
                failures=(),
                duration_ms=1,
                usage=sf.Usage(),
            ),
            sf.MemberResult(
                operation_id="op-b",
                name="b",
                kind="model",
                models=("gemini-cli/model-b",),
                failures=(),
                duration_ms=1,
                usage=sf.Usage(),
            ),
        ),
        failures=(),
        usage=sf.Usage(),
    )


def _sync_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.Client:
    return sf.Client(
        engine_url="https://engine.example",
        scoreboard_url=SCOREBOARD_URL,
        scoreboard_transport=httpx.MockTransport(handler),
    )


def _async_client(handler: Callable[[httpx.Request], httpx.Response]) -> sf.AsyncClient:
    return sf.AsyncClient(
        engine_url="https://engine.example",
        scoreboard_url=SCOREBOARD_URL,
        scoreboard_transport=httpx.MockTransport(handler),
    )


def test_client_lists_scoreboard_registered_leaderboards() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_list_response())

    with _sync_client(handler) as client:
        values = client.leaderboards.list()

    assert values == (
        sf.LeaderboardInfo(
            id="draco",
            display_name="DRACO",
            description="Deep Research AI Comparison",
            dataset_url="https://scoreboard.example/draco.jsonl",
            created_at=datetime(2026, 8, 1, 10, tzinfo=UTC),
        ),
    )
    assert repr(values) == "Leaderboards(1)"
    html = cast(Any, values)._repr_html_()
    assert "sf-lb-list" in html
    assert "Filter leaderboards" in html
    assert "Deep Research AI Comparison" in html
    assert "sf.leaderboards.get(&quot;draco&quot;)" in html
    assert [request.url.path for request in seen] == ["/v1/benchmarks"]
    assert seen[0].url.host == "scoreboard.example"


def test_client_gets_one_ranked_leaderboard_with_baselines() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_get_response())

    with _sync_client(handler) as client:
        board = client.leaderboards.get("draco", top=25)

    assert board.benchmark.id == "draco"
    assert isinstance(board.entries[0].url4, sf.Url4)
    assert board.entries == (
        sf.LeaderboardEntry(
            rank=1,
            spec_id="fusion/alpha",
            accuracy=0.82,
            total_questions=100,
            ran_with_providers=("openrouter", "gemini-cli"),
            submitted_at=datetime(2026, 8, 8, 12, 30, tzinfo=UTC),
            submitted_by="researcher@example.com",
            verified_by_openmined=True,
            url4=sf.Url4(_linked_url4()),
        ),
    )
    assert board.baselines[0].id == UUID(BASELINE_ID)
    assert board.baselines[0].metadata == {
        "organization": "Example Lab",
        "tags": ("closed",),
    }
    assert isinstance(board.baselines[0].metadata, Mapping)
    with pytest.raises(TypeError):
        board.baselines[0].metadata["organization"] = "changed"  # type: ignore[index]
    assert seen[0].url.path == "/v1/leaderboard/draco"
    assert dict(seen[0].url.params) == {"top": "25"}


def test_client_submits_a_candidate_result_without_repeating_report_fields() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json=_score_response())

    candidate = _candidate_result()
    with _sync_client(handler) as client:
        score = client.leaderboards.submit(candidate)

    assert score == sf.LeaderboardScore(
        id=UUID(SCORE_ID),
        version=1,
        benchmark_id="draco",
        spec_id="fusion/alpha",
        url4=sf.Url4(_linked_url4()),
        submitted_by="researcher@example.com",
        submitted_at=datetime(2026, 8, 8, 12, 30, tzinfo=UTC),
        accuracy=0.5,
        total_questions=2,
        correct_questions=1,
        ran_with_providers=("openrouter", "gemini-cli"),
        ran_at_local=datetime(2026, 8, 8, 12, tzinfo=UTC),
        client_name="screamingface",
        client_version="0.1.0",
        client_platform="darwin",
        verified_by_openmined=False,
        metadata={
            "benchmark_revision": "fixture-revision",
            "candidate_kind": "fusion",
            "run_id": "run-fusion-alpha",
        },
    )
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/scores"
    assert seen[0].headers["Idempotency-Key"] == candidate.run_id
    payload = seen[0].read().decode()
    assert '"benchmark_id":"draco"' in payload
    assert '"spec_id":"fusion/alpha"' in payload
    assert '"correct_questions":1' in payload
    assert '"ran_with_providers":["openrouter","gemini-cli"]' in payload


def test_client_gets_one_score_by_uuid_or_string() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_score_response())

    with _sync_client(handler) as client:
        by_uuid = client.leaderboards.get_score(UUID(SCORE_ID))
        by_text = client.leaderboards.get_score(SCORE_ID)

    assert by_uuid == by_text
    assert by_uuid.id == UUID(SCORE_ID)
    assert [request.url.path for request in seen] == [
        f"/v1/scores/{SCORE_ID}",
        f"/v1/scores/{SCORE_ID}",
    ]


def test_submit_rejects_results_the_accuracy_scoreboard_cannot_represent() -> None:
    client = _sync_client(lambda _: pytest.fail("invalid result reached the Scoreboard"))

    with client, pytest.raises(ValueError, match="unscored"):
        client.leaderboards.submit(_candidate_result(score=None))


def test_submit_surfaces_the_live_closed_write_contract() -> None:
    client = _sync_client(
        lambda _: httpx.Response(403, json={"detail": "score submission is not open yet"})
    )

    with client, pytest.raises(sf.LeaderboardError) as exc_info:
        client.leaderboards.submit(_candidate_result())

    assert exc_info.value.code == "score_submission_forbidden"
    assert exc_info.value.status == 403
    assert exc_info.value.details == "score submission is not open yet"


def test_leaderboard_rich_display_uses_the_brand_board_with_only_real_fields() -> None:
    with _sync_client(lambda _: httpx.Response(200, json=_get_response())) as client:
        board = client.leaderboards.get("draco")

    html = cast(Any, board)._repr_html_()

    assert "ScreamingFace candidate leaderboard" in html
    assert "sf-lb-board" in html
    assert "sf-lb__score-fill--gradient" in html
    assert "sf-lb__row--winner" in html
    assert "fusion/alpha" in html
    assert "single/model" in html
    assert "82.0" in html
    assert "61.0" in html
    assert "verified only" in html
    assert "data-python=" in html
    assert "candidate = sf.Model(" in html
    assert "&#x27;openrouter/model&#x27;" in html
    assert "copies editable Python" in html
    assert "questions" in html
    assert "cost" not in html.lower()
    assert "mine only" not in html.lower()


def test_leaderboard_rich_display_escapes_scoreboard_text_and_recipe_attributes() -> None:
    payload = _get_response()
    benchmark = cast(dict[str, object], payload["benchmark"])
    benchmark["display_name"] = "DRACO <script>"
    entry = cast(list[dict[str, object]], payload["entries"])[0]
    entry["spec_id"] = 'fusion/"alpha" <script>'
    entry["url4_expression"] = _linked_url4(prompt='" onclick="alert(1)')

    with _sync_client(lambda _: httpx.Response(200, json=payload)) as client:
        html = cast(Any, client.leaderboards.get("draco"))._repr_html_()

    assert "DRACO &lt;script&gt;" in html
    assert "fusion/&quot;" in html
    assert "<script>" not in html
    assert "prompt=&#x27;&quot; onclick=&quot;alert(1)&#x27;" in html


def test_leaderboard_widgets_use_the_brand_system_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = _list_response() if request.url.path == "/v1/benchmarks" else _get_response()
        return httpx.Response(200, json=payload)

    with _sync_client(handler) as client:
        list_html = cast(Any, client.leaderboards.list())._repr_html_()
        board_html = cast(Any, client.leaderboards.get("draco"))._repr_html_()

    for html in (list_html, board_html):
        assert "--sf-lb-bg:#fcfdff" in html
        assert 'font-family:"IBM Plex Sans"' in html
        assert 'font-family:"IBM Plex Mono"' in html
        assert "border-radius:0" in html
        assert "max-width:920px" in html
        assert ".jp-mod-theme-dark .sf-lb" in html
        assert '.jp-mod-theme-light .sf-lb,[data-jp-theme-light="true"] .sf-lb' in html
        assert ".vscode-dark .sf-lb" in html
        assert ".vscode-light .sf-lb" in html


@pytest.mark.asyncio
async def test_async_client_exposes_the_same_leaderboard_interface() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/benchmarks":
            return httpx.Response(200, json=_list_response())
        return httpx.Response(200, json=_get_response())

    async with _async_client(handler) as client:
        listed = await client.leaderboards.list()
        board = await client.leaderboards.get("draco", top=10)

    assert listed[0].id == "draco"
    assert board.entries[0].rank == 1


@pytest.mark.asyncio
async def test_async_client_submits_and_gets_scores() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201 if request.method == "POST" else 200, json=_score_response())

    async with _async_client(handler) as client:
        submitted = await client.leaderboards.submit(_candidate_result())
        fetched = await client.leaderboards.get_score(submitted.id)

    assert submitted == fetched


def test_module_leaderboards_delegate_to_the_lazy_default_client(monkeypatch: Any) -> None:
    class Leaderboards:
        def list(self) -> tuple[str, ...]:
            return ("draco",)

        def get(self, benchmark_id: str, *, top: int = 50) -> str:
            return f"{benchmark_id}:{top}"

        def submit(self, candidate_result: object) -> tuple[str, object]:
            return ("submitted", candidate_result)

        def get_score(self, score_id: object) -> tuple[str, object]:
            return ("score", score_id)

    class FakeClient:
        leaderboards = Leaderboards()

    monkeypatch.setattr(_default_client, "_client", FakeClient())

    assert sf.leaderboards.list() == ("draco",)
    assert sf.leaderboards.get("draco", top=20) == "draco:20"
    candidate = _candidate_result()
    assert sf.leaderboards.submit(candidate) == ("submitted", candidate)
    assert sf.leaderboards.get_score(SCORE_ID) == ("score", SCORE_ID)

    monkeypatch.setattr(_default_client, "_client", None)


def test_default_client_reads_the_scoreboard_environment_once(monkeypatch: Any) -> None:
    monkeypatch.setattr(_default_client, "_client", None)
    monkeypatch.setenv("SCREAMINGFACE_SCOREBOARD_URL", "https://first.example")

    first = _default_client.default_client()
    monkeypatch.setenv("SCREAMINGFACE_SCOREBOARD_URL", "https://second.example")
    second = _default_client.default_client()

    assert first is second
    assert first.scoreboard_url == "https://first.example"
    first.close()
    monkeypatch.setattr(_default_client, "_client", None)


@pytest.mark.parametrize(
    ("response", "operation", "code", "permanent"),
    [
        (
            httpx.Response(404, json={"detail": "Benchmark not found"}),
            "get",
            "unknown_leaderboard",
            True,
        ),
        (httpx.Response(503), "list", "scoreboard_contract_error", False),
        (httpx.Response(200, text="{"), "list", "invalid_leaderboard", True),
        (httpx.Response(200, json={"benchmarks": "wrong"}), "list", "invalid_leaderboard", True),
    ],
)
def test_leaderboard_failures_are_typed(
    response: httpx.Response,
    operation: str,
    code: str,
    permanent: bool,
) -> None:
    client = _sync_client(lambda _: response)

    with client, pytest.raises(sf.LeaderboardError) as exc_info:
        if operation == "get":
            client.leaderboards.get("missing")
        else:
            client.leaderboards.list()

    assert exc_info.value.code == code
    assert exc_info.value.permanent is permanent


def test_unreachable_scoreboard_is_a_typed_retryable_failure() -> None:
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = _sync_client(unreachable)

    with client, pytest.raises(sf.LeaderboardError) as exc_info:
        client.leaderboards.list()

    assert exc_info.value.code == "scoreboard_unreachable"
    assert exc_info.value.scoreboard_url == SCOREBOARD_URL
    assert exc_info.value.retryable is True


@pytest.mark.parametrize(("benchmark_id", "top"), [("", 50), ("draco", 0), ("draco", True)])
def test_get_rejects_invalid_query_values(benchmark_id: str, top: object) -> None:
    client = _sync_client(lambda _: pytest.fail("invalid query reached the scoreboard"))

    with client, pytest.raises((TypeError, ValueError)):
        client.leaderboards.get(benchmark_id, top=top)  # type: ignore[arg-type]
