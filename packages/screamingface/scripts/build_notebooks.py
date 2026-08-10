"""Build the public v1 notebooks deterministically."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
from nbformat import NotebookNode

_DRACO_ANSWER_PROMPT_PARTS = (
    "You are answering a research-quality prompt. Provide a thorough, ",
    "well-reasoned answer in prose. Address every aspect the prompt raises. ",
    "Use clear structure (headings, bullet lists where appropriate) and cite ",
    "specific facts, methodologies, or sources where relevant.\n\n",
    "Do not refuse, abstain, or claim uncertainty unless the question is ",
    "genuinely ambiguous — the goal is to demonstrate depth of understanding. ",
    "Length: aim for the level of detail the question warrants; brevity that ",
    "skips key points will be penalised by the rubric.",
)
_DRACO_ANSWER_PROMPT = "".join(_DRACO_ANSWER_PROMPT_PARTS)

_DRACO_SYNTHESIS_PROMPT_PARTS = (
    "You are synthesising a single, comprehensive answer to a research-quality ",
    "prompt by combining N independent answers from a panel of models. The ",
    "downstream grader will score your output against a STRUCTURED RUBRIC of ",
    "weighted criteria — your goal is to maximise rubric coverage.\n\n",
    "Procedure:\n",
    "1. Read every panel answer carefully.\n",
    "2. Identify which claims, facts, citations, or arguments each panel member ",
    "contributes that the others miss.\n",
    "3. Produce ONE unified prose response that:\n",
    "   - Combines the strongest reasoning from every panel member\n",
    "   - Preserves specific named entities, dates, methodologies, and citations\n",
    "   - Resolves disagreements by favouring the more specific / better-cited claim\n",
    "   - Uses clear structure (headings, lists) where it aids the reader\n",
    "4. Do not introduce new facts that no panel member provided.\n",
    "5. Do not hedge or refuse — the panel collectively has enough material.\n\n",
    "Output: the unified prose answer, no preamble, no JSON wrapper.",
)
_DRACO_SYNTHESIS_PROMPT = "".join(_DRACO_SYNTHESIS_PROMPT_PARTS)


def notebooks() -> dict[str, NotebookNode]:
    return {
        "00_quickstart.ipynb": _quickstart(),
        "01_client_tour.ipynb": _client_tour(),
        "05_draco_lite_e2e.ipynb": _draco_lite_e2e(),
        "06_draco_full_e2e.ipynb": _draco_full_e2e(),
        "07_ifeval_e2e.ipynb": _ifeval_e2e(),
    }


def _notebook(*cells: NotebookNode) -> NotebookNode:
    for index, cell in enumerate(cells, 1):
        cell["id"] = f"cell-{index:02d}"
    return nbformat.v4.new_notebook(
        cells=list(cells),
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12"},
        },
    )


def _local_stack_cell() -> NotebookNode:
    return nbformat.v4.new_markdown_cell(
        """## Before running

From a terminal in `packages/screamingface/`:

```bash
just stack-prepare  # first run only: download pinned Benchmark assets
just stack-up       # start AI Gateway :9105 and Engine :9108
just stack-status
```

Use `just stack-logs` to inspect startup failures and `just stack-down` when finished. Stack
management stays outside the notebook so **Run All** never starts or stops local services."""
    )


def _draco_candidate_policy_cell(*, synthesis: bool = False) -> NotebookNode:
    source = _string_assignment("DRACO_ANSWER_PROMPT", _DRACO_ANSWER_PROMPT_PARTS)
    if synthesis:
        source += "\n\n" + _string_assignment(
            "DRACO_SYNTHESIS_PROMPT",
            _DRACO_SYNTHESIS_PROMPT_PARTS,
        )
    return nbformat.v4.new_code_cell(source)


def _string_assignment(name: str, parts: tuple[str, ...]) -> str:
    literals = "\n".join(f"    {json.dumps(part, ensure_ascii=False)}" for part in parts)
    return f"{name} = (\n{literals}\n)"


def _quickstart() -> NotebookNode:
    """Complete local flow from public discovery through score replay."""

    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace quickstart

Six steps: inspect the public Leaderboards, connect a provider, run a Benchmark, read the
Report, publish its Candidate Result, and replay its URL4. The wider interface is covered in
`01_client_tour.ipynb`."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_code_cell(
            '''import screamingface as sf

sf.configure(
    engine_url="http://127.0.0.1:9108",
    scoreboard_url="http://127.0.0.1:9106",
)

BENCHMARK_ID = "draco/smoke"'''
        ),
        nbformat.v4.new_markdown_cell(
            """## 1 · Leaderboards

