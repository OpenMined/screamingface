from __future__ import annotations

import json
from collections import defaultdict

import httpx
import pytest
from url4 import Request, Url4Node, build, render

import screamingface as sf
import screamingface.evaluation as evaluation
from screamingface.data import load_mock_questions
from screamingface.engine import Url4EngineClient, parse_fusion_result, parse_panel_result
from screamingface.model_inputs import _FusionMember, normalize_model_inputs


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def _members(model_ids: tuple[str, ...]) -> tuple[_FusionMember, ...]:
    return normalize_model_inputs(model_ids)


def test_fusion_recipe_is_unbound_canonical_and_engine_routed() -> None:
    ids = sf.models.list(max_price=20)
    fusion = sf.Fusion(
        "mvp",
        ids[:3],
        reducer=sf.MajorityVote(tie_breaker=ids[0]),
    )

    assert render(build(fusion.url4)) == fusion.url4
    assert "$question" in fusion.url4
    assert "question=" not in fusion.url4
    assert "/codex/gpt-5.5" in fusion.url4
    assert "/gemini/2.5" in fusion.url4
    assert "/claude/sonnet-4.6" in fusion.url4
    assert "sf-model://" not in fusion.url4
    assert "aigateway" not in fusion.url4.lower()

    concrete = fusion.request_for("Which option?\n\nA. One\nB. Two\nC. Three\nD. Four")
    assert render(build(concrete)) == concrete
    assert concrete.startswith("(question=")
    assert "screamingface.panel-result.v2" in concrete


