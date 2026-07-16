from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

import screamingface as sf
import screamingface.data as data
import screamingface.evaluation as evaluation
import screamingface.session as session_module
from screamingface.errors import DatasetUnavailable, GatewayError, LoginRequired
from screamingface.evaluation import (
    ModelAnswer,
    QuestionIOLayer,
    _majority_processor,
    normalize_answer,
)
from screamingface.gateway import AIGatewayClient, Completion, Connection, GatewayLogin


@pytest.fixture(autouse=True)
def _clean_session() -> None:
    sf.reset_session()


def test_question_loading_boundaries_and_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    question = data.load_mock_questions(1)[0]
    assert "A." in question.prompt()
    assert "Reply with only A, B, C, or D." in question.prompt()
    with pytest.raises(ValueError, match="positive"):
        data.load_mock_questions(0)
    with pytest.raises(ValueError, match="contains 20"):
        data.load_mock_questions(21)

    def missing(_name: str):
        raise ImportError

    monkeypatch.setattr(data, "import_module", missing)
    with pytest.raises(DatasetUnavailable, match="datasets"):
        data.load_live_questions(1, 0)


def test_live_question_loading_is_seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "Question": "Which option is correct?",
            "Correct Answer": "right",
            "Incorrect Answer 1": "wrong 1",
            "Incorrect Answer 2": "wrong 2",
            "Incorrect Answer 3": "wrong 3",
        }
    ]
    loader = SimpleNamespace(load_dataset=lambda *args, **kwargs: rows)
    monkeypatch.setattr(data, "import_module", lambda _name: loader)

    first = data.load_live_questions(1, 7)[0]
    second = data.load_live_questions(1, 7)[0]
    assert first == second
    assert first.options[first.answer] == "right"
    with pytest.raises(ValueError, match="positive"):
        data.load_live_questions(0, 0)
    with pytest.raises(ValueError, match="contains 1"):
        data.load_live_questions(2, 0)


class AnswerAdapter:
    async def answer(self, model: str, question: data.Question, *, seed: int) -> ModelAnswer:
        return ModelAnswer(f"answer A from {model} at {seed}", 0.25)


@pytest.mark.asyncio
async def test_io_layer_and_majority_boundaries() -> None:
    question = data.load_mock_questions(1)[0]
    io = QuestionIOLayer(question, AnswerAdapter(), 3)
    assert await io.fetch("sf-model://codex/gpt-5.5", relative=False) == "A"
    assert io.cost_usd == 0.25
    with pytest.raises(ValueError, match="relative"):
        await io.fetch("anything", relative=True)
    with pytest.raises(ValueError, match="unsupported"):
        await io.fetch("https://example.test", relative=False)

    process = _majority_processor(("one", "two"), "two")
    assert await process("A\nB", "majority_vote", None) == "B"
    assert await process("none", "majority_vote", None) == ""
    with pytest.raises(ValueError, match="unsupported reducer"):
        await process("A", "other", None)
    assert normalize_answer("no selection") == ""


def test_sync_evaluation_boundary() -> None:
    sf.setup(mode="mock")
    ids = sf.models.list()
    fusion = sf.Fusion("async-notebook", ids[:3], judge=ids[0])
    assert fusion.evaluate("gpqa", first=1, seed=0).sample_size == 1


@pytest.mark.asyncio
async def test_evaluation_reports_loading_and_question_progress() -> None:
    session = sf.setup(mode="mock", interactive=False)
    assert isinstance(session, sf.Session)
    ids = sf.models.list()
    fusion = sf.Fusion("visible-progress", ids[:3], judge=ids[0])
    events: list[tuple[int, int, str]] = []

    run = await evaluation.evaluate(
        session=session,
        fusion=fusion,
        benchmark="gpqa",
        first=2,
        seed=0,
        progress=lambda completed, total, message: events.append((completed, total, message)),
    )

    assert run.sample_size == 2
    assert events[0] == (0, 6, "Loading GPQA sample")
    assert any("Question 1/2" in message for _, _, message in events)
    assert {completed for completed, _, _ in events} >= {0, 1, 2, 3, 4, 5, 6}
    assert events[-1] == (6, 6, "Complete")


def test_notebook_progress_widget_reports_timeout_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    displayed: list[object] = []
    monkeypatch.setattr("IPython.display.display", displayed.append)

    progress = evaluation._NotebookProgress(2)
    progress.update(1, 2, "Question 2/2")

    assert displayed
    assert progress._bar.value == 1
    assert "Question 2/2" in progress._status.value
    assert "30 seconds" in progress._status.value


def test_session_and_fusion_validation() -> None:
    with pytest.raises(RuntimeError, match="setup"):
        sf.models.list()
    with pytest.raises(ValueError, match="mode"):
        sf.setup(mode=cast(session_module.Mode, "invalid"))
    session = sf.setup(mode="mock")
    assert "SIMULATION" in session._repr_html_()
    ids = sf.models.list()
    with pytest.raises(ValueError, match="empty"):
        sf.Fusion(" ", ids[:2])
    with pytest.raises(ValueError, match="at least two"):
        sf.Fusion("one", ids[:1])
    with pytest.raises(ValueError, match="unknown"):
        sf.Fusion("unknown", [ids[0], "vendor/missing"])
    with pytest.raises(ValueError, match="majority_vote"):
        sf.Fusion("bad reducer", ids[:2], reduce="mean")
    with pytest.raises(ValueError, match="gpqa"):
        sf.Fusion("ok", ids[:2]).evaluate("other")