Leaderboard discovery reads from the Scoreboard and does not require a provider connection.
`just stack-up` registers the local `draco/smoke` development Leaderboard, so discovery,
evaluation, and publication use the same Benchmark id. Both values render as interactive,
brand-system notebook widgets."""
        ),
        nbformat.v4.new_code_cell("leaderboards = sf.leaderboards.list()\nleaderboards"),
        nbformat.v4.new_code_cell(
            "leaderboard = sf.leaderboards.get(BENCHMARK_ID, top=10)\nleaderboard"
        ),
        nbformat.v4.new_markdown_cell(
            """## 2 · Connect

`sf.connect()` renders the Engine-backed provider panel. A key entered here goes to the SF
Engine for AI Gateway validation and encrypted storage; the notebook never retains it. On a
hosted Engine the panel asks for Cloudflare Access login first."""
        ),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 3 · Evaluate

`draco/smoke` keeps DRACO's execution structure but reduces it to one pinned Case, one
criterion, and one Judge pass. It makes two paid calls — one Candidate answer, one Judge
grade — so the score is diagnostic and **not comparable** to canonical DRACO.

Running this cell makes those two inexpensive calls. While it runs, the live panel shows
progress, model calls, tokens and cost."""
        ),
        nbformat.v4.new_code_cell(
            """candidate = sf.Model("openrouter/google/gemini-3-flash-preview")

report = sf.evaluate(candidate, benchmark=BENCHMARK_ID, limit=1)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 4 · Report

The Report renders score, pass rate, coverage, cost and tokens, with every Case and the
Judge's per-criterion reasoning underneath. **&darr; report.json** downloads the portable
artifact — the same complete JSON document `report.export()` writes to the notebook's working
directory."""
        ),
        nbformat.v4.new_code_cell("report"),
        nbformat.v4.new_code_cell("artifact_path = report.export()\nartifact_path"),
        nbformat.v4.new_markdown_cell(
            """## 5 · Publish and retrieve

Publication accepts the evaluated `CandidateResult` directly. It derives the Benchmark id,
compiled URL4, models, accuracy counts, timestamps, and idempotency key from that immutable
result. Publication is independently opt-in so **Run All** never changes the Scoreboard.

The local Scoreboard accepts writes without login. Hosted deployments may require an
edge-verified identity or keep score submission closed."""
        ),
        nbformat.v4.new_code_cell(
            """PUBLISH_RESULT = False

submission = sf.leaderboards.submit(report.candidates.only) if PUBLISH_RESULT else None
submission if submission is not None else ("Set PUBLISH_RESULT = True to publish this result.")"""
        ),
        nbformat.v4.new_code_cell(
            "published_score = sf.leaderboards.get_score(submission.id) if submission is not None "
            "else None\npublished_score"
        ),
        nbformat.v4.new_code_cell(
            """updated_leaderboard = (
    sf.leaderboards.get(BENCHMARK_ID, top=10) if submission is not None else leaderboard
)
updated_leaderboard"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6 · Fork or replay the submitted URL4

`published_score.url4` is the raw evaluation expression stored by the Scoreboard. Its
`.to_python()` method returns an editable Model/Fusion and evaluation cell without spending.
Passing the URL4 itself to `sf.evaluate(...)` instead executes that exact, already
Benchmark-linked expression and returns a normal `Report`; do not pass `benchmark=` or `limit=`
again.

Replay is a fresh paid Evaluation and model output may differ, so it has its own opt-in guard."""
        ),
        nbformat.v4.new_code_cell(
            "fork_python = published_score.url4.to_python() if published_score is not None "
            "else None\n"
            'print(fork_python) if fork_python is not None else "Publish a score to generate '
            'its Python fork."'
        ),
        nbformat.v4.new_code_cell(
            """REPLAY_RESULT = False

replayed_report = (
    sf.evaluate(published_score.url4) if REPLAY_RESULT and published_score is not None else None
)
replayed_report if replayed_report is not None else (
    "Set REPLAY_RESULT = True after publishing to run the stored URL4 again."
)"""
        ),
    )


def _client_tour() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# ScreamingFace client tour

