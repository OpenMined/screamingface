"""Stub layer for the eval demo: patches the TARGET SDK API onto today's `screamingface`.

Importing this module (after `import screamingface as sf`) makes the whole notebook run
with no API keys by filling the six SDK gaps with stubs that execute:

- real where we have the real thing — grading calls the actual validated grader in
  ``benchmarking/graders/rubric.py`` (the one behind the $233.78 DRACO run of record);
- simulated where a real run would spend money — panel/synthesizer/judge LLM calls are
  deterministic stand-ins, each announcing itself with a ``[stub · ...]`` line that says
  what a real run would do and where the production code lives:
  https://github.com/OpenMined/screamingface-benchmarks

Patched surface (only where the SDK lacks it, so stubs step aside as gaps land):
  sf.benchmark(source, record_to_row=)  -> Benchmark of Rows        (SDK gap 1)
  sf.Fusion(...)                        -> real Fusion, falling back to a preview-only
                                           StubFusion on unknown catalog models (gap 6)
  fusion.evaluate(Benchmark, seed=)     -> stub engine run, answers kept on run.rows (gaps 2-3)
  run.grade([judge]) / sf.RubricJudge / sf.MultipleChoice           (gap 4)
  run.cost                              -> answer vs judge call counts (gap 5)

Extension seams — how ANYONE plugs in a new benchmark
-----------------------------------------------------
The pipeline is `load -> run -> grade -> aggregate`, and each stage resolves its
strategy from a named registry, exactly the way inspect_ai registers `@task`,
`@solver`, `@scorer` and maps datasets with `record_to_sample`
(see .dk/refs/libs/inspect_ai — src/inspect_ai/_util/registry.py):

  @sf.loader("my-bench")        # LOAD:  source name/suffix -> Benchmark of Rows
  @sf.runner("my-task-type")    # RUN:   how a worker attempts one row of this type
  @sf.grader("my-grader")       # GRADE: how an answer becomes a score in [0, 1]
  @sf.aggregator("my-agg")      # AGG:   how per-row scores roll into the headline

A new benchmark = registering ONE new strategy at ONE seam (usually just a loader —
if its task_type and grading mode already exist, everything else is reused).
`sf.registry()` prints what's currently pluggable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import screamingface as sf
from loguru import logger
from screamingface.fusion import Fusion as _RealFusion

sys.path.insert(0, str(Path(__file__).parent))
from benchmarking.graders.rubric import grade_against_rubric_async  # noqa: E402 — the REAL validated grader

BENCH_REPO = "https://github.com/OpenMined/screamingface-benchmarks"


def _gh(path: str) -> str:
    """Deep link into the production benchmarks repo (paths verified on main)."""
    return f"{BENCH_REPO}/blob/main/{path}"

# Same `[stub · stage]` tag the notebooks reference, just colorized. stdout (not loguru's
# default stderr) so Jupyter doesn't paint every line on the red error background.
logger.remove()
logger.add(
    sys.stdout,
    colorize=True,
    format="<dim>[</dim><magenta>stub</magenta><dim> · </dim><cyan>{extra[stage]}</cyan><dim>]</dim> {message}",
)


def _log(stage: str, msg: str) -> None:
    logger.bind(stage=stage).info(msg)


def _h(text: str) -> int:
    """Deterministic hash → int (stable across runs, no randomness)."""
    return int(hashlib.md5(text.encode()).hexdigest(), 16)


def _await(coro):
    """Run a coroutine from sync code, safe inside Jupyter's event loop."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


# --- registries: the four extension seams (inspect_ai's registry pattern) ---------------

_REGISTRY: dict[str, dict[str, object]] = {"loader": {}, "runner": {}, "grader": {}, "aggregator": {}}


def _register(kind: str, name: str):
    def decorate(obj):
        _REGISTRY[kind][name] = obj
        return obj

    return decorate


def loader(name: str):
    """Register a LOAD strategy: fn(source, **kw) -> Benchmark. Name or file suffix."""
    return _register("loader", name)


def runner(task_type: str):
    """Register a RUN strategy for a task_type: fn(fusion, row, seed) -> (panel, answer)."""
    return _register("runner", task_type)


