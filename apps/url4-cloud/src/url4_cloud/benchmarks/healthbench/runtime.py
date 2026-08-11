"""Install HealthBench's private assets and deterministic functions into one Runner world.

If ``definition.py`` writes the recipe (the expression tree that names six routes),
this module is the kitchen: it registers a handler behind each of those routes so the
recipe can actually resolve. Data flows through them in exam order:

    /cases             → serve the selected question booklet (from the baked assets)
    /rubric-tasks      → Candidate answered one Case: fetch its private rubric, render
                         one fully-built judge prompt per rubric item
    /rubric-verdict    → parse one judge reply into a verdict (or raise → retry)
    /rubric-evaluation → staple {case, rubric, verdict} into one row
    /case-evaluation   → collect a Case's rows into its per-Case artifact
    /aggregate         → reduce all Case artifacts into the final score

Everything here is deterministic — the model calls live in the expression, not in
these handlers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from url4.core.errors import ResolutionError
from url4.peer.server import Request, Url4Node
from url4_cloud.benchmarks.contract import (
    CANDIDATE_INPUT_SCHEMA,
    decode_candidate_invocation,
)
from url4_cloud.benchmarks.healthbench import aggregate as reducing
from url4_cloud.benchmarks.healthbench import records
from url4_cloud.benchmarks.healthbench.case_evaluation import (
    bind_case_evaluation,
    bind_rubric_evaluation,
)
from url4_cloud.benchmarks.healthbench.definition import (
    AGGREGATE_ROUTE,
    BENCHMARK_ID,
    CASE_EVALUATION_ROUTE,
    CASES_ROUTE,
    JUDGE_MODEL,
    REVISION,
    RUBRIC_EVALUATION_ROUTE,
    TASKS_ROUTE,
    VERDICT_ROUTE,
    WORST30_CASE_IDS,
)
from url4_cloud.benchmarks.healthbench.prompts import build_grader_prompt, render_rubric_item
from url4_cloud.benchmarks.healthbench.verdict import bind, binding_key


def install(node: Url4Node, root: Path) -> None:
    """Register every route referenced by the HealthBench expressions.

    Providers read lazily so a general-purpose Runner can carry the installed
    definition without HealthBench's private image assets — until an expression
    actually selects HealthBench, which is when the preflight below runs.
    """
    # Install the six routes that implement the exam's protocol.
    _install_protocol_once(
        node,
        root,
        cases_route=CASES_ROUTE,
        tasks_route=TASKS_ROUTE,
        verdict_route=VERDICT_ROUTE,
        rubric_evaluation_route=RUBRIC_EVALUATION_ROUTE,
        case_evaluation_route=CASE_EVALUATION_ROUTE,
        aggregate_route=AGGREGATE_ROUTE,
        benchmark_id=BENCHMARK_ID,
        benchmark_revision=REVISION,
        case_ids=WORST30_CASE_IDS,
    )


def _install_protocol_once(
    node: Url4Node,
    root: Path,
    *,
    cases_route: str,
    tasks_route: str,
    verdict_route: str,
    rubric_evaluation_route: str,
    case_evaluation_route: str,
    aggregate_route: str,
    benchmark_id: str,
    benchmark_revision: str,
    case_ids: tuple[int, ...],
) -> None:
    if cases_route not in getattr(node, "_data", {}):
        node.data(cases_route, _cases(root, case_ids), media_type="application/json")
    routes = frozenset(node.processor_routes())
    endpoints = (
        (tasks_route, _rubric_tasks(root, case_ids)),
        (verdict_route, _rubric_verdict),
        (rubric_evaluation_route, _rubric_evaluation),
        (case_evaluation_route, _case_evaluation),
        (aggregate_route, _aggregate(root, benchmark_id, benchmark_revision, case_ids)),
    )
    for route, handler in endpoints:
        if route not in routes:
            node.endpoint(route)(handler)


def preflight(root: Path, case_ids: tuple[int, ...]) -> None:
    """Fail before the FIRST paid call when the baked assets cannot serve this exam.

    A broken asset (missing cases.json, unreadable rubric) is knowable before any
    model runs. Without this check it would surface in the reducer — AFTER paying
    for the full Candidate + judge run, only to score None (review S-DR3). So the
    cases route runs this first: broken image → fail in seconds for free. The
    reducer still re-checks the same conditions (B1) — defense in depth.
    """

    problems: list[str] = []
    if not (root / "cases.json").is_file():
        problems.append(f"cases.json missing under {root}")
    else:
        try:
            rows = json.loads((root / "cases.json").read_text(encoding="utf-8"))
            present = {row.get("id") for row in rows if isinstance(row, Mapping)}
            missing = [case_id for case_id in case_ids if case_id not in present]
            if missing:
                problems.append(f"cases.json lacks selected cases {missing[:5]}")
        except (OSError, ValueError) as exc:
            problems.append(f"cases.json unreadable: {exc}")
    for case_id in case_ids:
        if reducing.load_rubric_points(root, case_id) is None:
            problems.append(f"rubric asset for case {case_id} missing or invalid")
    if problems:
        raise _unavailable("HealthBench assets failed preflight: " + "; ".join(problems[:8]))


def _cases(root: Path, case_ids: tuple[int, ...]):
    # Reference counterpart: the example selection at the top of the reference's
    # eval loop (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py)
    # — here the selection is the frozen worst-30% subset served from baked assets.
    def cases() -> str:
        preflight(root, case_ids)
        raw = _read(root / "cases.json", "HealthBench cases")
        return json.dumps(_select_cases(raw, case_ids), ensure_ascii=False, separators=(",", ":"))

    return cases


def _rubric_tasks(root: Path, case_ids: tuple[int, ...]):
    # The fan-out point: one Candidate answer in, N ready-to-send judge tasks out.
    # Receives the Candidate's output (context) + the Case id (intent); pulls the
    # PRIVATE rubric off disk — the first time the answer key touches the flow.
    # Reference counterpart: the prompt-construction half of `grade_sample`
    # (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py).
    def rubric_tasks(request: Request) -> str:
        try:
            case_id = _positive_case_id(request.intent)
            output, finish_reason, refusal = decode_candidate_invocation(request.context)
            if refusal is not None:
                raise ResolutionError(
                    "Candidate refused the HealthBench Case",
                    code="provider_refusal",
                    permanent=True,
                )
            raw_cases = _read(root / "cases.json", "HealthBench cases")
            transcript = _transcript(raw_cases, case_id)
            items = _rubric_items(root, case_id)
            case_record = records.bind_case(
                raw_cases, case_id=case_id, output=output, finish_reason=finish_reason
            )
            rows: list[dict[str, str]] = []
            for item in items:
                rendered = render_rubric_item(item["points"], item["criterion"])
                rubric_record = records.bind_rubric_item(
                    rendered, case_id=case_id, rubric_id=item["rubric_id"]
                )
                rows.append(
                    {
                        "case_id": str(case_id),
                        "rubric_id": str(item["rubric_id"]),
                        # INVARIANT: the judge prompt is fully rendered HERE, engine-
                        # side, so its bytes match the reference `grade_sample` exactly
                        # — nothing about the prompt is assembled inside the expression.
                        "grader_prompt": build_grader_prompt(transcript, output, rendered),
                        # Dedup: the full Case record (Candidate's whole output) rides
                        # the FIRST task only; the rest carry "{}" — case_evaluation.py
                        # hoists it back to one record per Case.
                        "case_record": (
                            json.dumps(case_record, ensure_ascii=False, separators=(",", ":"))
                            if not rows
                            else "{}"
                        ),
                        "rubric_record": json.dumps(
                            rubric_record, ensure_ascii=False, separators=(",", ":")
                        ),
                    }
                )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    return rubric_tasks


def _rubric_verdict(request: Request) -> str:
    # The parse gate between "the judge said something" and "we have a verdict":
    # context = the raw judge reply, intent = "case_id:rubric_id" (Engine-stamped,
    # never trusted from the judge).
    # Reference counterpart: the parse-and-retry half of `grade_sample`
    # (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py).
    try:
        case_id, rubric_id = binding_key(request.intent)
        record = bind(
            request.context,
            case_id=case_id,
            rubric_id=rubric_id,
            producer_id=JUDGE_MODEL,
        )
    except ValueError as exc:
        raise _unavailable(str(exc)) from exc
    if record.get("valid") is not True:
        # WHY transient, not a returned record: the expression's `;retry=` on this
        # route re-resolves the NESTED judge call, so each re-ask draws a fresh
        # sample at provider-default temperature — the reference's retry mechanism,
        # bounded (`grade_sample` loops forever on the same condition). After the
        # bounded retries the error propagates and the CASE fails loudly, keeping
        # the reply head as audit evidence.
        raw = str(record.get("raw_output") or "")
        raise ResolutionError(
            f"invalid judge reply for case {case_id} rubric {rubric_id} "
            f"({record.get('reason')}): {raw[:200]!r}",
            code="judge_reply_invalid",
            permanent=False,
        )
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def _rubric_evaluation(request: Request) -> str:
    try:
        case_id = _positive_case_id(request.intent)
        payload = _object(request.context, "HealthBench rubric evaluation")
        # Exact keys in exact order — the payload comes from OUR expression's struct()
        # (definition.py), so any drift means the expression and runtime disagree.
        if tuple(payload) != ("case", "rubric", "evidence"):
            raise ValueError("HealthBench rubric evaluation fields must be case, rubric, evidence")
        raw_case = _embedded_object(payload["case"], "Case record")
        result = bind_rubric_evaluation(
            case_id,
            raw_case or None,
            _embedded_object(payload["rubric"], "Rubric record"),
            _embedded_object(payload["evidence"], "Rubric verdict"),
        )
    except (TypeError, ValueError) as exc:
        raise _unavailable(str(exc)) from exc
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _case_evaluation(request: Request) -> str:
    try:
        case_id = _positive_case_id(request.intent)
        raw = json.loads(request.context)
        if not isinstance(raw, list) or not raw:
            raise ValueError("HealthBench Case evaluation must be a non-empty JSON array")
        evaluations = [
            _embedded_object(item, f"Rubric evaluation {index}")
            for index, item in enumerate(raw, start=1)
        ]
        result = bind_case_evaluation(case_id, evaluations)
    except (TypeError, ValueError) as exc:
        # WHY the context head in the error: this route sits on the resolver seam —
        # its context is whatever the runner rendered for the rubric_rows collection.
        # A live failure here (2026-08-06 smoke run) was undiagnosable without seeing
        # the actual payload, and this error IS the audit record that reaches the
        # report via on_error=collect.
        raise _unavailable(f"{exc}; context head: {request.context[:300]!r}") from exc
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _aggregate(
    root: Path,
    benchmark_id: str,
    benchmark_revision: str,
    case_ids: tuple[int, ...],
):
    def aggregate_handler(request: Request) -> str:
        # Intent is "aggregate:<selected>" — the expression tells the reducer how
        # many Cases the run actually selected (a `limit=N` run slices the Case
        # loop, and scoring the full installed list would fail every un-run Case).
        operation, _, raw_count = request.intent.partition(":")
        if operation != "aggregate" or not raw_count.isdigit():
            raise ResolutionError(
                f"unsupported HealthBench operation {request.intent!r}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        selected = int(raw_count)
        if not 1 <= selected <= len(case_ids):
            raise ResolutionError(
                f"HealthBench aggregate selection {selected} is outside 1..{len(case_ids)}",
                code="benchmark_operation_unsupported",
                permanent=True,
            )
        try:
            result = reducing.aggregate(
                request.context,
                root,
                benchmark_id=benchmark_id,
                benchmark_revision=benchmark_revision,
                # The slice in the expression is (0, selected) over this same
                # ordering, so the selected prefix IS the run's Case list.
                case_ids=case_ids[:selected],
            )
        except (OSError, ValueError) as exc:
            raise _unavailable(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    return aggregate_handler


def _transcript(raw_cases: str, case_id: int) -> str:
    """The reference's judge/display form — ``"role: content"`` turns joined by blank lines.

    Reference counterpart: how ``grade_sample`` flattens the conversation before
    substituting it into ``<<conversation>>``
    (https://github.com/openai/simple-evals/blob/main/healthbench_eval.py) — the
    judge must see the transcript in exactly these bytes.
    """

    for row in json.loads(raw_cases):
        if isinstance(row, Mapping) and row.get("id") == case_id:
            envelope = json.loads(str(row.get("input")))
            if (
                not isinstance(envelope, Mapping)
                or envelope.get("schema") != CANDIDATE_INPUT_SCHEMA
            ):
                raise ValueError(f"HealthBench case {case_id} input is not a chat envelope")
            messages = envelope.get("messages")
            decoded = json.loads(messages) if isinstance(messages, str) else messages
            if not isinstance(decoded, list) or not decoded:
                raise ValueError(f"HealthBench case {case_id} carries no messages")
            return "\n\n".join(
                f"{turn.get('role')}: {turn.get('content')}"
                for turn in decoded
                if isinstance(turn, Mapping)
            )
    raise ValueError(f"unknown HealthBench case {case_id}")


def _rubric_items(root: Path, case_id: int) -> list[dict[str, Any]]:
    path = root / "rubrics" / f"{case_id}.json"
    decoded = json.loads(_read(path, f"HealthBench rubric {case_id}"))
    items = decoded.get("items") if isinstance(decoded, Mapping) else None
    if not isinstance(items, list) or not items:
        raise ValueError(f"HealthBench rubric {case_id} carries no items")
    return items


def _positive_case_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("case_id must be a positive integer")
    try:
        selected = int(value)
    except ValueError:
        raise ValueError("case_id must be a positive integer") from None
    if selected < 1:
        raise ValueError("case_id must be a positive integer")
    return selected


def _select_cases(raw: str, case_ids: tuple[int, ...]) -> list[dict[str, object]]:
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("expected a JSON array of objects")
        by_id = {row["id"]: row for row in rows}
        return [by_id[case_id] for case_id in case_ids]
    except (KeyError, TypeError, ValueError) as exc:
        raise _unavailable(f"could not select HealthBench cases {case_ids}: {exc}") from exc


def _object(value: str, label: str) -> dict[str, object]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must be a JSON object")
    return decoded


def _embedded_object(value: object, label: str) -> dict[str, object]:
    decoded = json.loads(value) if isinstance(value, str) else value
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must decode to an object")
    return decoded


def _read(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _unavailable(f"could not read {label} at {str(path)!r}: {exc}") from exc


def _unavailable(detail: str) -> ResolutionError:
    return ResolutionError(
        detail,
        code="benchmark_unavailable",
        permanent=True,
    )


__all__ = ["install", "preflight"]