Explore the full public Client surface without making a paid model call. This complements the
short quickstart: it covers explicit Client lifecycle, Engine discovery, provider connections,
Model and Fusion authoring, hosted authentication, asynchronous use, progress Events, typed
errors, and Report anatomy.

Every state-changing or paid example is either descriptive or guarded off by default."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell(
            """## 1. Choose a Client lifecycle

Module functions such as `sf.models.list()` use one lazy default Client. `sf.configure()` replaces
that default when an application needs another Engine origin, and `sf.close()` closes it.

Long-running applications can instead own an explicit Client and close it deterministically. This
tour uses that form so its lifecycle is visible."""
        ),
        nbformat.v4.new_code_cell(
            """client = sf.Client(engine_url="http://127.0.0.1:9108")
{
    "engine_url": client.engine_url,
    "closed": client.closed,
    "authenticated": client.authenticated,
    "authenticating": client.authenticating,
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """For a hosted Engine protected by Cloudflare Access, caller login is separate from
provider credentials. Protected requests can start login automatically, or an application can be
explicit:

```python
with sf.Client(engine_url="https://your-engine.example") as hosted:
    hosted.login(timeout=300)
    print(hosted.authenticated)
    hosted.logout()
```

Local loopback development does not require that browser flow."""
        ),
        nbformat.v4.new_markdown_cell("## 2. Discover Models and their exact contracts"),
        nbformat.v4.new_code_cell("models = client.models.list()\nmodels"),
        nbformat.v4.new_code_cell(
            """MODEL_ID = "openrouter/google/gemini-3-flash-preview"
model = client.models.get(MODEL_ID)
{
    "id": model.id,
    "provider": model.provider,
    "auth_mode": model.auth_mode,
    "enabled_parameters": [
        name for name, parameter in model.parameters.items() if parameter.enabled
    ],
    "enabled_tools": [
        name for name, capability in model.tools.items() if capability.gateway_status == "enabled"
    ],
    "stale": model.stale,
    "degraded": model.degraded,
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """Parameter schemas are executable contracts. Candidate construction is local;
evaluation preflight validates the selected values against this live Engine contract before any
model request is launched."""
        ),
        nbformat.v4.new_code_cell(
            """max_tokens = model.parameters["max_tokens"]
{
    "request_path": max_tokens.request_path,
    "schema": max_tokens.schema,
    "provider_support": max_tokens.provider_support,
    "gateway_projection": max_tokens.gateway_projection,
    "cache_behavior": max_tokens.cache_behavior,
}"""
        ),
        nbformat.v4.new_markdown_cell("## 3. Discover Benchmarks and pinned variants"),
        nbformat.v4.new_code_cell("benchmarks = client.benchmarks.list()\nbenchmarks"),
        nbformat.v4.new_code_cell(
            """smoke = client.benchmarks.get("draco/smoke")
{
    "id": smoke.id,
    "variant": smoke.variant,
    "title": smoke.title,
    "description": smoke.description,
    "revision": smoke.revision,
    "case_count": smoke.case_count,
}"""
        ),
        nbformat.v4.new_markdown_cell(
            """### Module-level shorthand

Every discovery call above has a module-level form backed by the one lazy default Client.
Use the explicit Client when you need lifecycle control; use these in a notebook."""
        ),
        nbformat.v4.new_code_cell(
            """sf.benchmarks.list()
sf.benchmarks.get("draco/smoke")
sf.models.get("openrouter/google/gemini-3-flash-preview")"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 4. Inspect and manage provider connections

`client.connect()` displays the Engine-backed notebook panel. Applications can also use
`client.connect("openrouter", api_key=...)`, OAuth, `client.connections.get(...)`, and
`client.disconnect(...)`. Provider secrets go to the Engine for validation and encrypted storage;
they are never returned by discovery."""
        ),
        nbformat.v4.new_code_cell("client.connections.list()"),
        nbformat.v4.new_code_cell(
            """MUTATE_CONNECTIONS = False

if MUTATE_CONNECTIONS:
    from getpass import getpass

    connection = client.connect("openrouter", api_key=getpass("OpenRouter API key: "))
else:
    connection = "Connection mutation disabled. Use client.connect() for the notebook panel."
connection"""
        ),
        nbformat.v4.new_markdown_cell(
            """OAuth providers return a bounded flow rather than a secret:

```python
flow = client.connect("provider-id", method="oauth")
print(flow.authorize_url)
connection = flow.wait(timeout=300)  # or flow.cancel()
client.disconnect("provider-id")
```"""
        ),
        nbformat.v4.new_markdown_cell("## 5. Author Models and Fusions locally"),
        nbformat.v4.new_code_cell(
            """writer = sf.Model(
    MODEL_ID,
    name="writer",
    prompt="Answer accurately and explain the important trade-offs.",
    params={"max_tokens": 4096, "temperature": 0.0},
)
reviewer = sf.Model(
    "openrouter/anthropic/claude-haiku-4.5",
    name="reviewer",
    params={"max_tokens": 4096, "temperature": 0.0},
)
panel = sf.Fusion(
    [writer, reviewer],
    name="reviewed-answer",
    synthesizer=sf.Model(
        MODEL_ID,
        prompt="Produce one accurate final answer from the panel responses.",
        params={"max_tokens": 4096, "temperature": 0.0},
    ),
)
[writer, panel]"""
        ),
        nbformat.v4.new_markdown_cell(
            """Recipes contain no Benchmark logic. At evaluation time the Client compiles each
Recipe into URL4 and links it to the selected Engine-owned Benchmark protocol."""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6. Evaluate with progress and typed Events

`progress=True` prints the built-in readable lifecycle. `on_event` receives immutable Events for
custom UI, telemetry, finish-reason/refusal inspection, or logging. `limit` selects a bounded
prefix only when the Benchmark permits it. The run below remains disabled by default."""
        ),
        nbformat.v4.new_code_cell(
            """RUN_EVALUATION = False
events = []

report = (
    client.evaluate(
        [writer, panel],
        benchmark="draco/smoke",
        limit=1,
        on_event=events.append,
        progress=True,
    )
    if RUN_EVALUATION
    else None
)
[event.kind for event in events]"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 7. Read the Report as values or a portable artifact

`Report.ok` means the Evaluation produced scored Candidate results without recorded failures.
Results retain the compiled URL4 graph, model operations, aggregate and per-Case usage, finish
reasons, Benchmark grades, Checks, accepted or rejected raw Evidence, failures, and timing."""
        ),
        nbformat.v4.new_code_cell(
            """if report is not None:
    result = report.candidates["writer"]
    case = result.cases[0]
    report_view = {
        "ok": report.ok,
        "benchmark": report.benchmark,
        "candidate_names": [item.name for item in report.candidates],
        "score": result.score,
        "metrics": dict(result.metrics),
        "url4": result.url4,
        "operations": result.operations,
        "finish_reason": case.finish_reason,
        "grade": case.grade,
        "checks": () if case.grade is None else case.grade.checks,
        "evidence": ()
        if case.grade is None or not case.grade.checks
        else case.grade.checks[0].evidence,
        "failures": report.failures,
        "usage": report.usage,
        "duration_ms": report.duration_ms,
    }
else:
    report_view = "Evaluation disabled — no result to inspect."
report_view"""
        ),
        nbformat.v4.new_code_cell("report.to_json() if report is not None else None"),
        nbformat.v4.new_markdown_cell(
            """## 8. Handle the public error family

Catch `sf.ScreamingFaceError` for Engine, authentication, planning, connection, and execution
failures. More specific subclasses remain available when recovery differs:

```python
try:
    report = client.evaluate(writer, benchmark="draco/smoke", limit=1)
except sf.ProviderConnectionError:
    client.connect()
except sf.PlanningError as exc:
    print(f"Fix the Candidate or Benchmark selection: {exc}")
except sf.ExecutionError as exc:
    print(f"The launched run failed: {exc}")
except sf.ScreamingFaceError as exc:
    print(f"ScreamingFace could not complete the request: {exc}")
```"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 9. Use the asynchronous Client

The asynchronous API mirrors discovery, connections, authentication, and evaluation. Top-level
`await` works in Jupyter, so this metadata-only example is safe to run."""
        ),
        nbformat.v4.new_code_cell(
            """async with sf.AsyncClient(engine_url="http://127.0.0.1:9108") as async_client:
    async_models = await async_client.models.list()
    async_smoke = await async_client.benchmarks.get("draco/smoke")

{"model_count": len(async_models), "benchmark": async_smoke.id}"""
        ),
        nbformat.v4.new_markdown_cell("## 10. Close the explicit Client"),
        nbformat.v4.new_code_cell("client.close()\nclient.closed"),
    )


def _ifeval_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# IFEval: canonical, self-corrective, and LANL ensemble

IFEval contains 541 instruction-following prompts with deterministic checks for requirements such
as word counts, required sections, and forbidden punctuation. Grading uses the vendored official
verifier and makes no grading-model calls.

This notebook compares three independently revisioned Engine protocols:

- `ifeval` invokes the complete Candidate once and grades its final answer.
- `ifeval/self-corrective` gives deterministic failure feedback to the complete Candidate for up
  to three attempts.
- `ifeval/lanl-ensemble` invokes each direct Fusion member, stops when a member passes, and uses
  the configured synthesizer route only for benchmark-owned coaching or exact tie-breaking.

Every evaluation cell below performs paid Candidate calls. Start with `limit=1`, inspect the
Reports, and increase the selection deliberately."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_code_cell(
            """import screamingface as sf

sf.connect()"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Define Candidate-owned answer and synthesis policy

An explicit synthesizer `sf.Model` makes its whole-Fusion prompt and generation parameters
visible. The LANL protocol keeps that Model's route and parameters but replaces the ordinary
blending prompt with its own revisioned coaching and selection instructions."""
        ),
        nbformat.v4.new_code_cell(
            """ANSWER_PROMPT = (
    "Answer the request accurately and completely. "
    "Follow every instruction and formatting constraint in the request."
)
SYNTHESIS_PROMPT = (
    "Produce one final answer to the original request from the panel drafts. "
    "Preserve every instruction and formatting constraint."
)

haiku = sf.Model(
    "openrouter/anthropic/claude-haiku-4.5",
    prompt=ANSWER_PROMPT,
    params={"max_tokens": 4096},
)
gemini = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=ANSWER_PROMPT,
    params={"max_tokens": 4096},
)
kimi = sf.Model(
    "openrouter/moonshotai/kimi-k2.6",
    prompt=ANSWER_PROMPT,
    params={"max_tokens": 4096},
)
panel = sf.Fusion(
    [haiku, gemini],
    name="haiku+gemini",
    synthesizer=sf.Model(
        "openrouter/moonshotai/kimi-k2.6",
        prompt=SYNTHESIS_PROMPT,
        params={"max_tokens": 4096},
    ),
)
[kimi, panel]"""
        ),
        nbformat.v4.new_markdown_cell("## 1. Canonical solo baseline"),
        nbformat.v4.new_code_cell(
            """canonical_solo = sf.evaluate(kimi, benchmark="ifeval", limit=1)
canonical_solo"""
        ),
        nbformat.v4.new_markdown_cell("## 2. Canonical whole-Fusion synthesis"),
        nbformat.v4.new_code_cell(
            """canonical_fusion = sf.evaluate(panel, benchmark="ifeval", limit=1)
canonical_fusion"""
        ),
        nbformat.v4.new_markdown_cell("## 3. Self-corrective Candidate"),
        nbformat.v4.new_code_cell(
            """self_corrective = sf.evaluate(
    sf.Model(
        "openrouter/moonshotai/kimi-k2.6",
        prompt=ANSWER_PROMPT,
        params={"max_tokens": 16384},
    ),
    benchmark="ifeval/self-corrective",
    limit=1,
)
self_corrective"""
        ),
        nbformat.v4.new_markdown_cell("## 4. LANL early-exit ensemble"),
        nbformat.v4.new_code_cell(
            """lanl_ensemble = sf.evaluate(
    panel,
    benchmark="ifeval/lanl-ensemble",
    limit=1,
)
lanl_ensemble"""
        ),
        nbformat.v4.new_markdown_cell("## Compare complete portable artifacts"),
        nbformat.v4.new_code_cell(
            """{
    "canonical_solo": canonical_solo.to_dict(),
    "canonical_fusion": canonical_fusion.to_dict(),
    "self_corrective": self_corrective.to_dict(),
    "lanl_ensemble": lanl_ensemble.to_dict(),
}"""
        ),
    )


def _draco_lite_e2e() -> NotebookNode:
    return _notebook(
        nbformat.v4.new_markdown_cell(
            """# DRACO Lite: a small retrieval-aware comparison

This notebook exercises both retrieval routes through the public ScreamingFace SDK. The Engine
owns the Case, retrieval policy, Judge, Grading, and Aggregation; each SDK Candidate owns only its
answer policy.

`draco/lite` uses two pinned representative Cases, ten criteria per Case, and one Judge pass per
criterion. It is useful for directional development checks, but its score is **not comparable**
to canonical DRACO.

> **Spend warning:** execution is disabled by default. Review the discovered Benchmark and set
> `RUN_EVALUATION = True` deliberately; **Run All** otherwise makes no model calls."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """Export `TAVILY_API_KEY` before `just stack-up`. A missing key fails the Tavily
Candidate before its first paid model request instead of silently running without retrieval. The
connection panel sends the OpenRouter key through the Engine to AI Gateway; the Client never calls
AI Gateway directly."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell("## Define one Candidate per retrieval route"),
        _draco_candidate_policy_cell(),
        nbformat.v4.new_code_cell(
            """DRACO_PARAMS = {"max_tokens": 8192, "temperature": 0.0}
DRACO_PARAMS_NO_TEMPERATURE = {"max_tokens": 8192}

native_search = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
tavily_search = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## Evaluate DRACO Lite

The same Engine-owned lite protocol invokes both Candidates. The current reference deployment
routes GPT through provider-native search and Gemini Flash through the guarded Tavily tool loop.
Success proves both configured routes were available; a model may legitimately answer without
calling an offered function. The repository's forced-tool tests certify actual Tavily
`/search` and `/extract` dispatch deterministically."""
        ),
        nbformat.v4.new_code_cell(
            """RUN_EVALUATION = False

candidates = [native_search, tavily_search]
report = sf.evaluate(candidates, benchmark="draco/lite") if RUN_EVALUATION else None
report_output = (
    report.to_json()
    if report is not None
    else \"Evaluation disabled — set RUN_EVALUATION = True to spend.\"
)
report_output"""
        ),
        nbformat.v4.new_markdown_cell("## Inspect the Report"),
        nbformat.v4.new_code_cell(
            """if report is not None:
    comparison = [
        {
            "name": result.name,
            "score": result.score,
            "metrics": dict(result.metrics),
            "duration_ms": result.duration_ms,
            "finish_reasons": [case.finish_reason for case in result.cases],
            "failures": result.failures,
            "usage": result.usage,
        }
        for result in report.candidates
    ]
else:
    comparison = []
comparison"""
        ),
        nbformat.v4.new_code_cell(
            """if report is not None:
    selected = report.candidates[0]
    selected_case = selected.cases[0]
    detail = {
        "compiled_url4": selected.url4,
        "operations": selected.operations,
        "case_id": selected_case.case_id,
        "input": selected_case.input,
        "output": selected_case.output,
        "finish_reason": selected_case.finish_reason,
        "grade": selected_case.grade,
        "checks": () if selected_case.grade is None else selected_case.grade.checks,
        "failures": selected_case.failures,
    }
else:
    detail = None
detail"""
        ),
        nbformat.v4.new_code_cell(
            """{
    "ok": report.ok,
    "benchmark": report.benchmark,
    "case_count": report.case_count,
    "duration_ms": report.duration_ms,
    "failures": report.failures,
    "usage": report.usage,
} if report is not None else None"""
        ),
    )


