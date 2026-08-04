"""The Engine's universal Candidate Invocation route."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from url4 import Iteration, Node, RelExpr, build, expr, iterate, render, src, text
from url4.core.errors import ResolutionError
from url4.dag import run as url4_run
from url4.observe import NodeFinished, ObservationEvent, Usage
from url4_cloud.benchmarks.definition import chat_input
from url4_cloud.benchmarks.draco.definition import DRACO, EXCLUDED_DOMAINS, JUDGE_MODEL
from url4_cloud.benchmarks.ifeval.definition import IFEVAL
from url4_cloud.benchmarks.ifeval.iterative_correction import IFEVAL_ITERATIVE_CORRECTION
from url4_cloud.runner.config import CommandSpec, DataSpec, ModelSpec, RunnerConfigError
from url4_cloud.runner.connector import AigatewayConfig, build_aigateway_world


class _Recorder:
    def __init__(self) -> None:
        self.events: list[ObservationEvent] = []

    def on_event(self, event: ObservationEvent) -> None:
        self.events.append(event)


def _link(candidate: Node, benchmark: Node) -> str:
    """The SDK's generic AST link: inert Candidate plus one nested Benchmark source."""

    if isinstance(benchmark, Iteration):
        # A top-level iteration cannot occupy the second slot of another rendered group: URL4's
        # reduce-over-iteration envelope would parse that ``*(...)`` at the outer level. Shield
        # it in its canonical instrumental passthrough before nesting it.
        benchmark = expr(
            src(benchmark, name="benchmark_result", weight=0.0),
            intent=text("$benchmark_result"),
        )
    return render(
        expr(
            src(text(render(candidate)), name="candidate", weight=0.0),
            benchmark,
            intent=text(""),
        )
    )


def _link_model_members(
    candidates: tuple[Node, ...],
    benchmark: Node,
    synthesizer: Node | None = None,
) -> str:
    """The same generic structural bindings emitted by the SDK for a Fusion."""

    bindings = [
        src(
            text(render(candidate)),
            name=f"candidate_model_member_{index}",
            weight=0.0,
        )
        for index, candidate in enumerate(candidates, 1)
    ]
    if synthesizer is not None:
        bindings.append(src(text(render(synthesizer)), name="candidate_synthesizer", weight=0.0))
    return render(expr(*bindings, benchmark, intent=text("")))


_ONE_CRITERION_RUBRIC = {
    "sections": [
        {
            "id": "correctness",
            "criteria": [{"id": "c1", "weight": 1}],
        }
    ]
}


def _draco_assets(root: Path) -> None:
    (root / "criteria").mkdir(parents=True)
    (root / "rubrics").mkdir()
    (root / "cases.json").write_text('[{"id":1,"input":"What is two plus two?"}]', encoding="utf-8")
    (root / "criteria" / "1.json").write_text(
        json.dumps(
            [
                {
                    "id": "c1",
                    "requirement": "The answer is four.",
                    "criterion_type": "positive",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "rubrics" / "1.json").write_text(json.dumps(_ONE_CRITERION_RUBRIC), encoding="utf-8")


def _draco_responder(
    calls: list[str], requests: list[dict[str, object]]
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        model = payload["model"]
        assert isinstance(model, str)
        calls.append(model)
        content = (
            "A complete answer."
            if model == "provider/candidate"
            else '{"explanation":"The answer is four.","criterion_status":"MET"}'
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return respond


@pytest.mark.asyncio
async def test_draco_definition_executes_candidate_judges_and_aggregate(tmp_path: Path) -> None:
    calls: list[str] = []
    requests: list[dict[str, object]] = []

    resource = DRACO.resource(1)
    benchmark_url4 = resource["url4"]
    assert isinstance(benchmark_url4, str)
    candidate = RelExpr(
        path="/provider/candidate",
        context="$input",
        intent=text("Answer the question."),
    )
    _draco_assets(tmp_path / "draco")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_draco_responder(calls, requests)),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/candidate",
                models=(
                    ModelSpec(id="provider/candidate", native_web_search=True),
                    ModelSpec(id=JUDGE_MODEL),
                ),
            ),
            client=client,
            benchmark_assets=tmp_path,
        )

        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark_url4)))
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["score"] == 1.0
    assert decoded["metrics"]["coverage"] == 1.0
    assert calls == ["provider/candidate", *([JUDGE_MODEL] * 5)]
    assert requests[0]["web_search"] is True
    assert requests[0]["web_search_excluded_domains"] == sorted(EXCLUDED_DOMAINS)
    for request in requests[1:]:
        serialized = json.dumps(request)
        assert "What is two plus two?" in serialized
        assert "<criterion_type>" in serialized
        assert "positive" in serialized
        assert "criterion_id" not in serialized
        assert "$answer" not in serialized


