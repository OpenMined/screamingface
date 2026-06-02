"""E2E: the shipped ``ScoredLiveTruth`` URL4 scored-query pipeline runs end to
end to a REAL accuracy result (SF-34 / M7.2).

What this proves, in one in-process run of the actual shipped spec:

    dataset (mocked, inline) ── per row ──▶
        consensus = /claude($item.question)        (mocked: returns the answer)
        /python(/data/code/check_correct.py)!{…}   (REAL script, subprocess)
    ── collect 3 verdicts into a JSON array ──▶
        /python(/data/code/calculate_accuracy.py)   (REAL script, subprocess)
    ── accuracy report JSON ──▶ asserted here

Wiring choice (the interpreter-level approach from the task brief, approach 2):

* ``create_app`` activates the REAL ``python-runner`` plugin, so its
  ``/data/code/{name}.py`` route is mounted and ``handle_backend_call`` runs
  the scripts through ``run_script_main`` in a sandboxed subprocess. The two
  scripts are the byte-for-byte committed ``eval_scripts/check_correct.py`` and
  ``eval_scripts/calculate_accuracy.py`` — injected into the plugin's
  ``scripts`` settings exactly as ``sf.json`` ships them. They are NOT mocked.

* ``/claude`` is a tiny fake plugin dropped into the active-plugin registry; it
  answers each row's question from a lookup table. The reducer never routes to
  it (the outer ``!`` reducer is ``/python(...calculate_accuracy.py)``), so a
  fake ``/claude`` is sufficient.

* The dataset URL fetch is the only network touch, and it is monkeypatched:
  ``url4.resolve_str`` returns an inline 3-row JSONL when called with the
  livetruth URL and delegates every other context (notably the per-row
  ``/data/code/*.py`` script fetches) to the real resolver. Same selective
  monkeypatch pattern as ``test_collection_concurrency.py`` /
  ``test_scored_pipeline.py``.

* The EXPRESSION is read straight from ``sf.json``
  (``plugin_config.url4-specs.specs.ScoredLiveTruth.expression``) so the test
  exercises the SHIPPED spec, not a hand-written copy.

Dataset is designed so ``/claude`` returns a WRONG answer for exactly one of
three rows → a deterministic, non-trivial 66.67% accuracy (n=3, n_correct=2),
and that number is computed by the REAL ``calculate_accuracy.py``, never a mock.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.eval_runs._hook_payloads import HOOK_QUESTION_CHECKED
from screamingface.plugins.python_runner.plugin import PythonRunnerSettings
from screamingface.plugins.url4_executor.ensemble import EnsembleInterpreter
from screamingface.plugins.url4_executor.scope import Env

pytestmark = pytest.mark.timeout(60)


# ---------------------------------------------------------------------------
# Repo-relative helpers: the SHIPPED expression and the REAL eval scripts.
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "eval_scripts").is_dir() and (parent / "apps").is_dir():
            return parent
    raise RuntimeError("repo root (with eval_scripts/ + apps/) not found above test file")


def _server_root() -> Path:
    # apps/server — where sf.json lives.
    for parent in Path(__file__).resolve().parents:
        if (parent / "sf.json").is_file():
            return parent
    raise RuntimeError("apps/server (with sf.json) not found above test file")


# The three real, committed scripts and the shipped spec — loaded, not faked.
_ROOT = _repo_root()
CHECK_CORRECT_SRC = (_ROOT / "eval_scripts" / "check_correct.py").read_text()
CALCULATE_ACCURACY_SRC = (_ROOT / "eval_scripts" / "calculate_accuracy.py").read_text()

_SF_JSON = json.loads((_server_root() / "sf.json").read_text())
SCORED_EXPR: str = _SF_JSON["plugin_config"]["url4-specs"]["specs"]["ScoredLiveTruth"]["expression"]

# The collection-source URL embedded in the shipped expression. We monkeypatch
# the dataset fetch for exactly this URL.
LIVETRUTH_URL = "https://screamingface.ai/livetruth-latest.eval.jsonl"

# Inline dataset — 3 rows, fields `question` + `expected_answer` (what the
# expression's $item.question / $item.expected_answer reference). JSONL.
DATASET_ROWS = [
    {"question": "What is the capital of France?", "expected_answer": "Paris"},
    {"question": "What is the capital of the United Kingdom?", "expected_answer": "London"},
    {"question": "What is the capital of Japan?", "expected_answer": "Tokyo"},
]
DATASET_JSONL = "\n".join(json.dumps(r) for r in DATASET_ROWS)

# /claude answers: correct for France + UK, WRONG for Japan → 2/3 correct.
CLAUDE_ANSWERS = {
    "What is the capital of France?": "Paris",
    "What is the capital of the United Kingdom?": "London",
    "What is the capital of Japan?": "Kyoto",  # deliberately wrong (truth: Tokyo)
}


class _FakeClaudePlugin:
    """Minimal ``/claude`` backend: maps a row's question to its answer.

    The per-row body resolves ``/claude($item.question)`` with the substituted
    question as the dispatched ``sources`` (packed context), so we key off
    ``sources``. Falls back to substring matching for robustness against any
    surrounding whitespace/markup the resolver may add.
    """

    name = "fake-claude"
    backend_call_paths = ["/claude"]

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del intent, app, env
        self.calls.append(sources)
        for question, answer in CLAUDE_ANSWERS.items():
            if question in sources or sources.strip() == question:
                return answer
        raise AssertionError(f"unexpected /claude question in sources: {sources!r}")


def _fake_resolve_returning_dataset():
    """resolve_str stub: return the inline dataset for the livetruth URL,
    delegate everything else (esp. /data/code/*.py fetches) to the real impl."""
    from screamingface.plugins.url4_executor import url4_resolve as _url4_resolve

    _real_resolve_str = _url4_resolve.resolve_str

    async def _fake(context, app, env=None):
        if context == LIVETRUTH_URL:
            return DATASET_JSONL
        return await _real_resolve_str(context, app, env)

    return _fake


@pytest.fixture
def scored_app():
    """Real app: url4-executor + python-runner, with the REAL eval scripts
    injected and a fake /claude registered."""
    app = create_app(AppConfig(plugins=["url4-executor", "python-runner"], plugin_config={}))

    # Inject the REAL scripts under the names the shipped expression references.
    py = app.state.plugins.active_plugins["python-runner"]
    py.settings = PythonRunnerSettings(
        scripts={
            "check_correct": CHECK_CORRECT_SRC,
            "calculate_accuracy": CALCULATE_ACCURACY_SRC,
        }
    )

    # Drop a fake /claude into the active registry (no live model). The
    # registry's ``active_plugins`` property returns a *copy*, so inject into
    # the backing ``_active`` dict that backend dispatch actually walks.
    claude = _FakeClaudePlugin()
    app.state.plugins._active["fake-claude"] = claude  # noqa: SLF001
    app.state.claude = claude  # convenience handle for assertions
    return app


@pytest.mark.asyncio
async def test_scored_livetruth_runs_to_real_accuracy(scored_app, monkeypatch):
    monkeypatch.setattr(
        "screamingface.plugins.url4_executor.url4.resolve_str",
        _fake_resolve_returning_dataset(),
    )

    # --- eval-runs bonus: spy on per-row question.checked hook firing. ---
    fired: list[dict] = []
    scored_app.state.hooks.register(
        HOOK_QUESTION_CHECKED,
        lambda **payload: fired.append(payload),
        plugin_name="spy",
    )
    # __run_id__ in env is what arms the hook inside python_runner.plugin.
    env = Env.root().child(__run_id__="m7-2-test-run", __run_spec__="ScoredLiveTruth")

    interp = EnsembleInterpreter(app=scored_app)
    result = await interp.evaluate(SCORED_EXPR, env=env)

    # The final result is the JSON produced by the REAL calculate_accuracy.py.
    report = json.loads(result)

    # 3 rows graded; France + UK correct, Japan wrong → 2/3 = 66.67%.
    assert report["n"] == 3, report
    assert report["n_correct"] == 2, report
    assert report["accuracy_pct"] == 66.67, report
    # The `summary` field is calculate_accuracy.py's own format — proof the
    # number came from the real script, not a mock.
    assert report["summary"].startswith("Accuracy: 66.67% +/- "), report
    assert "| n = 3" in report["summary"], report
    # No errors expected: every row produced a clean boolean verdict.
    assert "n_errors" not in report, report

    # /claude was asked all three questions (one per row).
    assert len(scored_app.state.claude.calls) == 3

    # --- eval-runs bonus assertions: one question.checked per graded row. ---
    assert len(fired) == 3, fired
    assert all(ev["run_id"] == "m7-2-test-run" for ev in fired)
    correct_flags = sorted(ev["correct"] for ev in fired)
    assert correct_flags == [False, True, True], fired
    # The wrong row is Japan; its predicted came from the fake claude (Kyoto).
    japan = next(ev for ev in fired if ev["correct"] is False)
    assert japan["predicted"] == "Kyoto", japan
