from __future__ import annotations

import asyncio
import json

import pytest
from url4 import Request, ResolutionError

from screamingface_engine.catalog import ModelRoute
from screamingface_engine.draco_grader import DracoRubricGrader

JUDGE = ModelRoute(
    "openrouter/google/gemini-3.1-pro-preview",
    "openrouter/google/gemini-3.1-pro-preview",
    "openrouter",
)


class FakeExecutor:
    def __init__(self, replies: list[str] | None = None) -> None:
        self.calls: list[Request] = []
        self.replies = replies or []

    async def complete(self, _model: ModelRoute, request: Request) -> str:
        self.calls.append(request)
        if self.replies:
            return self.replies.pop(0)
        return '{"explanation":"present","criterion_status":"MET"}'


class RaisingExecutor:
    async def complete(self, _model: ModelRoute, _request: Request) -> str:
        raise ResolutionError("judge unavailable", code="provider_unavailable")


class BlockingExecutor(FakeExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.peak = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, _model: ModelRoute, request: Request) -> str:
        self.calls.append(request)
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active == 2:
            self.started.set()
        await self.release.wait()
        self.active -= 1
        return '{"explanation":"present","criterion_status":"MET"}'


def _request(*, same_answer: bool = True) -> Request:
    recipe = {
        "schema": "screamingface.recipe-result.v1",
        "members": {
            "member_1": {
                "model": "openrouter/openai/gpt-5.5",
                "answer": "Combined answer" if same_answer else "Member answer",
            }
        },
        "answer": "Combined answer",
    }
    case = {
        "benchmark_id": "draco-preview@1",
        "case_id": "q1",
        "question": "Research question",
        "reference": {
            "id": "r1",
            "sections": [
                {
                    "id": "factual-accuracy",
                    "title": "Accuracy",
                    "criteria": [
                        {"id": "positive", "requirement": "State the fact", "weight": 5},
                        {"id": "negative", "requirement": "State an error", "weight": -1},
                    ],
                }
            ],
        },
    }
    return Request("/graders/draco-preview-rubric/1", json.dumps(recipe), json.dumps(case), {})


def _parts() -> tuple[dict[str, object], dict[str, object]]:
    request = _request()
    return json.loads(request.context), json.loads(request.intent)


@pytest.mark.asyncio
async def test_draco_grader_applies_weighted_formula_and_reuses_identical_answers() -> None:
    executor = FakeExecutor()
    grader = DracoRubricGrader(executor, JUDGE, passes=1)  # type: ignore[arg-type]

    payload = json.loads(await grader(_request()))

    assert len(executor.calls) == 2
    assert payload["recipe"]["score"] == pytest.approx(0.8)
    assert payload["recipe"]["metrics"]["pass_rate"] == pytest.approx(0.5)
    assert payload["recipe"] == {
        key: value for key, value in payload["members"]["member_1"].items() if key != "model"
    }
    assert "<criterion_type>\nnegative\n</criterion_type>" in executor.calls[1].context
    assert executor.calls[0].intent.startswith("You are evaluating a response")
    assert executor.calls[0].params == {
        "temperature": "0.2",
        "reasoning": "low",
        "max_tokens": "4096",
    }


@pytest.mark.asyncio
async def test_judge_concurrency_is_shared_across_answers() -> None:
    executor = BlockingExecutor()
    grader = DracoRubricGrader(executor, JUDGE, passes=1, concurrency=2)  # type: ignore[arg-type]
    _recipe, case = _parts()
    question = str(case["question"])
    reference = case["reference"]
    tasks = [
        asyncio.create_task(grader.grade_answer(question, reference, f"answer-{index}"))
        for index in range(2)
    ]

    await asyncio.wait_for(executor.started.wait(), timeout=1)
    assert executor.active == 2
    executor.release.set()
    await asyncio.gather(*tasks)
    assert executor.peak == 2


@pytest.mark.asyncio
async def test_draco_grader_grades_distinct_recipe_and_member_answers() -> None:
    executor = FakeExecutor()
    grader = DracoRubricGrader(executor, JUDGE, passes=1)  # type: ignore[arg-type]

    await grader(_request(same_answer=False))

    assert len(executor.calls) == 4