def _ifeval_assets(root: Path) -> None:
    (root / "instructions").mkdir(parents=True)
    (root / "cases.json").write_text(
        '[{"id":1,"input":"Describe tea without using any commas."}]', encoding="utf-8"
    )
    (root / "instructions" / "1.json").write_text(
        json.dumps(
            {
                "key": 1000,
                "prompt": "Describe tea without using any commas.",
                "instruction_id_list": ["punctuation:no_comma"],
                "kwargs": [{}],
            }
        ),
        encoding="utf-8",
    )


def _ifeval_responder(
    calls: list[str], requests: list[dict[str, object]]
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        model = payload["model"]
        assert isinstance(model, str)
        calls.append(model)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Tea is a warm drink made from steeped leaves."}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return respond


@pytest.mark.asyncio
async def test_ifeval_definition_executes_candidate_check_and_aggregate(tmp_path: Path) -> None:
    # INVARIANT: the judge-free exam spends exactly ONE model call per case — grading is
    # deterministic code, so a second call of any kind is a defect, not a variation.
    calls: list[str] = []
    requests: list[dict[str, object]] = []

    resource = IFEVAL.resource(1)
    benchmark_url4 = resource["url4"]
    assert isinstance(benchmark_url4, str)
    candidate = RelExpr(
        path="/provider/candidate",
        context="$input",
        intent=text("Answer the question."),
    )
    _ifeval_assets(tmp_path / "ifeval")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ifeval_responder(calls, requests)),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/candidate",
                # The route can retrieve in ordinary URL4, but IFEval's Benchmark-owned
                # Candidate policy disables it for this evaluation.
                models=(ModelSpec(id="provider/candidate", native_web_search=True),),
            ),
            client=client,
            benchmark_assets=tmp_path,
        )

        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark_url4)))
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["schema"] == "screamingface.candidate-result.v1"
    assert decoded["benchmark_id"] == "ifeval"
    assert decoded["score"] == 1.0
    assert decoded["case_count"] == 1
    assert decoded["failures"] == []
    assert calls == ["provider/candidate"]
    assert "Describe tea without using any commas." in json.dumps(requests[0])
    assert "web_search" not in requests[0]
    assert "web_search_excluded_domains" not in requests[0]


def _corrective_responder(
    calls: list[str], answers: list[str]
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        assert isinstance(model, str)
        calls.append(model)
        serialized = json.dumps(payload)
        # The first attempt fails the no-comma constraint. The Candidate then AUTHORS
        # its own feedback (the self-reflection call) and the coached retry corrects it.
        if "Do not write a new answer" in serialized:
            answer = "Remove every comma from your answer"
        elif "Previous answer" in serialized:
            answer = "Tea is a warm drink made from steeped leaves"
        else:
            answer = "Tea is warm, and it is nice."
        answers.append(answer)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return respond


@pytest.mark.asyncio
async def test_ifeval_corrective_definition_retries_until_the_check_passes(
    tmp_path: Path,
) -> None:
    # INVARIANT: the chain is UNROLLED — all three attempts execute even after a pass
    # (the R2 conditional-skip caveat): MAX_ATTEMPTS answers + two self-feedback calls.
    calls: list[str] = []
    answers: list[str] = []

    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1)
    benchmark_url4 = resource["url4"]
    assert isinstance(benchmark_url4, str)
    candidate = RelExpr(
        path="/provider/candidate",
        context="$input",
        intent=text("Answer the question."),
    )
    _ifeval_assets(tmp_path / "ifeval")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_corrective_responder(calls, answers)),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/candidate",
                models=(ModelSpec(id="provider/candidate"),),
            ),
            client=client,
            benchmark_assets=tmp_path,
        )

        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark_url4)))
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["schema"] == "screamingface.candidate-result.v1"
    assert decoded["benchmark_id"] == "ifeval-iterative-correction"
    assert calls == ["provider/candidate"] * 5
    assert decoded["score"] == 1.0
    assert decoded["metrics"]["pass_at_1"] == 0.0
    assert decoded["metrics"]["pass_at_2"] == 1.0
    assert decoded["metrics"]["corrected_cases"] == 1
    assert decoded["failures"] == []
    assert decoded["case_results"][0]["selected_attempt"] == 2


