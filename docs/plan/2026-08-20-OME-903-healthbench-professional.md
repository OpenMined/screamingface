# OME-903 — Implementation plan: the HealthBench Professional board

Spec: `docs/spec/2026-08-20-OME-903-healthbench-professional.md` · Stack:
screamingface-engine · Branch: `OME-903-healthbench-full`

## 0. Shape of the change

Today one file, `healthbench/definition.py`, plays three roles at once: it holds the
**shared pinning** (dataset, judge, preparer, grader template), it computes **one exam's
identity** (revision + routes), and it declares **the worst30 board**. A second board
needs the first two roles and only differs in the third — so the unit splits those roles
into two new modules and leaves both board files thin:

```
pins.py    what both boards pin identically  (dataset · judge · preparer · check criterion)
exam.py    how ANY HealthBench board is built (Routes · Exam · healthbench_benchmark())
   ├── definition.py      worst30      — 157 ids, unclipped mean
   └── professional.py    professional — 525 ids, official clipped mean
```

`runtime.py`, `aggregate.py`, and `scoring.py` are already parameterized by `case_ids` /
`benchmark_id` / `benchmark_revision`; the only genuinely hardcoded thing in the grading
chain is the exam-level mean. Nothing about the judge, the prompts, the per-case math, or
the asset layout changes.

## 1. Files

### New — `src/screamingface_engine/benchmarks/healthbench/pins.py`