def _draco_full_e2e() -> NotebookNode:
    notebook = _notebook(
        nbformat.v4.new_markdown_cell(
            """# Full DRACO pipeline through the ScreamingFace SDK

This is the SDK-native port of the full `pipeline_walkthrough.ipynb` in
`screamingface-benchmarks/notebooks/general/`.
It preserves the published Candidate surface—**7 solo Models and 9 Fusions**—using only the public
SDK. The Engine owns DRACO's dataset, judge, grading, and aggregation. Each SDK Candidate owns its
answer and synthesis policy.

This notebook always selects canonical `draco`: all 100 Cases, every criterion, and five Judge
passes per criterion. It has no smoke or lite switch, so a completed Report is unambiguously a
full Engine-protocol result.

> **Fidelity status:** `full` describes multiplicity, not byte-for-byte reference conformance.
> The Engine uses the DRACO dataset source, official per-criterion Judge instructions, published
> scoring math, reference answer/synthesis system prompts, and the 7-solo/9-Fusion lineup. Do not
> present its score as a reproduced paper or OpenRouter-blog number yet:
>
> - canonical Engine DRACO uses the paper's five Judge passes, while the current source walkthrough
>   uses three; the retired paper Judge is replaced by Gemini 3.1 Pro and `reasoning=low` is not yet
>   forwarded on that OpenRouter route;
> - answer retrieval is route-declared provider-native search or a Tavily search/fetch loop, not the
>   reference harness's single OpenRouter server-tool configuration and exact tool budgets;
> - Fusion writers receive the same question and ordered labeled panel answers, but the universal
>   SDK framing omits the reference template's final redundant “Produce the unified prose answer
>   now.” sentence and labels members by their public Recipe names;
> - the reference harness can reuse prior solo answers in Fusion panels; this run currently makes
>   independent Candidate calls. That can change spend and generated answers, although the grading
>   protocol is unchanged.

> **Spend warning:** execution is disabled by default. Set `RUN_EVALUATION = True` only after
> reviewing the full experiment's estimated scope."""
        ),
        _local_stack_cell(),
        nbformat.v4.new_markdown_cell(
            """Export `TAVILY_API_KEY` before `just stack-up`: the Gemini, Kimi, DeepSeek, and
Qwen answer routes use its guarded tool loop, and the Engine fails before model spend when that
required retrieval mechanism is unavailable."""
        ),
        nbformat.v4.new_code_cell("import screamingface as sf"),
        nbformat.v4.new_markdown_cell("## 1. Connect OpenRouter"),
        nbformat.v4.new_code_cell("sf.connect()"),
        nbformat.v4.new_markdown_cell(
            """## 2. Define the full solo lineup

These are the seven solo Candidates from the original full-pipelines notebook. Qwen is also
defined because it participates in the open-source Fusion. The reference configuration requires
at least 8,192 output tokens for answer and tool paths, so this notebook pins that Candidate policy
instead of inheriting the SDK's smaller general default.

The Gateway's live model contract currently marks `temperature` unsupported for Fable 5 and
GPT-5.5. Their requests therefore omit it; every model that supports it retains the reference
temperature of zero."""
        ),
        _draco_candidate_policy_cell(synthesis=True),
        nbformat.v4.new_code_cell(
            """DRACO_PARAMS = {"max_tokens": 8192, "temperature": 0.0}
DRACO_PARAMS_NO_TEMPERATURE = {"max_tokens": 8192}

fable = sf.Model(
    "openrouter/anthropic/claude-fable-5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
opus = sf.Model(
    "openrouter/anthropic/claude-opus-4.8",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
gpt = sf.Model(
    "openrouter/openai/gpt-5.5",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS_NO_TEMPERATURE,
)
gemini_pro = sf.Model(
    "openrouter/google/gemini-3.1-pro-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
gemini_flash = sf.Model(
    "openrouter/google/gemini-3-flash-preview",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
kimi = sf.Model(
    "openrouter/moonshotai/kimi-k2.6",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
deepseek = sf.Model(
    "openrouter/deepseek/deepseek-v4-pro",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)
qwen = sf.Model(
    "openrouter/qwen/qwen3.6-plus",
    prompt=DRACO_ANSWER_PROMPT,
    params=DRACO_PARAMS,
)"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 3. Define the nine Fusion Candidates

Each Fusion names the synthesizer from the reproduced configuration explicitly. Equivalent Models
deduplicate inside one Candidate graph. The self-Fusion uses explicit sample identities and
temperature so its two Opus calls remain independent. DRACO gives guarded retrieval to
answer-producing members; whole-Fusion synthesis and the Benchmark-owned Judge remain
retrieval-free.

The reference harness can reuse solo answers across overlapping Fusion panels. Until the Engine's
cross-Candidate cache lands, this SDK run evaluates each Candidate independently and may repeat
those member calls. The grading protocol stays fixed, but fresh provider calls can change both the
generated answer and spend; cross-harness scores therefore are not assumed identical."""
        ),
        nbformat.v4.new_code_cell(
            """fable_plus_gpt = sf.Fusion(
    [fable, gpt],
    name="fable_plus_gpt",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
frontier_trio = sf.Fusion(
    [opus, gpt, gemini_pro],
    name="frontier_trio",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
opus_plus_gpt = sf.Fusion(
    [opus, gpt],
    name="opus_plus_gpt",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
opus_self_fusion = sf.Fusion(
    [
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-1",
            prompt=DRACO_ANSWER_PROMPT,
            params={"max_tokens": 8192, "temperature": 0.7},
        ),
        sf.Model(
            "openrouter/anthropic/claude-opus-4.8",
            name="opus-sample-2",
            prompt=DRACO_ANSWER_PROMPT,
            params={"max_tokens": 8192, "temperature": 0.7},
        ),
    ],
    name="opus_self_fusion",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
budget_trio = sf.Fusion(
    [gemini_flash, kimi, deepseek],
    name="budget_trio",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
beat_runner_up = sf.Fusion(
    [opus, gpt, deepseek],
    name="beat_runner_up",
    synthesizer=sf.Model(
        "openrouter/anthropic/claude-opus-4.8",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
pareto_cross = sf.Fusion(
    [deepseek, kimi, gpt],
    name="pareto_cross",
    synthesizer=sf.Model(
        "openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
pareto_lean = sf.Fusion(
    [deepseek, kimi],
    name="pareto_lean",
    synthesizer=sf.Model(
        "openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)
best_open_source = sf.Fusion(
    [deepseek, kimi, qwen],
    name="best_open_source",
    synthesizer=sf.Model(
        "openrouter/deepseek/deepseek-v4-pro",
        prompt=DRACO_SYNTHESIS_PROMPT,
        params=DRACO_PARAMS,
    ),
)"""
        ),
        nbformat.v4.new_markdown_cell("## 4. Arm the canonical run explicitly"),
        nbformat.v4.new_code_cell("RUN_EVALUATION = False"),
        nbformat.v4.new_markdown_cell(
            """## 5. Evaluate every Candidate

One Evaluation runs the complete Candidate lineup concurrently. Leaving
`RUN_EVALUATION = False` makes **Run All** safe and performs no model calls."""
        ),
        nbformat.v4.new_code_cell(
            """candidates = [
    fable,
    opus,
    gpt,
    gemini_pro,
    gemini_flash,
    kimi,
    deepseek,
    fable_plus_gpt,
    frontier_trio,
    opus_plus_gpt,
    opus_self_fusion,
    budget_trio,
    beat_runner_up,
    pareto_cross,
    pareto_lean,
    best_open_source,
]

report = sf.evaluate(candidates, benchmark="draco") if RUN_EVALUATION else None
report_output = (
    report.to_json()
    if report is not None
    else \"Evaluation disabled — set RUN_EVALUATION = True to spend.\"
)
report_output"""
        ),
        nbformat.v4.new_markdown_cell(
            """## 6. Inspect the Report

The Report presents a typed leaderboard plus the exact Case artifacts, failures, operation graphs,
timing, usage, and portable JSON needed to audit the full experiment."""
        ),
        nbformat.v4.new_code_cell(
            """if report is not None:
    leaderboard = sorted(
        (
            {
                "name": result.name,
                "kind": result.kind,
                "score": result.score,
                "duration_ms": result.duration_ms,
                "failures": len(result.failures),
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost_usd": result.usage.cost_usd,
            }
            for result in report.candidates
        ),
        key=lambda row: (row["score"] is not None, row["score"] or 0.0),
        reverse=True,
    )
else:
    leaderboard = []
leaderboard"""
        ),
        nbformat.v4.new_code_cell(
            """if report is not None:
    selected = report.candidates[0]
    selected_case = selected.cases[0]
    audit_sample = {
        "candidate": selected.name,
        "compiled_url4": selected.url4,
        "models": selected.models,
        "operations": selected.operations,
        "members": selected.members,
        "case_id": selected_case.case_id,
        "finish_reason": selected_case.finish_reason,
        "grade": selected_case.grade,
        "checks": () if selected_case.grade is None else selected_case.grade.checks,
        "case_failures": selected_case.failures,
    }
else:
    audit_sample = None
audit_sample"""
        ),
        nbformat.v4.new_code_cell(
            """{
    "ok": report.ok,
    "benchmark": report.benchmark,
    "case_count": report.case_count,
    "duration_ms": report.duration_ms,
    "failures": report.failures,
    "usage": report.usage,
} if report is not None else None"""
        ),
        nbformat.v4.new_code_cell("report.to_json() if report is not None else None"),
    )
    notebook.metadata["kernelspec"] = {
        "display_name": "screamingface (SDK)",
        "language": "python",
        "name": "screamingface-sdk",
    }
    return notebook


def main() -> None:
    examples = Path(__file__).parents[1] / "examples"
    for name, value in notebooks().items():
        nbformat.write(value, examples / name)


if __name__ == "__main__":
    main()