@pytest.mark.asyncio
async def test_ifeval_corrective_accepts_a_fusion_candidate(tmp_path: Path) -> None:
    """A normal Fusion's synthesized text is the answer checked on every attempt."""

    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model = payload["model"]
        assert isinstance(model, str)
        calls.append(model)
        answer = (
            "Tea is a warm drink made from steeped leaves"
            if model == "provider/synth"
            else "A useful member draft"
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1)
    benchmark_url4 = resource["url4"]
    assert isinstance(benchmark_url4, str)
    candidate = build(
        "(model_1:0.0:/provider/member-a?q=($input)!'Answer.', "
        "model_2:0.0:/provider/member-b?q=($input)!'Answer.', "
        "model_3:0.0:/provider/member-c?q=($input)!'Answer.', "
        "synthesis_1:0.0:/provider/synth?q=(payload={question: '$input', members: "
        "{member_1: {name: 'member-a', answer: '$model_1'}, "
        "member_2: {name: 'member-b', answer: '$model_2'}, "
        "member_3: {name: 'member-c', answer: '$model_3'}}})!'Synthesize.')"
        "!'$synthesis_1'"
    )
    _ifeval_assets(tmp_path / "ifeval")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/member-a",
                models=(
                    ModelSpec(id="provider/member-a"),
                    ModelSpec(id="provider/member-b"),
                    ModelSpec(id="provider/member-c"),
                    ModelSpec(id="provider/synth"),
                ),
            ),
            client=client,
            benchmark_assets=tmp_path,
        )

        try:
            result = await world.node.evaluate(_link(candidate, build(benchmark_url4)))
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["benchmark_id"] == "ifeval-iterative-correction"
    assert decoded["score"] == 1.0
    # Three answer attempts plus two self-feedback invocations, each running the
    # WHOLE Fusion (solo shape treats the Candidate as one opaque answerer).
    assert {model: calls.count(model) for model in set(calls)} == {
        "provider/member-a": 5,
        "provider/member-b": 5,
        "provider/member-c": 5,
        "provider/synth": 5,
    }


def _ensemble_responder(
    calls: list[str], requests: list[dict[str, object]]
) -> Callable[[httpx.Request], httpx.Response]:
    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        model = payload["model"]
        assert isinstance(model, str)
        calls.append(model)
        serialized = json.dumps(payload)
        if model == "provider/synth":
            # The Candidate's synthesizer serves as JUDGE: it picks a letter or
            # authors corrective feedback — it never writes an answer.
            answer = "B" if "exactly one letter" in serialized else "Drop every comma"
        elif "Judge feedback" in serialized:
            answer = "Tea is a warm drink made from steeped leaves"
        else:
            answer = "Tea is warm, fragrant and calming."
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answer}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return respond


