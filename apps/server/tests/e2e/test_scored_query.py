"""E2E: the shipped ``ScoredLiveTruth`` URL4 scored-query pipeline runs end to
end to a REAL accuracy result (SF-34 / M4 — 3-way weighted ensemble).

What this proves, in one in-process run of the actual shipped spec:

    dataset (mocked, inline) ── per row ──▶
        consensus = (claude:0.40:/claude($item.question)!'…',
                     codex:0.30:/codex($item.question)!'…',
                     gemini:0.30:/gemini($item.question)!'…')!'Combine…'
            (3 mocked fan-out backends + 1 reduce via the processor)
        /python(/data/code/check_correct.py)!{…}   (REAL script, subprocess)
    ── collect 3 verdicts into a JSON array ──▶
        /python(/data/code/calculate_accuracy.py)   (REAL script, subprocess)
    ── accuracy report JSON ──▶ asserted here

Wiring choice (the interpreter-level approach from the task brief, approach 1 —
dedicated reducer backend):

* ``create_app`` activates the REAL ``python-runner`` plugin, so its
  ``/data/code/{name}.py`` route is mounted and ``handle_backend_call`` runs
  the scripts through ``run_script_main`` in a sandboxed subprocess. The two
  scripts are the byte-for-byte committed ``eval_scripts/check_correct.py`` and
  ``eval_scripts/calculate_accuracy.py`` — injected into the plugin's
  ``scripts`` settings exactly as ``sf.json`` ships them. They are NOT mocked.

* ``/claude``, ``/codex`` and ``/gemini`` are three tiny fake plugins dropped
  into the active-plugin registry; each answers a row's question from its own
  per-model lookup table (keyed off the dispatched ``sources``).

* The consensus reduce dispatches to the interpreter's PROCESSOR. We register a
  dedicated ``/reducer`` fake and build ``EnsembleInterpreter(processor=
  "/reducer")``. The reducer receives ``build_reducer_input``'s weighted-label
  text as its intent (e.g. ``claude (weight=40):\\nLondon``), parses the three
  candidates + weights out of it, and returns the WEIGHTED-MAJORITY answer.
  That returned value is the REDUCED consensus — distinct, by design, from any
  single fan-out model on the rows where the models disagree.

* The dataset URL fetch is the only network touch, and it is monkeypatched:
  ``url4.resolve_str`` returns an inline 3-row JSONL when called with the
  livetruth URL and delegates every other context (notably the per-row
  ``/data/code/*.py`` script fetches) to the real resolver. Same selective
  monkeypatch pattern as ``test_collection_concurrency.py`` /
  ``test_scored_pipeline.py``.

* The EXPRESSION is read straight from ``sf.json``
  (``plugin_config.url4-specs.specs.ScoredLiveTruth.expression``) so the test
  exercises the SHIPPED 3-way spec, not a hand-written copy.

Dataset is designed so the REDUCED consensus is correct for France + UK and
WRONG for Japan → a deterministic, non-trivial 66.67% accuracy (n=3,
n_correct=2), computed by the REAL ``calculate_accuracy.py``, never a mock.
"""

from __future__ import annotations

import json
import re
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


# The two real, committed scripts and the shipped spec — loaded, not faked.
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

# Per-model fan-out answers. Weights from the shipped spec: claude=0.40,
# codex=0.30, gemini=0.30. The reducer takes the weighted MAJORITY, so:
#
#   France : Paris / Paris / Paris   → Paris   (== expected Paris)   correct
#   UK     : London / London / Londres → London (claude+codex 0.70 win;
#                                         != gemini → proves reduction) correct
#   Japan  : Kyoto / Kyoto / Tokyo   → Kyoto   (claude+codex 0.70 win;
#                                         != expected Tokyo, != gemini)  WRONG
#
# So consensus is the REDUCED value (never a raw single model on the rows where
# the models disagree), and accuracy is a deterministic 2/3 = 66.67%.
MODEL_ANSWERS: dict[str, dict[str, str]] = {
    "/claude": {
        "What is the capital of France?": "Paris",
        "What is the capital of the United Kingdom?": "London",
        "What is the capital of Japan?": "Kyoto",
    },
    "/codex": {
        "What is the capital of France?": "Paris",
        "What is the capital of the United Kingdom?": "London",
        "What is the capital of Japan?": "Kyoto",
    },
    "/gemini": {
        "What is the capital of France?": "Paris",
        "What is the capital of the United Kingdom?": "Londres",  # disagrees → reduced away
        "What is the capital of Japan?": "Tokyo",  # disagrees → reduced away
    },
}

# The reduced consensus the weighted-majority reducer must produce per row.
EXPECTED_CONSENSUS = {
    "What is the capital of France?": "Paris",
    "What is the capital of the United Kingdom?": "London",
    "What is the capital of Japan?": "Kyoto",
}