Benchmark-neutral pinning, moved verbatim out of `definition.py` (values unchanged, so
worst30's revision hash cannot move):

```python
DATASET = "openai/healthbench-professional"
DATASET_REVISION = "349962fd46dd02343a0d8a606491baf59154ea1a"
PREPARER_REVISION = "hf-rows-v1"
JUDGE_MODEL = "openrouter/openai/gpt-5.4"
JUDGE_PARAMS = (("web_search", "false"), ("max_tokens", "4096"))
JUDGE_RETRIES = 2
CHECK_CRITERION = "healthbench-pass.v1"
```

The existing WHY comments (no temperature pin, empty judge intent, the snapshot-pin
deviation) travel with the constants they explain.

### New — `src/screamingface_engine/benchmarks/healthbench/exam.py`

```python
@dataclass(frozen=True, slots=True)
class Routes:
    prefix: str; cases: str; tasks: str; verdict: str
    rubric_evaluation: str; case_evaluation: str; aggregate: str; check_surface: str

    @classmethod
    def for_exam(cls, benchmark_id: str, revision: str) -> Routes

@dataclass(frozen=True, slots=True)
class Exam:
    """One HealthBench identity: which cases, which final mean, at which addresses."""
    id: str
    case_ids: tuple[int, ...]
    revision: str
    routes: Routes
    mean: Callable[[Sequence[float]], float | None]

def exam_revision(*, protocol_revision: str, selection_sha: str, scoring: str) -> str
def build_exam_protocol(exam: Exam, selected_case_count: int) -> Node   # today's _build
def healthbench_benchmark(*, id, title, description, case_ids, protocol_revision,
                          scoring, mean, selection_sha) -> Benchmark
```

`healthbench_benchmark` computes the revision, derives the routes, wires
`build`/`install`/`check_surface`, and returns the `Benchmark`. `install` closes over the
`Exam` and calls `runtime.install(node, assets / "healthbench", exam)` — both boards read
the SAME baked asset root (spec §6).

`exam_revision` hashes exactly the inputs worst30 hashes today, in the same order:
`DATASET · DATASET_REVISION · protocol_revision · EVALUATION_PROTOCOL_REVISION ·
CANDIDATE_RESULT_SCHEMA · PREPARER_REVISION · selection_sha · JUDGE_MODEL ·
repr(JUDGE_PARAMS) · JUDGE_RETRIES · GRADER_TEMPLATE · scoring`. INVARIANT: worst30's
computed value must stay `39cfd96b068f7230` (its value on `main` today) — a pinned test
guards it.

### Modified — `healthbench/definition.py` (worst30, slimmed)

Keeps its public constant names so no existing import breaks: `BENCHMARK_ID`,
`CASE_COUNT`, `PROTOCOL_REVISION`, `SCORING`, `REVISION`, `ROUTE_PREFIX`, `CASES_ROUTE`,
`TASKS_ROUTE`, `VERDICT_ROUTE`, `RUBRIC_EVALUATION_ROUTE`, `CASE_EVALUATION_ROUTE`,
`AGGREGATE_ROUTE`, `CHECK_SURFACE_ROUTE` — now derived from `WORST30_EXAM.routes` instead
of f-strings. The `_build` body moves to `exam.build_exam_protocol` unchanged.

The pinning names (`DATASET`, `DATASET_REVISION`, `PREPARER_REVISION`, `JUDGE_MODEL`,
`JUDGE_PARAMS`, `JUDGE_RETRIES`, `CHECK_CRITERION`) LEAVE this module — importers move to
`pins`. No re-export shim: production code and tests both import from the new home.

### New — `healthbench/professional.py`

```python
BENCHMARK_ID = "healthbench-professional"
CASE_COUNT = 525                       # asserted against the baked file by prepare.emit
CASE_IDS = tuple(range(1, CASE_COUNT + 1))
PROTOCOL_REVISION = "professional-per-item-v1"
SCORING = "official-clipped-mean-v1"
HEALTHBENCH_PROFESSIONAL = healthbench_benchmark(..., mean=clipped_mean, ...)
```

`selection_sha` = sha256 over the case-id list (worst30 fingerprints its frozen HF ids;
this board's selection IS "every position", so the id list is the honest fingerprint).

Title "HealthBench Professional"; description names 525 cases, the physician rubric, the
AI judge, and says the score is the official clipped mean — comparable to published
HealthBench numbers.

### Modified — `healthbench/scoring.py`

Add beside `unclipped_mean`:

```python
def clipped_mean(values: Sequence[float]) -> float | None:
    """The OFFICIAL HealthBench aggregate — the reference's np.clip(mean, 0, 1)."""
```

with a worked example in the docstring (`[0.8, -0.4] → mean -0.… → 0.0`) and a WHY for
the upper bound being structurally unreachable (a per-case score is achieved/possible with
achieved ≤ possible).

### Modified — `healthbench/aggregate.py`

`aggregate(...)` gains a required keyword `mean: Callable[[Sequence[float]], float | None]`.
`_healthbench_score` becomes `_scorer(mean)` returning the closure `finalize_candidate_result`
already expects. Nothing else in the reduction changes — coverage, failure ladder, refusal
handling, and the per-case math are shared verbatim.

### Modified — `healthbench/runtime.py`

`install(node: Url4Node, root: Path, exam: Exam) -> None`. The module stops importing
worst30's constants; routes, `case_ids`, `benchmark_id`, `benchmark_revision`, and the
exam-level `mean` all come off the `Exam`. `_install_protocol_once` keeps its
already-parameterized body and its "route already present" guard, which is what lets both
boards install into one Runner world.

### Modified — `healthbench/prepare.py`

- imports `DATASET` / `DATASET_REVISION` from `pins`, and `CASE_COUNT` from `professional`.
- `emit()` gains the row-count invariant: `len(rows) != CASE_COUNT` → `PrepareError`. WHY:
  the frozen-position assertion only proves the worst30 rows did not MOVE; a dataset that
  gained rows at the end would pass it and silently bake a 526-case exam under a 525-case
  identity.
- the CLI print line names both boards.

### Modified — `benchmarks/builtins.py`

Register `HEALTHBENCH_PROFESSIONAL`. The registry sorts by id, so the catalogue becomes
`draco · healthbench-professional · healthbench-worst30 · ifeval`.

## 2. Tests (RED first)

New file `tests/unit/test_healthbench_professional.py` — the identity + protocol contract:

| Test | Invariant defended |
|---|---|
| registered under `healthbench-professional` | the board is discoverable by its own id |
| `case_count == 525` and ids are exactly `1..525` | serves the WHOLE exam, no filter |
| revision ≠ worst30's, and appears in every route | two boards, two address spaces |
| expression renders, re-parses, stays < 4000 chars | the fan-out is Engine-side (S-RT1) |
| judge call bytes identical to worst30's | judge pinning is shared, not re-derived |
| candidate invoked with `web_search=false` | grading stays retrieval-free |
| `limit=3` renders `slice=0:3`, `case_count` still 525 | smoke runs slice, they do not redefine the board |
| check surface advertised under this board's prefix, criterion `healthbench-pass.v1`, cost `paid` | capability parity with worst30 (spec §3.5) |

Appended to `tests/unit/test_healthbench_definition.py`:

- worst30's `REVISION == "39cfd96b068f7230"` — the refactor may not move the existing
  board's address (spec §6). This is the test that makes the whole refactor safe, and it
  is the tripwire that reminds the next deliberate protocol bump to re-seed the scoreboard
  entry alongside it.

Appended to `tests/unit/test_healthbench_aggregate.py`:

- a case set whose mean is NEGATIVE scores `0.0` under `clipped_mean` and stays negative
  under `unclipped_mean` — the one real behavioural difference between the boards.
- `clipped_mean` unit cases: floors at 0, passes a normal mean through, `None` on empty.

Appended to `tests/unit/test_healthbench_runtime.py`:

- installing BOTH exams into one node yields disjoint route sets and both serve their own
  case list from the same asset root — no collision, one answer key.

Appended to `tests/unit/test_healthbench_prepare.py`:

- `emit()` raises `PrepareError` when the row count is not 525 (row added / removed).

Changed (imports only, assertions untouched): `test_healthbench_definition.py`,
`test_healthbench_runtime.py`, `test_healthbench_check_surface.py` import `JUDGE_MODEL` /
`CHECK_CRITERION` from `healthbench.pins`.

Changed (must change): `test_benchmark_protocol.py::test_public_catalogue_contains_exactly_
the_three_product_benchmarks` — the catalogue is now four benchmarks. Renamed to say four
and asserts the new tuple; this is the ticket's intended effect, not a weakened test.

## 3. Order of work

1. Ledger → RED tests (all of §2) → confirm they fail for the right reason.
2. `pins.py` + `exam.py`, `definition.py` rewired — worst30 revision test must go green
   with the hash UNCHANGED before anything new is added.
3. `scoring.clipped_mean` → `aggregate` mean parameter → `runtime.install(exam)`.
4. `professional.py` → `builtins.py` → `prepare.py` row-count invariant.
5. Gates: `uv run .claude/scripts/run_gates.py screamingface-engine`.
6. PR (draft) → green CI → close per `task-management`.

## 4. Out of scope (tracked elsewhere)

- Scoreboard seed entry with this board's revision → scoreboard sub-issue (spec §5).
- SDK example notebook → optional follow-up.
- Any paid run — owner-executed; this unit ships free/offline tests only.