@pytest.mark.asyncio
async def test_member_shaped_corrective_runs_member_checks_retries_and_judging(
    tmp_path: Path,
) -> None:
    """The verifying-ensemble shape: per-member checks, judge-authored feedback, select."""

    calls: list[str] = []
    requests: list[dict[str, object]] = []

    resource = IFEVAL_ITERATIVE_CORRECTION.resource(1, members=3)
    benchmark_url4 = resource["url4"]
    assert isinstance(benchmark_url4, str)
    members = tuple(
        RelExpr(
            path=f"/provider/member-{index}",
            context="$input",
            intent=text("Answer the question."),
        )
        for index in range(1, 4)
    )
    synthesizer = RelExpr(
        path="/provider/synth",
        context="$input",
        intent=text("Follow the task."),
    )
    _ifeval_assets(tmp_path / "ifeval")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_ensemble_responder(calls, requests)),
        base_url="http://aigateway.test",
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(
                default_model="provider/member-1",
                models=(
                    *(ModelSpec(id=f"provider/member-{index}") for index in range(1, 4)),
                    ModelSpec(id="provider/synth"),
                ),
            ),
            client=client,
            benchmark_assets=tmp_path,
        )

        try:
            result = await world.node.evaluate(
                _link_model_members(members, build(benchmark_url4), synthesizer)
            )
        finally:
            await world.aclose()

    decoded = json.loads(result.text)
    assert decoded["benchmark_id"] == "ifeval-iterative-correction"
    assert decoded["score"] == 1.0
    assert decoded["failures"] == []
    assert decoded["metrics"]["pass_at_1"] == 0.0
    assert decoded["metrics"]["pass_at_2"] == 1.0
    # 9 member answers + 3 judge picks + 2 judge feedback authorings, all unrolled.
    assert calls.count("provider/synth") == 5
    assert len(calls) == 14
    # Judge-authored feedback reaches every member on attempts two and three.
    assert (
        sum(
            request["model"] != "provider/synth" and "Judge feedback" in json.dumps(request)
            for request in requests
        )
        == 6
    )


@pytest.mark.asyncio
async def test_candidate_expression_runs_with_the_invocation_input() -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "candidate answer"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )

    model = "provider/model"
    candidate = RelExpr(
        path=f"/{model}",
        context="$input",
        intent=text("Answer the request."),
    )
    benchmark = RelExpr(
        path="/candidate",
        context="What is 2 + 2?",
        intent=text("$candidate"),
    )
    linked = _link(candidate, benchmark)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            result = await world.node.evaluate(linked)
        finally:
            await world.aclose()

    assert result.text == "candidate answer"
    assert len(requests) == 1
    assert "What is 2 + 2?" in json.dumps(requests[0]["messages"])