def grader(name: str):
    """Register a GRADE strategy: object with grade_row(row, answer) -> float in [0, 1]."""
    return _register("grader", name)


def aggregator(name: str):
    """Register an AGGREGATE strategy: fn(per_row_scores) -> float."""
    return _register("aggregator", name)


def registry() -> None:
    """Print every pluggable strategy — the four seams, live."""
    for kind, entries in _REGISTRY.items():
        print(f"{kind:<11} {', '.join(sorted(entries)) or '(empty)'}")


# --- LOAD seam (SDK gap 1) ------------------------------------------------------------


@dataclass(frozen=True)
class Rubric:
    raw: dict

    def preview(self) -> None:
        total = sum(len(s["criteria"]) for s in self.raw["sections"])
        print(f"{len(self.raw['sections'])} sections · {total} weighted criteria")
        for s in self.raw["sections"]:
            print(f"  {s['title']:<34} {len(s['criteria']):>3} criteria")


@dataclass(frozen=True)
class Row:
    id: str
    source: str
    task_type: str
    question: str
    answer: str
    metadata: dict = field(default_factory=dict)

    @property
    def rubric(self) -> Rubric:
        return Rubric(json.loads(self.answer))


@dataclass
class Benchmark:
    name: str
    task_type: str
    rows: list

    def __getitem__(self, i):
        return self.rows[i]

    def __len__(self):
        return len(self.rows)

    def __repr__(self):
        grade = (
            "weighted rubric (LLM judge)"
            if self.task_type == "abstractive"
            else "answer key (pure code)"
        )
        return f"Benchmark · {self.name} ({len(self.rows)} rows) · {self.task_type} · graded by {grade}"


def default_record_to_row(record: dict) -> Row:
    """Map one arena-schema record -> Row (inspect_ai's `record_to_sample` pattern).

    Pass your own `record_to_row=` to sf.benchmark() for any foreign schema.
    """
    return Row(
        record["id"],
        record["source"],
        record["task_type"],
        record["question"],
        record["answer"],
        record.get("metadata") or {},
    )


@loader(".jsonl")
def load_jsonl(source, record_to_row=None, **_):
    record_to_row = record_to_row or default_record_to_row
    rows = [record_to_row(json.loads(line)) for line in Path(source).read_text().splitlines()]
    _log("load", f"{source} → {len(rows)} rows · prod ingestion: {_gh('data_ingestion/run_ingestion.py')}")
    return Benchmark(rows[0].source, rows[0].task_type, rows)


# Tiny SAMPLE rows in each benchmark's shape (synthetic, demo only —
# real datasets + ingestion live in the benchmarks arena).
@loader("medxpertqa-sample")
def load_medxpert_sample(source, **_):
    rows = [
        Row(
            "mx-demo-1",
            "medxpertqa-sample",
            "mcq",
            "Which electrolyte abnormality is most associated with a prolonged QT interval?\n"
            "A. Hypokalemia\nB. Hypercalcemia\nC. Hypernatremia\nD. Hyperkalemia",
            "A",
        ),
        Row(
            "mx-demo-2",
            "medxpertqa-sample",
            "mcq",
            "First-line treatment for anaphylaxis?\n"
            "A. IV corticosteroids\nB. IM epinephrine\nC. Oral antihistamines\nD. Nebulized albuterol",
            "B",
        ),
    ]
    _log("load", f"'{source}' → {len(rows)} synthetic sample rows (shape-faithful) · "
                 f"real loader: {_gh('data_ingestion/hf_loader.py')} · "
                 f"real grader: {_gh('benchmarking/graders/mcq_exact.py')}")
    return Benchmark(source, "mcq", rows)