@pytest.mark.asyncio
async def test_engine_client_sends_one_get_v1_with_expression_in_q() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="result", headers={"content-type": "text/plain"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = Url4EngineClient("http://engine.test", client=http)
        assert await client.evaluate("(question='hello')") == "result"

    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/v1"
    assert seen[0].url.params["q"] == "(question='hello')"


@pytest.mark.asyncio
async def test_engine_error_envelope_becomes_typed_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": "endpoint_not_found", "message": "missing route"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = Url4EngineClient("http://engine.test", client=http)
        with pytest.raises(sf.EngineError) as caught:
            await client.evaluate("(/missing('x')!'answer')")

    assert caught.value.code == "endpoint_not_found"
    assert caught.value.status_code == 404
    assert caught.value.request_expression == "(/missing('x')!'answer')"


def test_panel_result_requires_stable_model_slot_association() -> None:
    ids = tuple(sf.models.list())
    body = json.dumps(
        {
            "schema": "screamingface.panel-result.v2",
            "panel_1_id": ids[0],
            "panel_1_model": ids[1],
            "panel_1_answer": "A",
            "panel_2_id": ids[1],
            "panel_2_model": ids[0],
            "panel_2_answer": "B",
            "panel_3_id": ids[2],
            "panel_3_model": ids[2],
            "panel_3_answer": "C",
        }
    )

    with pytest.raises(sf.EngineError, match="panel_1"):
        parse_panel_result(body, _members(ids))


def test_fusion_result_requires_stable_synthesizer_association() -> None:
    ids = tuple(sf.models.list())
    body = json.dumps(
        {
            "schema": "screamingface.fusion-result.v2",
            "panel_1_id": ids[0],
            "panel_1_model": ids[0],
            "panel_1_answer": "A",
            "panel_2_id": ids[1],
            "panel_2_model": ids[1],
            "panel_2_answer": "B",
            "panel_3_id": ids[2],
            "panel_3_model": ids[2],
            "panel_3_answer": "C",
            "reducer": "model",
            "reducer_model": ids[1],
            "answer": "B",
        }
    )

    with pytest.raises(sf.EngineError, match="reducer model"):
        parse_fusion_result(body, _members(ids), ids[0])


@pytest.mark.asyncio
async def test_model_dictionary_reaches_url4_as_named_prompted_parameterized_call() -> None:
    ids = tuple(sf.models.list()[:2])
    seen: dict[str, Request] = {}
    node = Url4Node("configured-model-contract")

    for model_id in ids:
        route = sf.models.get(model_id).route

        async def answer(request: Request, *, model=model_id) -> str:
            seen[model] = request
            return "A"

        node.endpoint(route)(answer)

    fusion = sf.Fusion(
        "configured-model",
        [
            {
                "model": ids[0],
                "name": "careful-sample",
                "prompt": "Answer carefully: $question",
                "params": {"temperature": 0.7, "seed": 1},
            },
            ids[1],
        ],
    )
    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://url4.test") as http:
        client = Url4EngineClient("http://url4.test", client=http)
        body = await client.evaluate(fusion.request_for("Which option?"))

    result = parse_panel_result(body, fusion._members)
    assert result.answers == ("A", "A")
    assert seen[ids[0]].context == ""
    assert seen[ids[0]].intent == "Answer carefully: Which option?"
    assert seen[ids[0]].params == {"temperature": "0.7", "seed": "1"}


@pytest.mark.asyncio
async def test_real_url4_http_app_runs_panel_then_synthesizer() -> None:
    ids = tuple(sf.models.list())
    question = load_mock_questions(1)[0]
    calls: list[tuple[str, Request]] = []
    node = Url4Node("synthesis-contract")

    for index, model_id in enumerate(ids):
        route = sf.models.get(model_id).route

        async def answer(request: Request, *, model=model_id, choice=chr(65 + index)) -> str:
            calls.append((model, request))
            if request.intent.startswith("Synthesize"):
                return "B"
            return choice

        node.endpoint(route)(answer)

    fusion = sf.Fusion(
        "synthesis",
        ids,
        reducer=sf.ModelReducer(
            model=ids[0],
            prompt="Synthesize one answer from $panel_answers for $question",
            params={"temperature": 0.2, "max_tokens": 512},
        ),
    )
    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://url4.test") as http:
        client = Url4EngineClient("http://url4.test", client=http)
        body = await client.evaluate(fusion.request_for(question.prompt()))

    result = parse_fusion_result(body, fusion._members, ids[0])
    assert result.answers == ("A", "B", "C")
    assert result.answer == "B"
    assert len(calls) == 4
    synthesis = calls[-1][1]
    assert synthesis.context == ""
    assert "panel_1_answer" in synthesis.intent
    assert "panel_2_answer" in synthesis.intent
    assert "panel_3_answer" in synthesis.intent
    assert "$panel_answers" not in synthesis.intent
    assert synthesis.params == {"temperature": "0.2", "max_tokens": "512"}


@pytest.mark.asyncio
async def test_gpqa_evaluator_accepts_a_synthesized_fusion_answer() -> None:
    ids = tuple(sf.models.list())
    question = load_mock_questions(1)[0]
    correct = chr(65 + question.answer)
    node = Url4Node("synthesis-evaluation")

    for model_id in ids:
        route = sf.models.get(model_id).route

        async def answer(request: Request, *, expected=correct) -> str:
            return expected

        node.endpoint(route)(answer)

    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://url4.test") as http:
        session = sf.Session(
            mode="mock",
            engine_url="http://url4.test",
            engine=Url4EngineClient("http://url4.test", client=http),
            dataset_source="synthetic-gpqa-shaped",
        )
        fusion = sf.Fusion(
            "synthesis",
            ids,
            reducer=sf.ModelReducer(
                model=ids[0],
                prompt="Return the best answer from $panel_answers",
            ),
        )
        run = await evaluation.evaluate(
            session=session,
            fusion=fusion,
            benchmark="gpqa",
            first=1,
            seed=0,
        )

    assert run.reducer == "model"
    assert run.tie_breaker is None
    assert run.score == 100.0


@pytest.mark.asyncio
async def test_real_url4_http_app_runs_the_complete_quickstart() -> None:  # noqa: PLR0915
    ids = tuple(sf.models.list(max_price=20)[:3])
    questions = load_mock_questions(20)
    prompt_index = {question.prompt(): index for index, question in enumerate(questions)}
    calls: dict[str, list[Request]] = defaultdict(list)
    node = Url4Node("quickstart-contract")

    for model_id in ids:
        route = sf.models.get(model_id).route
        bucket = sf.models.get(model_id).mock_error_bucket

        async def answer(request: Request, *, model=model_id, error_bucket=bucket) -> str:
            calls[model].append(request)
            index = prompt_index[request.intent]
            correct = questions[index].answer
            wrong = index in range(error_bucket * 4, error_bucket * 4 + 4)
            choice = (correct + 1) % 4 if wrong else correct
            return chr(65 + choice)

        node.endpoint(route)(answer)

    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://url4.test") as http:
        session = sf.Session(
            mode="mock",
            engine_url="http://url4.test",
            engine=Url4EngineClient("http://url4.test", client=http),
            dataset_source="synthetic-gpqa-shaped",
        )
        fusion = sf.Fusion(
            "frontier-trio",
            ids,
            reducer=sf.MajorityVote(tie_breaker=ids[0]),
        )
        run = await evaluation.evaluate(
            session=session,
            fusion=fusion,
            benchmark="gpqa",
            first=20,
            seed=0,
        )

    assert run.score == 100.0
    assert run.baseline == 80.0
    assert run.gain == 20.0
    assert sum(map(len, calls.values())) == 60
    assert all(len(calls[model]) == 20 for model in ids)
    assert all(request.context == "" for rows in calls.values() for request in rows)
    assert all(request.intent in prompt_index for rows in calls.values() for request in rows)
    assert all(request.params == {} for rows in calls.values() for request in rows)


def test_majority_vote_uses_tie_breaker_without_an_extra_call() -> None:
    models = ("one", "two", "three")

    assert evaluation.majority_vote(("A", "B", "C"), models, "two") == "B"
    assert evaluation.majority_vote(("A", "B", "B"), models, "one") == "B"
    assert evaluation.majority_vote(("none", "none", "none"), models, None) == ""
