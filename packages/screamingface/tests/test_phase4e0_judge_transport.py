from __future__ import annotations

import httpx
import pytest
from url4 import Request, Url4Node, build

import screamingface as sf
from screamingface import _execution, _grading, connections
from screamingface._compiler import compile_model_expression
from screamingface._engine_http import eval_request_target_bytes
from screamingface._profile import ModelRecord, ProviderRecord, ReducerRecord, Registry


def _registry(*, limit: int) -> Registry:
    return Registry(
        models=(
            ModelRecord("codex/gpt-5.5", (), "codex"),
            ModelRecord("gemini/2.5-flash", (), "gemini"),
            ModelRecord("judge/model", (), "judge"),
        ),
        reducers=(ReducerRecord("majority_vote", "/reducers/majority-vote"),),
        response_schemas=("screamingface.fusion-result.v1",),
        max_request_target_bytes=limit,
        providers=(
            ProviderRecord("codex", "OpenAI Codex", ("oauth",)),
            ProviderRecord("gemini", "Google Gemini", ("oauth", "api_key")),
            ProviderRecord("judge", "Judge", ("api_key",)),
        ),
    )


@pytest.fixture(autouse=True)
def _connected_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    sf.config(engine="http://127.0.0.1:4404")

    def response(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/connections"
        return httpx.Response(
            200,
            json={
                "schema": "screamingface.connections.v1",
                "connections": [
                    {
                        "provider": provider.id,
                        "status": "connected",
                        "auth_method": provider.auth_methods[0],
                        "account_label": None,
                    }
                    for provider in _registry(limit=61440).providers
                ],
            },
        )

    monkeypatch.setattr(connections, "_transport", httpx.MockTransport(response))


@pytest.mark.asyncio
async def test_model_expression_uses_a_binding_for_arbitrary_literal_context() -> None:
    node = Url4Node("literal-context")
    observed: list[Request] = []

    @node.endpoint("/judge/model")
    async def judge(request: Request) -> str:
        observed.append(request)
        return "MET"

    context = (
        "An unmatched ( is ordinary answer text; $5 remains literal.\n"
        "Quotes such as 'this' and a backslash \\ also remain data."
    )
    expression = compile_model_expression(
        model="judge/model",
        context=context,
        intent="Judge $literally.",
        params={"reasoning": "low"},
    )

    assert build(expression)
    assert "model_context=" in expression
    assert "$$5 remains literal" in expression
    assert "q=($model_context)!'Judge $$literally.'" in expression

    transport = httpx.ASGITransport(app=node.asgi())
    async with httpx.AsyncClient(transport=transport, base_url="http://node.test") as client:
        response = await client.get("/v1", params={"q": expression})

    assert response.status_code == 200
    assert response.text == "MET"
    assert observed[0].context == context
    assert observed[0].intent == "Judge $literally."
    await node.aclose()


def test_eval_request_target_size_matches_the_exact_httpx_encoding() -> None:
    expression = "(/judge/model?q=($value)!'£ and spaces',value='a/b?c')"

    assert eval_request_target_bytes(expression) == len(
        httpx.URL("/v1", params={"q": expression}).raw_path
    )


def test_run_rejects_every_oversize_expression_before_engine_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fusion = sf.Fusion(
        "pair",
        ["codex/gpt-5.5", "gemini/2.5-flash"],
        reducer=sf.reducers.MajorityVote(),
    )
    benchmark = sf.Benchmark(
        "large@1",
        cases=[sf.Case("q1", "(" * 70_000, reference="A")],
        grader=sf.graders.ExactChoice(),
    )
    monkeypatch.setattr(_execution, "load_registry", lambda: _registry(limit=64))
    monkeypatch.setattr(
        _execution.httpx,
        "Client",
        lambda **_kwargs: pytest.fail("run contacted the engine"),
    )

    with pytest.raises(sf.EngineRequestTooLargeError) as caught:
        fusion.run(benchmark)

    assert caught.value.actual_bytes > caught.value.allowed_bytes == 64
    assert "case 'q1'" in str(caught.value)


def test_rubric_rejects_all_oversize_judge_calls_before_judge_spend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = sf.Benchmark(
        "rubric@1",
        cases=[
            sf.Case(
                "q1",
                "Question",
                reference={
                    "sections": [
                        {
                            "id": "facts",
                            "criteria": [{"id": "fact", "weight": 1, "requirement": "Be correct."}],
                        }
                    ]
                },
            )
        ],
        grader=sf.graders.Rubric(model="judge/model", prompt="Judge.", passes=2),
    )
    run = sf.Run(
        benchmark=benchmark,
        fusion_name="pair",
        fusion_url4="(recipe)",
        members={
            "member_1": "codex/gpt-5.5",
            "member_2": "gemini/2.5-flash",
        },
        cases=benchmark._materialize_cases(),
        results=[
            sf.CaseResult(
                "q1",
                members={
                    "member_1": sf.MemberResult("codex/gpt-5.5", "(" * 200),
                    "member_2": sf.MemberResult("gemini/2.5-flash", "answer"),
                },
                answer="(" * 200,
            )
        ],
    )
    monkeypatch.setattr(_grading, "load_registry", lambda: _registry(limit=96))
    monkeypatch.setattr(
        _grading.httpx,
        "Client",
        lambda **_kwargs: pytest.fail("grading contacted the engine"),
    )

    with pytest.raises(sf.EngineRequestTooLargeError) as caught:
        run.grade()

    assert caught.value.actual_bytes > caught.value.allowed_bytes == 96
    assert "case 'q1' fusion criterion 'fact' pass 1" in str(caught.value)