@loader("healthbench-sample")
def load_healthbench_sample(source, **_):
    rows = [
        Row(
            "hb-demo-1",
            "healthbench-sample",
            "abstractive",
            "Patient: I've had a fever of 39°C for three days and now my neck feels stiff. "
            "Should I just wait it out at home?",
            json.dumps(
                {
                    "id": "hb-demo-1-rubric",
                    "sections": [
                        {
                            "id": "clinical",
                            "title": "Clinical Accuracy",
                            "criteria": [
                                {"id": "urgent-eval", "weight": 10, "requirement": "Advises urgent medical evaluation for possible meningitis"},
                                {"id": "red-flags", "weight": 7, "requirement": "Identifies fever + stiff neck as a red-flag combination"},
                                {"id": "no-false-reassurance", "weight": 6, "requirement": "Avoids reassuring the patient it is safe to wait at home"},
                            ],
                        },
                        {
                            "id": "communication",
                            "title": "Communication Quality",
                            "criteria": [
                                {"id": "plain-language", "weight": 3, "requirement": "Explains the reasoning in plain language"},
                                {"id": "empathy", "weight": 2, "requirement": "Acknowledges the patient's concern"},
                            ],
                        },
                    ],
                }
            ),
        ),
    ]
    _log("load", f"'{source}' → 1 synthetic sample row (shape-faithful) · "
                 f"real grader: {_gh('benchmarking/graders/healthbench_rubric.py')} · "
                 f"real prompts: {_gh('benchmarking/prompts/healthbench.py')}")
    return Benchmark(source, "abstractive", rows)


def benchmark(source, **kwargs):
    """Target API: sf.benchmark(source, record_to_row=, ...) — SDK gap 1.

    Resolution order (all pluggable via @sf.loader):
    exact registered name → registered file suffix → error listing what's available.
    """
    if str(source) in _REGISTRY["loader"]:
        return _REGISTRY["loader"][str(source)](source, **kwargs)
    for suffix, fn in _REGISTRY["loader"].items():
        if suffix.startswith(".") and str(source).endswith(suffix):
            return fn(source, **kwargs)
    known = ", ".join(sorted(_REGISTRY["loader"]))
    raise ValueError(f"no loader for {source!r} — register one with @sf.loader(...); known: {known}")


# --- COMPOSE (SDK gap 6: DRACO lineup not in the catalog yet) ---------------------------


@dataclass(frozen=True)
class StubFusion:
    name: str
    models: tuple
    reducer: object

    @property
    def url4(self) -> str:
        calls = ", ".join(
            f"panel_{i}=/{m}($question)!'Answer the question'" for i, m in enumerate(self.models, 1)
        )
        synth = (
            f", fusion_answer=/{self.reducer.model}('Question + labeled panel drafts')"
            f"!'Synthesize the panel answers into one final answer'"
            if isinstance(self.reducer, sf.Synthesize)
            else ""
        )
        return f"({calls}{synth}, {{schema: 'screamingface.fusion-result.v1', …}})"

    def evaluate(self, bench, seed=0):
        return _evaluate(self, bench, seed)


def Fusion(name, models, reducer=None):
    """Target API: sf.Fusion — real SDK class, preview-only fallback on gap 6."""
    try:
        return _RealFusion(name, models=models, reducer=reducer)
    except ValueError as exc:
        _log("compose", f"{exc} → SDK gap 6 (catalog + engine routes); building a preview-only recipe instead")
        return StubFusion(name, tuple(models), reducer)


# --- RUN seam (SDK gaps 2–3) ------------------------------------------------------------


@dataclass(frozen=True)
class RowResult:
    row_id: str
    panel_answers: dict
    answer: str


@dataclass
class Run:
    fusion: object
    bench: Benchmark
    rows: list
    answer_calls: int
    judge_calls: int = 0

    def __repr__(self):
        return (
            f"Run · {self.fusion.name} · {self.bench.name} · {len(self.rows)} rows · "
            f"answer_calls={self.answer_calls}"
        )

    def grade(self, grader=None):
        return _grade(self, grader)

    @property
    def cost(self):
        return {
            "answer_calls": self.answer_calls,
            "judge_calls": self.judge_calls,
            "usd": None,
            "note": "stub run — a real run reports billed vs cached USD here",
        }


@runner("mcq")
def run_mcq_row(fus, row, seed):
    h = _h(f"{seed}:{row.id}")
    answer = row.answer if h % 4 else "ABCD"[(h >> 2) % 4]  # ~75%-correct stub panel
    return {m: answer for m in fus.models}, answer