@pytest.mark.asyncio
async def test_later_invocation_can_receive_an_earlier_candidate_answer() -> None:
    requests: list[dict[str, object]] = []
    answers = iter(("first answer", "second answer"))

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": next(answers)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    model = "provider/model"
    candidate = RelExpr(
        path=f"/{model}",
        context="$input",
        intent=text("Answer the request."),
    )
    first = RelExpr(path="/candidate", context="first question", intent=text("$candidate"))
    second = RelExpr(
        path="/candidate",
        context="Continue from this answer: $first",
        intent=text("$candidate"),
    )
    benchmark = expr(
        src(first, name="first", weight=0.0),
        src(second, name="second", weight=0.0),
        intent=text("$second"),
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            result = await world.node.evaluate(_link(candidate, benchmark))
        finally:
            await world.aclose()

    assert result.text == "second answer"
    assert len(requests) == 2
    assert "first question" in json.dumps(requests[0]["messages"])
    assert "first answer" in json.dumps(requests[1]["messages"])


@pytest.mark.asyncio
async def test_candidate_input_preserves_healthbench_style_native_chat_turns() -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "candidate answer"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    model = "provider/model"
    candidate = RelExpr(
        path=f"/{model}",
        context="$input",
        intent=text("Candidate-owned policy."),
    )
    turns = [
        {"role": "user", "content": "I have a persistent cough."},
        {"role": "assistant", "content": "How long has it lasted?"},
        {"role": "user", "content": "About three weeks."},
    ]
    benchmark = RelExpr(
        path="/candidate",
        context=chat_input(turns),
        intent=text("$candidate"),
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            result = await world.node.evaluate(_link(candidate, benchmark))
        finally:
            await world.aclose()

    assert result.text == "candidate answer"
    assert requests[0]["messages"] == [
        {"role": "system", "content": "Candidate-owned policy."},
        *turns,
    ]


@pytest.mark.asyncio
async def test_invalid_native_chat_input_fails_before_a_model_request() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    model = "provider/model"
    candidate = RelExpr(path=f"/{model}", context="$input", intent=text("Answer."))
    benchmark = RelExpr(
        path="/candidate",
        context=chat_input("not-json"),
        intent=text("$candidate"),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            with pytest.raises(ResolutionError) as exc_info:
                await world.node.evaluate(_link(candidate, benchmark))
        finally:
            await world.aclose()

    assert exc_info.value.code == "invalid_candidate_input"
    assert exc_info.value.permanent is True
    assert requests == []


@pytest.mark.asyncio
async def test_candidate_input_replays_medxpert_reasoning_as_an_assistant_turn() -> None:
    requests: list[dict[str, object]] = []
    answers = iter(('Reasoning with "quoted evidence".', "B"))

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": next(answers)}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    model = "provider/model"
    candidate = RelExpr(
        path=f"/{model}",
        context="$input",
        intent=text("Candidate-owned policy."),
    )
    question = "Which option is correct? A. Alpha B. Beta"
    first = RelExpr(
        path="/candidate",
        context=chat_input([{"role": "user", "content": question}]),
        intent=text("$candidate"),
    )
    second_turns = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": "$reasoning"},
        {"role": "user", "content": "Return only the answer letter."},
    ]
    second = RelExpr(
        path="/candidate",
        context=chat_input(second_turns),
        intent=text("$candidate"),
    )
    benchmark = expr(
        src(first, name="reasoning", weight=0.0),
        src(second, name="commit", weight=0.0),
        intent=text("$commit"),
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            result = await world.node.evaluate(_link(candidate, benchmark))
        finally:
            await world.aclose()

    assert result.text == "B"
    assert requests[1]["messages"] == [
        {"role": "system", "content": "Candidate-owned policy."},
        {"role": "user", "content": question},
        {"role": "assistant", "content": 'Reasoning with "quoted evidence".'},
        {"role": "user", "content": "Return only the answer letter."},
    ]


def test_chat_input_rejects_malformed_python_messages_while_authoring() -> None:
    with pytest.raises(ValueError, match="unsupported role"):
        chat_input([{"role": "tool", "content": "result"}])

    with pytest.raises(TypeError, match="content must be text"):
        chat_input([{"role": "user", "content": 42}])


@pytest.mark.asyncio
async def test_scicode_style_steps_carry_code_through_sandbox_grading() -> None:
    generated = iter(("```python\nx = 1\n```", "```python\ny = x + 1\n```"))
    candidate_inputs: list[str] = []
    sandbox_inputs: list[str] = []
    model = "provider/model"
    candidate = RelExpr(path="/generate", context="$input", intent=text("generate"))
    first = RelExpr(path="/candidate", context="Implement step 1.", intent=text("$candidate"))
    first_code = RelExpr(path="/extract", context="$first", intent=text("extract"))
    first_grade = RelExpr(path="/sandbox", context="$code_1", intent=text("grade step 1"))
    second = RelExpr(
        path="/candidate",
        context="Implement step 2 using prior code: $code_1. Prior grade: $grade_1.",
        intent=text("$candidate"),
    )
    second_code = RelExpr(path="/extract", context="$second", intent=text("extract"))
    second_grade = RelExpr(path="/sandbox", context="$code_2", intent=text("grade step 2"))
    benchmark = expr(
        src(first, name="first", weight=0.0),
        src(first_code, name="code_1", weight=0.0),
        src(first_grade, name="grade_1", weight=0.0),
        src(second, name="second", weight=0.0),
        src(second_code, name="code_2", weight=0.0),
        src(second_grade, name="grade_2", weight=0.0),
        intent=text("$grade_2"),
    )
    world = await build_aigateway_world(
        AigatewayConfig(default_model=model, models=(ModelSpec(id=model),))
    )

    @world.node.endpoint("/generate")
    def generate(request) -> str:
        candidate_inputs.append(request.context)
        return next(generated)

    @world.node.endpoint("/extract")
    def extract(request) -> str:
        return request.context.removeprefix("```python\n").removesuffix("\n```")

    @world.node.endpoint("/sandbox")
    def sandbox(request) -> str:
        sandbox_inputs.append(request.context)
        return "pass"

    try:
        result = await world.node.evaluate(_link(candidate, benchmark))
    finally:
        await world.aclose()

    assert result.text == "pass"
    assert candidate_inputs == [
        "Implement step 1.",
        "Implement step 2 using prior code: x = 1. Prior grade: pass.",
    ]
    assert sandbox_inputs == ["x = 1", "y = x + 1"]


@pytest.mark.asyncio
async def test_candidate_expression_can_be_a_nested_fusion_graph() -> None:
    requests: dict[str, dict[str, object]] = {}
    answers = {
        "provider/left": "left answer",
        "provider/right": "right answer",
        "provider/synthesizer": "combined answer",
    }

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        model = body["model"]
        requests[model] = body
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": answers[model]}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    candidate = expr(
        src(
            RelExpr(
                path="/provider/left",
                context="$input",
                intent=text("Answer independently."),
            ),
            name="left",
            weight=0.0,
        ),
        src(
            RelExpr(
                path="/provider/right",
                context="$input",
                intent=text("Answer independently."),
            ),
            name="right",
            weight=0.0,
        ),
        src(
            RelExpr(
                path="/provider/synthesizer",
                context="question: $input; left: $left; right: $right",
                intent=text("Synthesize the panel."),
            ),
            name="synthesis",
            weight=0.0,
        ),
        intent=text("$synthesis"),
    )
    benchmark = RelExpr(
        path="/candidate",
        context="Explain why the sky is blue.",
        intent=text("$candidate"),
    )
    models = tuple(ModelSpec(id=model) for model in answers)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model="provider/left", models=models),
            client=client,
        )
        try:
            result = await world.node.evaluate(_link(candidate, benchmark))
        finally:
            await world.aclose()

    assert result.text == "combined answer"
    assert set(requests) == set(answers)
    synthesis_messages = json.dumps(requests["provider/synthesizer"]["messages"])
    assert "Explain why the sky is blue." in synthesis_messages
    assert "left answer" in synthesis_messages
    assert "right answer" in synthesis_messages


