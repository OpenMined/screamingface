"""End-to-end: /ensemble with run headers persists one eval_run + N eval_questions (SF-165).

Drives the full path through url4-executor -> python-runner -> eval-runs
subscribers, in-process via httpx.ASGITransport.

Payload-shape note
------------------
The URL4 grammar's intent ``text`` atom matches ``[^,()]+`` (see
``url4_grammar.py``), so the inline JSON we attach as a backend-call
intent cannot contain commas. The canonical check_correct payload
``{"question":..., "expected":..., "predicted":...}`` is comma-separated
and would fail to tokenize. We therefore use a single-key payload
``{"q":"<question>"}`` and have the test script derive ``expected`` /
``predicted`` from that single value. The python-runner plugin reads
``question``/``expected`` from the intent JSON to populate the
``eval.question.checked`` event; with a single-key payload those fall
back to empty strings, and we assert accordingly. ``predicted`` /
``correct`` / ``raw_output`` come from the script's stdout JSON and
remain meaningful.

The outer ``(...)`` around the URL4 expression is also load-bearing --
``EnsembleInterpreter`` calls ``split_intent`` on the top-level
expression and would otherwise peel the ``!{...}`` off as an ensemble
intent (SF-159 finding; same pattern as
``python_runner/tests/test_e2e.py``).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs.models import EvalQuestion, EvalRun
from screamingface.plugins.python_runner.plugin import PythonRunnerSettings

# Single-key payload: script echoes ``q`` as both predicted and raw_output,
# and reports ``correct: true`` unconditionally. This is enough to exercise
# the persistence chain end-to-end.
CHECK_CORRECT_SCRIPT = """\
import json, sys
data = json.load(sys.stdin)
q = data.get("q", "")
print(json.dumps({
    "question": q,
    "expected": q,
    "predicted": q,
    "correct": True,
    "raw_output": q,
}))
"""


@pytest.fixture
def temp_state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "state.db"
    monkeypatch.setenv("SF_STATE__PATH", str(db))
    return db


@pytest.fixture
async def app_full(temp_state_path: Path):
    config = AppConfig(
        plugins=["state", "url4-executor", "python-runner", "eval-runs"],
        plugin_config={},
    )
    app = create_app(config)
    async with app.router.lifespan_context(app):
        plugin = app.state.plugins.active_plugins["python-runner"]
        plugin.settings = PythonRunnerSettings(scripts={"check_correct": CHECK_CORRECT_SCRIPT})
        yield app


@pytest.mark.asyncio
async def test_e2e_one_question_persists(app_full) -> None:
    run_id = str(uuid4())
    # Single-key payload to dodge the URL4 intent-text no-comma rule.
    url4 = '(/python(/data/code/check_correct.py)!{"q":"2+2"})'

    transport = httpx.ASGITransport(app=app_full)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        resp = await c.get(
            "/ensemble",
            params={"q": url4},
            headers={"X-SF-Run-Id": run_id, "X-SF-Run-Spec": "hle-claude-single"},
        )
    assert resp.status_code == 200, resp.text

    run = await EvalRun.get(id=UUID(run_id))
    assert run.status == "done"
    assert run.spec_name == "hle-claude-single"
    assert run.total_questions == 1
    assert run.correct_questions == 1
    assert run.accuracy == pytest.approx(1.0)

    questions = await EvalQuestion.filter(run_id=UUID(run_id))
    assert len(questions) == 1
    # ``question``/``expected`` come from the intent JSON, which only has a
    # single ``q`` key -- so the plugin records them as empty strings.
    # ``predicted``/``correct``/``raw_output`` come from script stdout and
    # carry the real values.
    assert questions[0].question == ""
    assert questions[0].expected == ""
    assert questions[0].predicted == "2+2"
    assert questions[0].correct is True
    assert questions[0].raw_output == "2+2"


@pytest.mark.asyncio
async def test_e2e_without_headers_persists_nothing(app_full) -> None:
    url4 = '(/python(/data/code/check_correct.py)!{"q":"x"})'

    transport = httpx.ASGITransport(app=app_full)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=60) as c:
        resp = await c.get("/ensemble", params={"q": url4})
    assert resp.status_code == 200

    assert await EvalRun.all().count() == 0
    assert await EvalQuestion.all().count() == 0