@runner("abstractive")
def run_abstractive_row(fus, row, seed):
    answer = (
        f"(stub fused research report for {row.id} — a real run sends the "
        f"url4 recipe to the engine with web tools on)"
    )
    return {m: f"(stub draft from {m})" for m in fus.models}, answer


def _evaluate(fus, bench, seed=0):
    """Target API: fusion.evaluate(bench, seed=) — SDK gaps 2–3.

    The per-row strategy comes from the runner registry (keyed by task_type), so a new
    way of working — multi-turn, agentic, a 2027 invention — is @sf.runner("new-type"),
    never a pipeline reshape. A real run compiles one url4 expression per row and sends
    it to the engine; here the 'engine' is a deterministic stand-in (no keys, no cost).
    """
    run_row = _REGISTRY["runner"].get(bench.task_type)
    if run_row is None:
        known = ", ".join(sorted(_REGISTRY["runner"]))
        raise ValueError(
            f"no runner for task_type {bench.task_type!r} — register one with "
            f"@sf.runner({bench.task_type!r}); known: {known}"
        )
    rows = []
    for row in bench.rows:
        panel, answer = run_row(fus, row, seed)
        rows.append(RowResult(row.id, panel, answer))
    synth = 1 if isinstance(getattr(fus, "reducer", None), sf.Synthesize) else 0
    calls = len(bench.rows) * (len(fus.models) + synth)
    _log(
        "run",
        f"{len(bench.rows)} rows × ({len(fus.models)} panel + {synth} synth) → "
        f"{calls} engine calls in a real run · every answer kept on run.rows",
    )
    _log("run", f"recipe: {fus.url4[:110]}…")
    return Run(fus, bench, rows, calls)


_real_evaluate = _RealFusion.evaluate


def _evaluate_dispatch(self, benchmark, first=20, seed=0, **kwargs):
    """Patched sf.Fusion.evaluate: Benchmark object → stub run; string → today's SDK path."""
    if isinstance(benchmark, Benchmark):
        return _evaluate(self, benchmark, seed)
    return _real_evaluate(self, benchmark, first=first, seed=seed, **kwargs)


# --- GRADE seam (SDK gaps 4–5) ------------------------------------------------------------


@grader("multiple-choice")
@dataclass
class MultipleChoice:
    """Answer-key grader: pure code, free. Prod: mcq_exact grading in the arena."""

    def grade_row(self, row, answer):
        return 1.0 if answer.strip().upper().startswith(row.answer.strip().upper()) else 0.0


@grader("rubric-judge")
@dataclass
class RubricJudge:
    """Target API: sf.RubricJudge(...) — wraps the REAL validated grader.

    Only the judge LLM call itself is stubbed (deterministic verdicts).
    """

    model: str
    temperature: float = 0.2
    reasoning: str = "low"
    mode: str = "chunked"  # "official" = paper-faithful, ~criteria×runs calls/row
    runs: int = 1
    calls: int = 0

    async def _judge(self, system, user):  # ← in prod: ONE pinned url4 judge call
        self.calls += 1
        ids = re.findall(r'"id"\s*:\s*"([^"]+)"', user)
        verdicts = [{"id": i, "met": _h(i) % 10 < 7} for i in ids]  # ~70% met, deterministic
        return json.dumps({"verdicts": verdicts})


# Default grader per task_type — what run.grade() resolves with no argument.
_DEFAULT_GRADER = {"mcq": MultipleChoice}


@aggregator("mean")
def agg_mean(per_row):
    return sum(per_row) / len(per_row)


@dataclass
class Scores:
    benchmark: str
    grader: str
    per_row: list
    details: dict = field(default_factory=dict)

    @property
    def mean(self):
        return _REGISTRY["aggregator"]["mean"](self.per_row)

    @property
    def stderr(self):
        n = len(self.per_row)
        var = sum((x - self.mean) ** 2 for x in self.per_row) / max(n - 1, 1)
        return math.sqrt(var / n)

    def aggregate(self, name="mean"):
        """AGG seam: resolve any registered aggregator (Elo, pass@k, … later)."""
        return _REGISTRY["aggregator"][name](self.per_row)

    def __repr__(self):
        extra = "".join(f" · {k} {v:.2f}" for k, v in self.details.items())
        return (
            f"Scores · {self.benchmark} · {self.grader} · "
            f"{self.mean:.3f} ± {self.stderr:.3f} (n={len(self.per_row)}){extra}"
        )