@pytest.mark.asyncio
async def test_nested_candidate_model_usage_reaches_the_outer_run_observer() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "candidate answer"}}],
                "usage": {"prompt_tokens": 13, "completion_tokens": 8},
            },
        )

    model = "provider/model"
    candidate = RelExpr(
        path=f"/{model}",
        context="$input",
        intent=text("Answer the request."),
    )
    benchmark = RelExpr(
        path="/candidate",
        context="question",
        intent=text("$candidate"),
    )
    recorder = _Recorder()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://aigateway.test"
    ) as client:
        world = await build_aigateway_world(
            AigatewayConfig(default_model=model, models=(ModelSpec(id=model),)),
            client=client,
        )
        try:
            result = await url4_run(_link(candidate, benchmark), world.node, observer=recorder)
        finally:
            await world.aclose()

    assert result == "candidate answer"
    usages = [event for event in recorder.events if isinstance(event, Usage)]
    assert [(event.provider, event.model) for event in usages] == [("provider", model)]
    assert sum(event.input_tokens for event in usages) == 13
    assert sum(event.output_tokens for event in usages) == 8


@pytest.mark.asyncio
async def test_candidate_failure_keeps_its_typed_error_on_the_outer_span() -> None:
    model = "provider/model"
    candidate = RelExpr(
        path="/missing-model",
        context="$input",
        intent=text("Answer the request."),
    )
    benchmark = RelExpr(
        path="/candidate",
        context="question",
        intent=text("$candidate"),
    )
    recorder = _Recorder()

    world = await build_aigateway_world(
        AigatewayConfig(default_model=model, models=(ModelSpec(id=model),))
    )
    try:
        with pytest.raises(ResolutionError) as exc_info:
            await url4_run(_link(candidate, benchmark), world.node, observer=recorder)
    finally:
        await world.aclose()

    assert exc_info.value.code == "endpoint_not_found"
    assert exc_info.value.permanent is True
    failed = [
        event
        for event in recorder.events
        if isinstance(event, NodeFinished) and event.status == "error"
    ]
    assert [(event.code, event.permanent) for event in failed] == [("endpoint_not_found", True)]


@pytest.mark.asyncio
async def test_cancelling_the_outer_run_cancels_candidate_work() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()
    never = asyncio.Event()
    model = "provider/model"
    candidate = RelExpr(path="/gated", context="$input", intent=text("wait"))
    benchmark = RelExpr(
        path="/candidate",
        context="question",
        intent=text("$candidate"),
    )

    world = await build_aigateway_world(
        AigatewayConfig(default_model=model, models=(ModelSpec(id=model),))
    )

    @world.node.endpoint("/gated")
    async def gated(_request) -> str:
        started.set()
        try:
            await never.wait()
        finally:
            cancelled.set()
        return "unreachable"

    task = asyncio.create_task(url4_run(_link(candidate, benchmark), world.node))
    try:
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), timeout=1.0)
    finally:
        if not task.done():
            task.cancel()
        await world.aclose()