@pytest.mark.asyncio
async def test_draco_grader_retries_invalid_judge_json_then_fails_loudly() -> None:
    executor = FakeExecutor(["bad", "bad", "bad", "bad", "bad", "bad"])
    grader = DracoRubricGrader(executor, JUDGE, passes=1)  # type: ignore[arg-type]

    with pytest.raises(ResolutionError, match="no valid") as raised:
        await grader(_request())

    assert raised.value.code == "invalid_judge_response"
    assert len(executor.calls) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda recipe, _case: recipe.update(schema="wrong"), "expected Recipe schema"),
        (lambda recipe, _case: recipe.update(members={}), "non-empty object"),
        (
            lambda recipe, _case: recipe.update(
                members={"member_2": {"model": "model", "answer": "answer"}}
            ),
            "contiguous",
        ),
        (lambda _recipe, case: case.update(reference=[]), "rubric object"),
        (lambda _recipe, case: case.update(reference={"sections": []}), "contain sections"),
        (
            lambda _recipe, case: case.update(reference={"sections": ["bad"]}),
            "sections must be objects",
        ),
        (
            lambda _recipe, case: case.update(
                reference={"sections": [{"id": "axis", "criteria": []}]}
            ),
            "sections must contain criteria",
        ),
        (
            lambda _recipe, case: case.update(
                reference={"sections": [{"id": "axis", "criteria": ["bad"]}]}
            ),
            "criteria must be objects",
        ),
        (
            lambda _recipe, case: case.update(
                reference={
                    "sections": [
                        {
                            "id": "axis",
                            "criteria": [
                                {"id": "x", "requirement": "x", "weight": 1},
                                {"id": "x", "requirement": "y", "weight": 1},
                            ],
                        }
                    ]
                }
            ),
            "duplicate criterion",
        ),
        (
            lambda _recipe, case: case.update(
                reference={
                    "sections": [
                        {
                            "id": "axis",
                            "criteria": [{"id": "x", "requirement": "x", "weight": "1"}],
                        }
                    ]
                }
            ),
            "weight must be numeric",
        ),
        (
            lambda _recipe, case: case.update(
                reference={
                    "sections": [
                        {
                            "id": "axis",
                            "criteria": [{"id": "x", "requirement": "x", "weight": 0}],
                        }
                    ]
                }
            ),
            "finite and non-zero",
        ),
        (lambda _recipe, case: case.pop("question"), "missing field"),
    ],
)
async def test_draco_grader_rejects_malformed_inputs(mutate, message: str) -> None:
    recipe, case = _parts()
    mutate(recipe, case)
    grader = DracoRubricGrader(FakeExecutor(), JUDGE, passes=1)  # type: ignore[arg-type]

    with pytest.raises(ResolutionError, match=message) as raised:
        await grader(
            Request(
                "/graders/draco-preview-rubric/1",
                json.dumps(recipe),
                json.dumps(case),
                {},
            )
        )

    assert raised.value.code == "malformed_source"


@pytest.mark.asyncio
async def test_draco_grader_rejects_params_and_non_object_json() -> None:
    grader = DracoRubricGrader(FakeExecutor(), JUDGE, passes=1)  # type: ignore[arg-type]
    request = _request()
    with pytest.raises(ResolutionError, match="parameters"):
        await grader(Request(request.path, request.context, request.intent, {"x": "1"}))
    with pytest.raises(ResolutionError, match="JSON object"):
        await grader(Request(request.path, "[]", request.intent, {}))


@pytest.mark.asyncio
async def test_draco_grader_cancels_sibling_judge_work_on_transport_failure() -> None:
    grader = DracoRubricGrader(RaisingExecutor(), JUDGE, passes=2)  # type: ignore[arg-type]

    with pytest.raises(ResolutionError, match="judge unavailable"):
        await grader(_request())


@pytest.mark.asyncio
async def test_draco_grader_accepts_fenced_judge_json() -> None:
    reply = '```json\n{"explanation":"present","criterion_status":"MET"}\n```'
    grader = DracoRubricGrader(FakeExecutor([reply, reply]), JUDGE, passes=1)  # type: ignore[arg-type]

    payload = json.loads(await grader(_request()))

    assert payload["recipe"]["score"] == pytest.approx(0.8)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "intent", "message"),
    [
        ("not-json", _request().intent, "unique-key JSON object"),
        ('{"schema":"a","schema":"b"}', _request().intent, "unique-key JSON object"),
        (
            _request().context,
            json.dumps({**json.loads(_request().intent), "extra": True}),
            "unknown field",
        ),
        (
            _request().context,
            json.dumps({**json.loads(_request().intent), "case_id": " "}),
            "non-blank",
        ),
    ],
)
async def test_draco_grader_rejects_strict_json_edges(
    context: str, intent: str, message: str
) -> None:
    grader = DracoRubricGrader(FakeExecutor(), JUDGE, passes=1)  # type: ignore[arg-type]

    with pytest.raises(ResolutionError, match=message):
        await grader(Request("/graders/draco-preview-rubric/1", context, intent, {}))