def _grade(run, grader_obj):
    rows_by_id = {r.id: r for r in run.bench.rows}
    if grader_obj is None:
        default = _DEFAULT_GRADER.get(run.bench.task_type)
        if default is None:
            raise ValueError(
                f"no default grader for task_type {run.bench.task_type!r} — "
                f"pass one: run.grade(sf.RubricJudge(...)) or any @sf.grader"
            )
        grader_obj = default()
    if isinstance(grader_obj, RubricJudge):
        return _grade_rubric(run, rows_by_id, grader_obj)
    if hasattr(grader_obj, "grade_row"):  # any registered/custom grader: row+answer -> [0,1]
        per_row = [grader_obj.grade_row(rows_by_id[rr.row_id], rr.answer) for rr in run.rows]
        prod = f" · prod: {_gh('benchmarking/graders/mcq_exact.py')}" if isinstance(grader_obj, MultipleChoice) else ""
        _log("grade", f"{type(grader_obj).__name__} — pure python, 0 judge calls, $0{prod}")
        return Scores(run.bench.name, type(grader_obj).__name__, per_row)
    raise TypeError(f"grader {grader_obj!r} needs grade_row(row, answer) or be a RubricJudge")


def _grade_rubric(run, rows_by_id, judge):
    """RubricJudge → the REAL validated grader, criterion by criterion."""
    per_row, pass_rates, coverages = [], [], []
    for rr in run.rows:
        row = rows_by_id[rr.row_id]
        result = _await(
            grade_against_rubric_async(
                question=row.question,
                model_answer=rr.answer,
                rubric_raw=row.answer,
                judge_fn_async=judge._judge,
                judge_runs=judge.runs,
            )
        )
        per_row.append(result["normalized_score"])
        pass_rates.append(result["pass_rate"])
        coverages.append(result["verdict_coverage"])
    run.judge_calls += judge.calls
    _log(
        "grade",
        f"REAL grader (benchmarking/graders/rubric.py — the one behind the "
        f"$233.78 run of record) · {judge.calls} judge calls, stubbed "
        f"deterministically; in prod each is one pinned call to {judge.model}",
    )
    _log("grade", f"prod grader: {_gh('benchmarking/graders/rubric.py')} · "
                  f"judge prompts: {_gh('benchmarking/prompts/rubric.py')}")
    return Scores(
        run.bench.name,
        f"RubricJudge({judge.mode}, runs={judge.runs})",
        per_row,
        {
            "pass_rate": sum(pass_rates) / len(pass_rates),
            "verdict_coverage": sum(coverages) / len(coverages),
        },
    )


# --- install: patch sf in place, only where the surface is missing --------------------------


def install() -> None:
    if getattr(sf, "_stubs_installed", False):
        return
    patched = []
    if not hasattr(sf, "benchmark"):
        sf.benchmark = benchmark
        sf.Row, sf.Benchmark = Row, Benchmark
        patched.append("sf.benchmark")
    sf.Fusion = Fusion  # real class first, preview fallback on unknown models (gap 6)
    _RealFusion.evaluate = _evaluate_dispatch  # accept Benchmark objects (gaps 2–3)
    patched += ["sf.Fusion (catalog fallback)", "fusion.evaluate(Benchmark)"]
    if not hasattr(sf, "RubricJudge"):
        sf.RubricJudge = RubricJudge
        sf.MultipleChoice = MultipleChoice
        patched += ["sf.RubricJudge", "sf.MultipleChoice"]
    # the four extension seams (inspect_ai-style named registries)
    sf.loader, sf.runner, sf.grader, sf.aggregator = loader, runner, grader, aggregator
    sf.registry = registry
    sf._stubs_installed = True
    print(
        f"[sf_stubs] screamingface {sf.__version__} + target API patched: "
        + ", ".join(patched)
        + " · extension seams: @sf.loader / @sf.runner / @sf.grader / @sf.aggregator"
    )


install()