@pytest.mark.asyncio
async def test_candidate_expression_cannot_recursively_invoke_candidate() -> None:
    model = "provider/model"
    leaf = RelExpr(path="/leaf", context="$input", intent=text("answer"))
    candidate = RelExpr(
        path="/candidate",
        context="$input",
        intent=text(render(leaf)),
    )
    benchmark = RelExpr(
        path="/candidate",
        context="question",
        intent=text("$candidate"),
    )
    world = await build_aigateway_world(
        AigatewayConfig(default_model=model, models=(ModelSpec(id=model),))
    )
    world.node.endpoint("/leaf")(lambda _request: "should not run")

    try:
        with pytest.raises(ResolutionError) as exc_info:
            await world.node.evaluate(_link(candidate, benchmark))
    finally:
        await world.aclose()

    assert exc_info.value.code == "candidate_recursion"
    assert exc_info.value.permanent is True


@pytest.mark.asyncio
async def test_world_caps_total_candidate_invocations() -> None:
    model = "provider/model"
    candidate = RelExpr(path="/leaf", context="$input", intent=text("answer"))
    first = RelExpr(path="/candidate", context="one", intent=text("$candidate"))
    second = RelExpr(path="/candidate", context="$first two", intent=text("$candidate"))
    third = RelExpr(path="/candidate", context="$second three", intent=text("$candidate"))
    benchmark = expr(
        src(first, name="first", weight=0.0),
        src(second, name="second", weight=0.0),
        src(third, name="third", weight=0.0),
        intent=text("$third"),
    )
    world = await build_aigateway_world(
        AigatewayConfig(
            default_model=model,
            models=(ModelSpec(id=model),),
            candidate_max_invocations=2,
        )
    )
    world.node.endpoint("/leaf")(lambda request: request.context)

    try:
        with pytest.raises(ResolutionError) as exc_info:
            await world.node.evaluate(_link(candidate, benchmark))
    finally:
        await world.aclose()

    assert exc_info.value.code == "candidate_invocation_limit"
    assert exc_info.value.permanent is True


@pytest.mark.asyncio
async def test_top_level_benchmark_iteration_can_invoke_the_linked_candidate() -> None:
    model = "provider/model"
    candidate = RelExpr(path="/leaf", context="$input", intent=text("answer"))
    benchmark = iterate(
        "/cases",
        body=(
            src("$item.question", name="question", weight=0.0),
            src(
                RelExpr(
                    path="/candidate",
                    context="$question",
                    intent=text("$candidate"),
                ),
                name="answer",
                weight=0.0,
            ),
        ),
        intent=text("$answer"),
        on_error="fail",
    )
    linked = _link(candidate, benchmark)
    world = await build_aigateway_world(
        AigatewayConfig(default_model=model, models=(ModelSpec(id=model),))
    )
    world.node.data(
        "/cases",
        json.dumps([{"question": "one"}, {"question": "two"}]),
        media_type="application/json",
    )
    world.node.endpoint("/leaf")(lambda request: request.context)

    try:
        result = await world.node.evaluate(linked)
    finally:
        await world.aclose()

    assert json.loads(result.text) == ["one", "two"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "commands", "data"),
    [
        (
            AigatewayConfig(
                default_model="candidate",
                models=(ModelSpec(id="candidate"),),
            ),
            (),
            (),
        ),
        (
            AigatewayConfig(
                default_model="provider/model",
                models=(ModelSpec(id="provider/model"),),
            ),
            (CommandSpec(path="/candidate", argv=("echo",)),),
            (),
        ),
        (
            AigatewayConfig(
                default_model="provider/model",
                models=(ModelSpec(id="provider/model"),),
            ),
            (),
            (DataSpec(path="/candidate", value="shadow"),),
        ),
    ],
)
async def test_candidate_route_is_reserved_from_operator_configuration(
    config: AigatewayConfig,
    commands: tuple[CommandSpec, ...],
    data: tuple[DataSpec, ...],
) -> None:
    with pytest.raises(RunnerConfigError, match="'/candidate'.*reserved"):
        await build_aigateway_world(config, commands=commands, data=data)