class _FakeFanoutPlugin:
    """A single fan-out backend (``/claude`` | ``/codex`` | ``/gemini``).

    The per-row body resolves ``/model($item.question)`` with the substituted
    question as the dispatched ``sources`` (packed context), so we key off
    ``sources`` (with a substring fallback for robustness).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.name = f"fake-{path.lstrip('/')}"
        self.backend_call_paths = [path]
        self._answers = MODEL_ANSWERS[path]
        self.calls: list[str] = []

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del intent, app, env
        self.calls.append(sources)
        for question, answer in self._answers.items():
            if question in sources or sources.strip() == question:
                return answer
        raise AssertionError(f"unexpected {self.path} question in sources: {sources!r}")


# Parses one ``name (weight=NN):`` block out of build_reducer_input's text.
_BLOCK_RE = re.compile(
    r"^(?P<name>[A-Za-z_][\w]*) \(weight=(?P<weight>\d+(?:\.\d+)?)\):\n(?P<text>.*)$",
    re.MULTILINE,
)


class _FakeReducerPlugin:
    """The interpreter's PROCESSOR — the consensus reduce backend ``/reducer``.

    Receives ``build_reducer_input``'s formatted text as its INTENT (the
    fan-out call's question arrives as ``sources``; the reducer call's
    weighted-label payload arrives as ``intent`` with empty ``sources``). It
    parses the per-model candidate answers + weights and returns the
    weighted-MAJORITY answer — the genuine REDUCED consensus.
    """

    name = "fake-reducer"
    backend_call_paths = ["/reducer"]

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def handle_backend_call(self, intent, *, sources="", app, env=None):
        del app, env
        self.calls.append(intent)
        # A reduce call carries the weighted-label payload as its intent and
        # NOTHING as sources — guard so a stray fan-out call can never land here.
        assert sources == "", f"/reducer unexpectedly got sources={sources!r}"
        assert "[Instruction]" in intent, f"/reducer got non-reducer intent: {intent!r}"

        weighted: dict[str, float] = {}
        for m in _BLOCK_RE.finditer(intent):
            answer = m.group("text").strip()
            weighted[answer] = weighted.get(answer, 0.0) + float(m.group("weight"))
        assert weighted, f"/reducer found no candidate blocks in: {intent!r}"
        # Weighted majority (ties broken deterministically by answer text).
        return max(sorted(weighted), key=lambda a: weighted[a])


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
    injected and fake /claude, /codex, /gemini + /reducer registered."""
    app = create_app(AppConfig(plugins=["url4-executor", "python-runner"], plugin_config={}))

    # Inject the REAL scripts under the names the shipped expression references.
    py = app.state.plugins.active_plugins["python-runner"]
    py.settings = PythonRunnerSettings(
        scripts={
            "check_correct": CHECK_CORRECT_SRC,
            "calculate_accuracy": CALCULATE_ACCURACY_SRC,
        }
    )

    # Drop the fakes into the active registry (no live models). The registry's
    # ``active_plugins`` property returns a *copy*, so inject into the backing
    # ``_active`` dict that backend dispatch actually walks.
    fanouts = {path: _FakeFanoutPlugin(path) for path in ("/claude", "/codex", "/gemini")}
    reducer = _FakeReducerPlugin()
    for plugin in (*fanouts.values(), reducer):
        app.state.plugins._active[plugin.name] = plugin  # noqa: SLF001
    app.state.fanouts = fanouts  # convenience handles for assertions
    app.state.reducer = reducer
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
    env = Env.root().child(__run_id__="m4-test-run", __run_spec__="ScoredLiveTruth")

    # The consensus reduce dispatches to this PROCESSOR path.
    interp = EnsembleInterpreter(app=scored_app, processor="/reducer")
    result = await interp.evaluate(SCORED_EXPR, env=env)

    # The final result is the JSON produced by the REAL calculate_accuracy.py.
    report = json.loads(result)

    # 3 rows graded; France + UK reduced-correct, Japan reduced-wrong → 2/3.
    assert report["n"] == 3, report
    assert report["n_correct"] == 2, report
    assert report["accuracy_pct"] == 66.67, report
    # The `summary` field is calculate_accuracy.py's own format — proof the
    # number came from the real script, not a mock.
    assert report["summary"].startswith("Accuracy: 66.67% +/- "), report
    assert "| n = 3" in report["summary"], report
    # No errors expected: every row produced a clean boolean verdict.
    assert "n_errors" not in report, report

    # --- per-row backend call counts: 3 fan-out + 1 reduce per row. ---
    for path, plugin in scored_app.state.fanouts.items():
        assert len(plugin.calls) == 3, (path, plugin.calls)
    assert len(scored_app.state.reducer.calls) == 3, scored_app.state.reducer.calls

    # --- eval-runs assertions: one question.checked per graded row, and the
    #     `consensus` handed to check_correct is the REDUCED value (weighted
    #     majority), NOT a raw single model's answer. ---
    assert len(fired) == 3, fired
    assert all(ev["run_id"] == "m4-test-run" for ev in fired)

    by_predicted = {ev["predicted"]: ev for ev in fired}
    # `predicted` is exactly the consensus check_correct received.
    assert set(by_predicted) == set(EXPECTED_CONSENSUS.values()), fired
    # France→Paris (correct), UK→London (correct), Japan→Kyoto (wrong).
    assert by_predicted["Paris"]["correct"] is True, by_predicted["Paris"]
    assert by_predicted["London"]["correct"] is True, by_predicted["London"]
    assert by_predicted["Kyoto"]["correct"] is False, by_predicted["Kyoto"]

    correct_flags = sorted(ev["correct"] for ev in fired)
    assert correct_flags == [False, True, True], fired

    # The reduced UK consensus is "London" — distinct from gemini's "Londres",
    # so the asserted consensus is provably the REDUCED value, not a single
    # fan-out model echoed through.
    assert "London" in by_predicted and "Londres" not in by_predicted, fired