class SetupClient:
    healthy = True
    saw_me = False
    closed = False

    def __init__(self, base_url: str, *, token: str | None, timeout: float) -> None:
        self.base_url = base_url
        self.token = token

    async def health(self) -> bool:
        return self.healthy

    async def me(self) -> dict[str, str]:
        self.saw_me = True
        return {"username": "reader"}

    async def login(self, username: str, password: str) -> GatewayLogin:
        assert username == "reader"
        assert password == "password"
        self.token = "jwt"
        return GatewayLogin("jwt", datetime.now(UTC), username)

    async def aclose(self) -> None:
        self.closed = True

    async def list_models(self) -> list[str]:
        return []

    async def list_connections(self) -> list[Connection]:
        return [Connection("codex-personal", "codex", "personal", "active")]


def test_live_setup_login_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "AIGatewayClient", SetupClient)
    with pytest.raises(LoginRequired):
        sf.setup(gateway="https://gateway.test")

    live = sf.setup(gateway="https://gateway.test", token="jwt")
    assert live.mode == "live"
    assert "LIVE" in live._repr_html_()
    assert live.profiles == {"codex": "personal"}
    assert sf.models.list() == []

    logged_in = sf.setup(
        gateway="https://gateway.test",
        username="reader",
        password="password",
    )
    assert logged_in.mode == "live"


def test_live_setup_validates_credentials_and_profile_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_module, "AIGatewayClient", SetupClient)
    with pytest.raises(ValueError, match="together"):
        sf.setup(gateway="https://gateway.test", username="reader")
    with pytest.raises(GatewayError, match="No active codex profile"):
        sf.setup(
            gateway="https://gateway.test",
            token="jwt",
            profiles={"codex": "missing"},
        )

    class AmbiguousClient(SetupClient):
        async def list_connections(self) -> list[Connection]:
            return [
                Connection("codex-one", "codex", "one", "active"),
                Connection("codex-two", "codex", "two", "active"),
            ]

    monkeypatch.setattr(session_module, "AIGatewayClient", AmbiguousClient)
    with pytest.raises(sf.AmbiguousProfile):
        sf.setup(gateway="https://gateway.test", token="jwt")


def test_run_helper_supports_active_loop() -> None:
    async def loop_identity() -> int:
        return id(asyncio.get_running_loop())

    async def check() -> None:
        assert session_module._run(asyncio.sleep(0, result="done")) == "done"

    asyncio.run(check())
    assert session_module._run(loop_identity()) == session_module._run(loop_identity())


def test_result_live_representation() -> None:
    run = sf.Run(
        benchmark="GPQA",
        dataset_source="gated",
        mode="live",
        models=("a", "b"),
        url="(a,b)",
        sample_size=1,
        seed=0,
        score=100,
        baseline=50,
        gain=50,
        cost_usd=0.01,
        fusion_name="safe <fusion>",
        reduce="majority_vote",
        judge="a",
        model_results=(
            sf.ModelResult("a", 50, 1, 1, 2, 0.005),
            sf.ModelResult("b", 25, 1, 1, 2, 0.005, failures=1),
        ),
    )
    html = run._repr_html_()
    assert "LIVE PROVIDER RUN" in html
    assert "safe &lt;fusion&gt;" in html
    assert "fusion accuracy" in html
    assert "gain over best" in html
    assert "PER-MODEL ACCURACY" in html
    assert "1 failures" in html
    assert "<fusion>" not in html


@pytest.mark.asyncio
async def test_gateway_network_and_validation_errors() -> None:
    async def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = AIGatewayClient("https://gateway.test", transport=httpx.MockTransport(broken))
    assert await client.health() is False
    await client.aclose()

    def response(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        payloads = {
            "/v1/auth/login": {"token": "jwt", "expires_at": "bad", "account": {}},
            "/v1/models": {"data": "bad"},
            "/v1/oauth/connections": {"connections": "bad"},
        }
        payload = payloads.get(path)
        return (
            httpx.Response(200, json=payload)
            if payload is not None
            else httpx.Response(500, text="secret-body")
        )

    client = AIGatewayClient(
        "https://gateway.test", token="jwt", transport=httpx.MockTransport(response)
    )
    with pytest.raises(GatewayError, match="invalid timestamp"):
        await client.login("u", "p")
    with pytest.raises(GatewayError, match="missing data"):
        await client.list_models()
    with pytest.raises(GatewayError, match="missing connections"):
        await client.list_connections()
    with pytest.raises(GatewayError) as error:
        await client.me()
    assert "secret-body" not in str(error.value)
    await client.aclose()

    login = GatewayLogin("secret", datetime.now(UTC), "reader")
    assert "secret" not in repr(login)
    assert Completion("A").total_tokens == 0


@pytest.mark.asyncio
async def test_tied_vote_selects_the_judges_existing_answer() -> None:
    # INVARIANT: spec §7 — a tied vote selects the configured member judge's existing
    # answer, even when that answer is not among the tied leaders. The deterministic
    # alphabetical fallback applies only without a judge or when the judge produced
    # no valid answer.
    members = ("m1", "m2", "m3", "m4", "m5")
    judged = _majority_processor(members, "m5")
    assert await judged("A\nA\nB\nB\nC", "majority_vote", None) == "C"
    judgeless = _majority_processor(members, None)
    assert await judgeless("A\nA\nB\nB\nC", "majority_vote", None) == "A"
    invalid_judge = _majority_processor(members, "m5")
    assert await invalid_judge("A\nA\nB\nB\nnone", "majority_vote", None) == "A"
