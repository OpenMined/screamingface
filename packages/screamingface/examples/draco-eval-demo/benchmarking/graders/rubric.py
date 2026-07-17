"""
DRACO rubric grading — per-criterion verdicts → headline metrics.

Mirrors the methodology in the DRACO paper and the OpenRouter post:

  normalized_score  weight-aware: Σ MET positive weights minus Σ MET negative
                    weights, divided by Σ positive weights, clamped to [0, 1].
                    This is the paper's primary metric (also the only metric
                    the OpenRouter post reports).
  pass_rate         unweighted: fraction of criteria "correctly handled" —
                    positive-weight criteria that are MET plus negative-weight
                    criteria that are UNMET. The paper reports it alongside
                    normalized_score as a more robust-to-weight-noise signal.
  axis_scores       normalized_score computed per rubric section ("axis" —
                    Factual Accuracy / Breadth & Depth / Presentation Quality
                    / Citation Quality on typical DRACO rubrics).

Each grading call can be run N independent times (`judge_runs`) and the
results averaged. The paper uses 5; the OpenRouter post uses 3.
"""

from __future__ import annotations

import json
import logging
import weakref
from collections import defaultdict
from functools import lru_cache
from statistics import mean, stdev
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from benchmarking.graders.errors import RubricShapeError
from runners.spend_guard import SpendGuardError

logger = logging.getLogger(__name__)

# Rubric grading intentionally does NOT emit `is_correct`.
# The DRACO paper defines no pass/fail threshold on `normalized_score`;
# the previous `PASS_THRESHOLD = 0.60` invention was removed to avoid
# any impression that a threshold-derived boolean is a DRACO-reported
# metric. Rubric result dicts OMIT `is_correct` (and `response_type`)
# entirely — the evaluators and `_make_record` only emit those fields
# when a grader returns a real boolean. Use `normalized_score`,
# `pass_rate`, `accuracy`, and `axis_scores` for real signal.

# How many times to retry a per-criterion judge call when the reply
# fails Pydantic validation. The paper's harness expects clients to
# retry on validation failure (per_criterion_grader.py's docstring:
# "Users handle parsing, validation, and retries in their
# implementation"). Retries fire only on validation errors — transient
# HTTP errors are already handled by allm_generate's retry loop.
PER_CRITERION_VALIDATION_RETRIES = 2

# Cap on simultaneously in-flight per-criterion judge calls, shared across
# every row graded on the same event loop. The row-level semaphore in
# arena/base.py bounds ROWS, not judge calls — one DRACO row fans out to
# n_criteria × judge_runs calls, so 20 concurrent rows × ~50 criteria ×
# 3 runs would otherwise put thousands of requests in flight at once.
# The resulting 429 storm burns allm_generate's retry budget, and every
# exhausted call drops its verdict — wasted spend and shrunken
# verdict_coverage on the very rows being published.
PER_CRITERION_MAX_INFLIGHT_JUDGE_CALLS = 32

# One semaphore per event loop (weak-keyed so test loops don't accumulate).
_judge_call_sems: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _judge_call_semaphore() -> "asyncio.Semaphore":  # noqa: F821 — lazy import
    import asyncio

    loop = asyncio.get_running_loop()
    sem = _judge_call_sems.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(PER_CRITERION_MAX_INFLIGHT_JUDGE_CALLS)
        _judge_call_sems[loop] = sem
    return sem


# ---------------------------------------------------------------------------
# Per-criterion judge output — validated at the LLM boundary.
# Byte-for-byte match for `PerCriterionOutput` in the harness at
# github.com/The-LLM-Data-Company/rubric ⇒ src/rubric/autograders/schemas.py.
# ---------------------------------------------------------------------------


class PerCriterionOutput(BaseModel):
    """One criterion's verdict as returned by the per-criterion judge.

    Populated straight from the judge's raw JSON — the paper's Appendix
    C.5 instructs the model to emit exactly this shape:
        {"explanation": "...", "criterion_status": "MET" | "UNMET"}
    """

    explanation: str = Field(
        description=("Judge's brief rationale for why the criterion is MET / UNMET.")
    )
    criterion_status: Literal["MET", "UNMET"] = Field(
        description=(
            "Whether the thing described in the criterion IS ('MET') "
            "or IS NOT ('UNMET') present in the response. This has no "
            "direct 'good'/'bad' meaning — negative criteria being MET "
            "penalises the score in downstream aggregation."
        )
    )


# ---------------------------------------------------------------------------
# Rubric parsing
# ---------------------------------------------------------------------------


def parse_rubric(raw: Any) -> dict:
    """Parse a Draco eval row's `expected_answer` into a dict.

    `expected_answer` lives in the dataset JSONL as a string (per the
    ScreamingFace schema — every field is a Value('string')). It's actually a
    JSON-encoded rubric. We accept either the raw string or an already-
    parsed dict, and return a normalised dict shape.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise TypeError(
            f"expected_answer must be str or dict, got {type(raw).__name__}"
        )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError(
            "rubric JSON must be an object with 'sections', got "
            f"{type(parsed).__name__}"
        )
    return parsed


def _zero_criteria_msg(rubric: dict) -> str:
    return (
        "rubric flattened to 0 criteria — expected "
        "{'sections': [{'criteria': [...]}]}; got top-level keys: "
        f"{list(rubric)[:5]}. A flat criteria list (HealthBench-style) "
        "needs grader 'healthbench_rubric', not 'rubric'."
    )


def _flatten_criteria(rubric: dict) -> list[dict]:
    """Walk rubric sections → flat list of criteria with axis attached.

    Each returned dict has at least: id (str), weight (int|float),
    requirement (str), axis (str — the section's id or title).
    """
    out: list[dict] = []
    for section in rubric.get("sections", []):
        axis = section.get("id") or section.get("title") or "unknown"
        for c in section.get("criteria", []) or []:
            row = dict(c)
            row.setdefault("weight", 0)
            row["axis"] = axis
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# Score computation (single run)
# ---------------------------------------------------------------------------


def normalized_score(rubric: dict, verdicts: dict[str, bool]) -> float:
    """Weight-aware normalised score in [0, 1] — paper formula, exact.

    From the DRACO paper (arXiv:2602.11685, §4.2):

        score = clamp(Σ MET·w / Σ w+ , [0, 1])

    where w+ ranges over positive weights only. Positive criteria being
    MET adds to the numerator (reward). Negative criteria being MET
    subtracts from the numerator (penalty). The denominator is only the
    positive weights — this is the maximum reachable numerator (every
    positive MET, every negative UNMET).

    DRACO tasks always ship with ≥ 1 positive criterion, so the paper
    doesn't define behaviour for all-negative rubrics. We return 0.0
    for that undefined case; do NOT interpolate a harness-specific
    fallback formula (would drift from the paper).
    """
    weighted_sum = 0.0
    denom_pos = 0.0
    for c in _flatten_criteria(rubric):
        w = float(c.get("weight", 0))
        met = bool(verdicts.get(c["id"], False))
        if w > 0:
            denom_pos += w
            if met:
                weighted_sum += w
        elif w < 0 and met:
            weighted_sum += w  # subtracts (w is negative)

    if denom_pos <= 0:
        return 0.0
    return max(0.0, min(1.0, weighted_sum / denom_pos))


def _restrict_rubric(rubric: dict, judged_ids) -> dict:
    """Rubric minus criteria that produced no verdict.

    The paper's normalization assumes every criterion is judged. When a
    verdict is missing (judge reply never validated), the harness's
    aggregate() computes both numerator and denominator over the
    CriterionReports it actually receives — an unjudged criterion drops
    out of both. Counting it as UNMET instead (weight kept in the
    denominator) would deflate scores in proportion to judge parse or
    transport failures.
    """
    return {
        "sections": [
            {
                **s,
                "criteria": [
                    c for c in (s.get("criteria") or []) if c.get("id") in judged_ids
                ],
            }
            for s in rubric.get("sections", [])
        ]
    }


def pass_rate(rubric: dict, verdicts: dict[str, bool]) -> float:
    """Unweighted fraction of criteria correctly handled.

    For positive-weight criteria, correct means MET. For negative-weight
    criteria (anti-patterns), correct means UNMET.
    """
    n_correct = 0
    n_total = 0
    for c in _flatten_criteria(rubric):
        w = float(c.get("weight", 0))
        met = bool(verdicts.get(c["id"], False))
        if w >= 0 and met:
            n_correct += 1
        elif w < 0 and not met:
            n_correct += 1
        n_total += 1
    return (n_correct / n_total) if n_total else 0.0


def axis_scores(rubric: dict, verdicts: dict[str, bool]) -> dict[str, float]:
    """`normalized_score` recomputed per rubric section ("axis")."""
    by_axis: dict[str, list[float]] = defaultdict(
        lambda: [0.0, 0.0]
    )  # [achieved, achievable]
    for c in _flatten_criteria(rubric):
        w = float(c.get("weight", 0))
        met = bool(verdicts.get(c["id"], False))
        axis = c["axis"]
        if w >= 0:
            by_axis[axis][1] += w
            if met:
                by_axis[axis][0] += w
        else:
            if met:
                by_axis[axis][0] += w  # subtracts
    out: dict[str, float] = {}
    for axis, (ach, total) in by_axis.items():
        out[axis] = max(0.0, min(1.0, ach / total)) if total > 0 else 0.0
    return out


def axis_pass_rates(rubric: dict, verdicts: dict[str, bool]) -> dict[str, float]:
    """Unweighted pass rate per rubric section.

    Same machinery as the global `pass_rate` but restricted per axis —
    the paper reports both weighted (`axis_scores`) and unweighted
    (`axis_pass_rates`) per axis. A positive-weight criterion counts
    when MET; a negative-weight criterion counts when UNMET (penalty
    correctly avoided).
    """
    by_axis: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [n_correct, n_total]
    for c in _flatten_criteria(rubric):
        w = float(c.get("weight", 0))
        met = bool(verdicts.get(c["id"], False))
        axis = c["axis"]
        if (w >= 0 and met) or (w < 0 and not met):
            by_axis[axis][0] += 1
        by_axis[axis][1] += 1
    return {
        axis: (correct / total) if total > 0 else 0.0
        for axis, (correct, total) in by_axis.items()
    }


# Per the DRACO paper, "accuracy" is not its own metric — it is the
# normalized score restricted to criteria tagged as Factual Accuracy.
# We tolerate ID variants (hyphens, underscores, casing) so we don't
# silently mis-route when rubric section IDs vary.
_FACTUAL_ACCURACY_KEYS = ("factual-accuracy", "factual_accuracy", "factualaccuracy")


def _factual_axis_value(axes: dict[str, float], default: float = 0.0) -> float:
    """Look up the factual-accuracy axis score, tolerant of ID variants."""
    if not axes:
        return default
    for k, v in axes.items():
        norm = str(k).lower().replace("_", "-").replace(" ", "-")
        if norm in _FACTUAL_ACCURACY_KEYS:
            return float(v)
    return default


# ---------------------------------------------------------------------------
# Judge response parser
# ---------------------------------------------------------------------------


class CriterionVerdict(BaseModel):
    """One rubric-criterion verdict as the judge emits it."""

    id: str
    met: bool = False


class RubricVerdicts(BaseModel):
    """The judge's full reply: `{"verdicts": [{"id": …, "met": …}, …]}`."""

    verdicts: list[CriterionVerdict]

    def as_map(self) -> dict[str, bool]:
        return {v.id: v.met for v in self.verdicts}


def parse_judge_response(raw: str) -> dict[str, bool]:
    """Extract `{criterion_id: met}` from the judge's reply, validated
    through the `RubricVerdicts` / `CriterionVerdict` models.

    Robust to the common shapes the judge emits in practice:
      - bare JSON object
      - JSON wrapped in ```json … ``` fences
      - JSON preceded by a short preamble ("Here are my verdicts:")
      - JSON with trailing prose after the closing brace
      - **truncated JSON** (judge hit max_tokens mid-stream) — we scan
        for individual complete `{"id": …, "met": …}` objects and
        salvage every one that validates as a `CriterionVerdict`

    Returns an empty dict only when no verdict object can be extracted
    at all — the caller treats that run as failed.
    """
    if not raw:
        return {}
    text = raw.strip()

    # Strip ```json / ``` fences if the judge wrapped its output.
    if "```" in text:
        text = "\n".join(
            l for l in text.splitlines() if not l.strip().startswith("```")
        ).strip()

    # First attempt: full JSON parse. Handles complete responses cleanly.
    data = None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = _extract_first_json_object(text)

    if isinstance(data, dict):
        if isinstance(data.get("verdicts"), list):
            try:
                out = RubricVerdicts.model_validate(data).as_map()
            except ValidationError:
                # Partially-malformed list — salvage the entries that do
                # validate rather than dropping the whole run.
                out = _validate_verdict_objects(data["verdicts"])
            if out:
                return out
        # Alt shape: flat {criterion_id: bool} map.
        if all(isinstance(v, bool) for v in data.values()):
            return {str(k): bool(v) for k, v in data.items()}

    # Salvage: walk the text picking off every complete `{...}` object
    # that carries `id` + `met`. Works on truncated / malformed JSON —
    # we get partial verdict recovery instead of zero.
    salvaged = _scan_verdict_objects(text)
    if salvaged:
        logger.warning(
            "draco.metrics: judge response wasn't valid JSON; salvaged %d "
            "verdict(s) via per-object scan (likely truncated mid-stream)",
            len(salvaged),
        )
        return salvaged

    logger.warning(
        "draco.metrics: judge response yielded no parseable verdicts "
        "(len=%d, head: %r)",
        len(raw or ""),
        (raw or "")[:200],
    )
    return {}


def _extract_first_json_object(text: str) -> Optional[dict]:
    """Scan for the first balanced top-level JSON object and parse it.

    Tolerates preamble/postamble around the object, which is the common
    shape when a judge slips in commentary like "Here's my verdict:".
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _validate_verdict_objects(objs: list) -> dict[str, bool]:
    """Validate a list of would-be verdict dicts through `CriterionVerdict`,
    keeping every entry that validates and skipping the rest."""
    out: dict[str, bool] = {}
    for obj in objs:
        try:
            v = CriterionVerdict.model_validate(obj)
        except ValidationError:
            continue
        out[v.id] = v.met
    return out


def _scan_verdict_objects(text: str) -> dict[str, bool]:
    """Walk the text looking for every complete `{...}` object that
    carries both `id` and `met` keys and validates as a `CriterionVerdict`.

    Designed for **truncated** judge output — uses `JSONDecoder.raw_decode`
    starting at each `{`, advancing past whatever parsed and skipping past
    anything that didn't. Even when the outermost `{...}` is incomplete
    (no closing brace), we still recover every inner verdict object that
    landed before the cut-off. Salvaged objects are validated AFTER the
    salvage so partial recovery keeps working.
    """
    decoder = json.JSONDecoder()
    candidates: list = []
    i = 0
    while True:
        i = text.find("{", i)
        if i == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, i)
            if isinstance(obj, dict) and "id" in obj and "met" in obj:
                candidates.append(obj)
            i = max(end, i + 1)
        except json.JSONDecodeError:
            i += 1
    return _validate_verdict_objects(candidates)


# ---------------------------------------------------------------------------
# Public entry point: grade against a rubric, optionally across N runs
# ---------------------------------------------------------------------------


def _build_chunked_rubrics(
    rubric: dict, max_criteria_per_chunk: int = 10
) -> list[dict]:
    """Split a multi-section rubric into mini-rubrics, each with at most
    `max_criteria_per_chunk` criteria.

    Sections smaller than the cap go in one chunk; LARGER sections get
    split into sub-chunks that preserve the section id (so per-axis
    aggregation still routes the verdicts to the right axis downstream).

    Empirically, judge models — especially reasoning models like Gemini
    3.1 Pro that burn most of their token budget on hidden thinking —
    can only emit ~10-15 verdicts per call before truncating. Defaulting
    to 10 leaves comfortable headroom. Bump via `eval.judge_chunk_size`
    if you trust your judge with bigger batches.
    """
    cap = max(1, int(max_criteria_per_chunk))
    out: list[dict] = []
    for section in rubric.get("sections", []) or []:
        crits = section.get("criteria") or []
        if not crits:
            continue
        if len(crits) <= cap:
            out.append({"sections": [section]})
            continue
        # Split this section into sub-chunks, preserving its id/title so
        # axis_scores / axis_pass_rates aggregate correctly.
        for i in range(0, len(crits), cap):
            sub = {**section, "criteria": crits[i : i + cap]}
            out.append({"sections": [sub]})
    return out


def grade_against_rubric(
    *,
    question: str,
    model_answer: str,
    rubric_raw: Any,
    judge_fn,
    judge_runs: int = 1,
    judge_system: Optional[str] = None,
    judge_user_template: Optional[str] = None,
    chunk_by_section: bool = True,
    max_criteria_per_chunk: int = 10,
) -> dict:
    """Run the rubric judge `judge_runs` times and return averaged metrics.

    Returns a dict ready to merge into an eval JSONL row. `is_correct`
    is intentionally NOT among the keys — the paper defines no pass/fail
    threshold on normalized_score (see module-level note). Keys:
      confidence              float — equals normalized_score
      reasoning               str — one-liner summary with mean ± SD
      grading_method          "rubric"
      normalized_score        float — mean across successful runs
      pass_rate               float — mean across successful runs
      normalized_score_std    float — sd (0 if n=1)
      pass_rate_std           float
      axis_scores             dict[axis -> mean normalized score]
      verdicts                list — per-run {criterion_id: met} maps
      n_runs                  int — number of runs that produced parseable verdicts
      n_runs_requested        int — what was asked for
    """
    # Lazy imports so this module is testable without eval_arena present.
    if judge_system is None or judge_user_template is None:
        from benchmarking.prompts.rubric import JUDGE_SYSTEM, JUDGE_USER_TEMPLATE

        judge_system = judge_system or JUDGE_SYSTEM
        judge_user_template = judge_user_template or JUDGE_USER_TEMPLATE

    try:
        rubric = parse_rubric(rubric_raw)
    except Exception as exc:
        # Fail LOUD: a rubric that doesn't parse would otherwise grade
        # every row 0.0 while spending judge money. _eval_one re-raises
        # RubricShapeError so the run aborts on the first bad row.
        raise RubricShapeError(f"rubric parse failed: {exc}") from exc

    # Per-(model-answer) salt so any upstream cache (OpenRouter edge,
    # provider-side prompt cache, etc.) can't accidentally reuse one
    # answer's verdicts for a different answer. Cheap, deterministic.
    import hashlib as _hashlib

    answer_salt = _hashlib.md5(
        (model_answer or "").encode("utf-8", "replace")
    ).hexdigest()[:10]

    # Build the chunks to grade. When chunk_by_section=True (default),
    # we split into mini-rubrics of ≤ max_criteria_per_chunk criteria —
    # smaller per-call output → the judge can emit every verdict cleanly
    # without hitting the token cap.
    rubric_chunks = (
        _build_chunked_rubrics(rubric, max_criteria_per_chunk)
        if chunk_by_section
        else [rubric]
    )
    if not rubric_chunks:
        rubric_chunks = [rubric]  # fallback: one call, full rubric

    n_target = max(1, int(judge_runs))
    # Total criterion count from the rubric — denominator for coverage.
    total_criteria = len(_flatten_criteria(rubric))
    if total_criteria == 0:
        raise RubricShapeError(_zero_criteria_msg(rubric))
    per_run_norm: list[float] = []
    per_run_pass: list[float] = []
    per_run_verdicts: list[dict[str, bool]] = []
    per_run_axes: list[dict[str, float]] = []
    per_run_axis_pass: list[dict[str, float]] = []
    per_run_coverage: list[float] = []
    # One entry per requested run: {"run": idx, "summary": str, "raws":
    # [full raw judge reply per chunk, in order, un-truncated]}. Storing
    # the full replies (was previously truncated to 120 chars per chunk
    # and only the first 2 chunks kept) lets after-the-fact debugging
    # inspect exactly what the judge said on failure without re-running.
    judge_raw_samples: list[dict] = []

    for run_idx in range(n_target):
        # Accumulate verdicts across chunks for this run.
        run_verdicts: dict[str, bool] = {}
        run_raws: list[str] = []

        for chunk_idx, chunk_rubric in enumerate(rubric_chunks):
            chunk_user = judge_user_template.format(
                question=question,
                expected_answer=json.dumps(chunk_rubric, ensure_ascii=False),
                model_answer=model_answer,
            )
            # Salt: run id + chunk id + a hash of the model answer.
            # The model-answer hash prevents cross-row cache collisions
            # (different answers ⇒ different prompts ⇒ no cache hit).
            salted = (
                f"{chunk_user}\n\n[run={run_idx}][chunk={chunk_idx}][ans={answer_salt}]"
            )
            try:
                raw = judge_fn(judge_system, salted)
            except SpendGuardError:
                # Budget / call cap hit — abort the run; a swallowed
                # refusal would grade the row with zero verdicts and
                # persist it as completed.
                raise
            except Exception as exc:
                logger.warning(
                    "draco.metrics: judge failed on run %d chunk %d: %s",
                    run_idx,
                    chunk_idx,
                    exc,
                )
                run_raws.append(f"<exception chunk {chunk_idx}: {exc}>")
                continue
            if isinstance(raw, str):
                run_raws.append(raw)
            chunk_verdicts = parse_judge_response(raw)
            if chunk_verdicts:
                run_verdicts.update(chunk_verdicts)

        judge_raw_samples.append(
            {
                "run": run_idx,
                "summary": (
                    f"run={run_idx} chunks={len(rubric_chunks)} "
                    f"verdicts={len(run_verdicts)}/{total_criteria}"
                ),
                "raws": run_raws,
            }
        )

        if not run_verdicts:
            continue

        cov = len(run_verdicts) / total_criteria if total_criteria else 0.0
        if cov < 0.95 and total_criteria > 0:
            logger.warning(
                "draco.metrics: run %d still only graded %d/%d criteria "
                "(%.0f%% coverage) after %d chunk(s). Inspect "
                "`judge_raw_samples` on the row.",
                run_idx,
                len(run_verdicts),
                total_criteria,
                cov * 100,
                len(rubric_chunks),
            )
        per_run_norm.append(normalized_score(rubric, run_verdicts))
        per_run_pass.append(pass_rate(rubric, run_verdicts))
        per_run_verdicts.append(run_verdicts)
        per_run_axes.append(axis_scores(rubric, run_verdicts))
        per_run_axis_pass.append(axis_pass_rates(rubric, run_verdicts))
        per_run_coverage.append(cov)

    if not per_run_norm:
        return {
            "confidence": 0.0,
            "reasoning": "all judge runs failed to produce parseable verdicts",
            "grading_method": "rubric",
            "normalized_score": 0.0,
            "pass_rate": 0.0,
            "accuracy": 0.0,
            "accuracy_pass_rate": 0.0,
            "axis_scores": {},
            "axis_pass_rates": {},
            "verdicts": [],
            "verdict_coverage": 0.0,
            "verdict_coverage_std": 0.0,
            "judge_raw_samples": judge_raw_samples,
            "n_runs": 0,
            "n_runs_requested": n_target,
            "total_criteria": total_criteria,
        }

    mean_norm = mean(per_run_norm)
    mean_pass = mean(per_run_pass)
    mean_cov = mean(per_run_coverage) if per_run_coverage else 0.0
    all_axes = {a for axs in per_run_axes for a in axs}
    axis_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axes]), 4)
        for a in sorted(all_axes)
    }
    axis_pass_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axis_pass]), 4)
        for a in sorted({a for axs in per_run_axis_pass for a in axs})
    }

    # DRACO defines `accuracy` as the Factual Accuracy axis score, NOT a
    # binary derived from a threshold. The paper reports both the weighted
    # variant (axis normalized_score) and the unweighted pass-rate variant.
    accuracy = _factual_axis_value(axis_means)
    accuracy_pass_rate = _factual_axis_value(axis_pass_means)

    _norm_sd = stdev(per_run_norm) if len(per_run_norm) > 1 else 0.0
    _pass_sd = stdev(per_run_pass) if len(per_run_pass) > 1 else 0.0
    return {
        # Rubric grading has no meaningful pass/fail — DRACO does not
        # define a threshold, so `is_correct` is omitted entirely;
        # downstream should read `normalized_score` / `accuracy`
        # instead. See module-level note on PASS_THRESHOLD removal.
        "confidence": round(mean_norm, 4),
        "reasoning": (
            f"rubric[chunked]: normalized={mean_norm:.3f}±{_norm_sd:.3f}, "
            f"pass_rate={mean_pass:.3f}±{_pass_sd:.3f}, accuracy={accuracy:.3f}, "
            f"coverage={mean_cov:.2f} over {len(per_run_norm)}/{n_target} run(s)"
        ),
        "grading_method": "rubric",
        # Overall rubric scores (every criterion, all axes).
        "normalized_score": round(mean_norm, 4),
        "pass_rate": round(mean_pass, 4),
        "normalized_score_std": round(stdev(per_run_norm), 4)
        if len(per_run_norm) > 1
        else 0.0,
        "pass_rate_std": round(stdev(per_run_pass), 4)
        if len(per_run_pass) > 1
        else 0.0,
        # DRACO accuracy = factual-accuracy axis. Continuous in [0, 1].
        "accuracy": round(accuracy, 4),
        "accuracy_pass_rate": round(accuracy_pass_rate, 4),
        # Full per-axis breakdowns — paper reports all 4 axes.
        "axis_scores": axis_means,
        "axis_pass_rates": axis_pass_means,
        # Coverage + provenance.
        "verdict_coverage": round(mean_cov, 4),
        "verdict_coverage_std": round(stdev(per_run_coverage), 4)
        if len(per_run_coverage) > 1
        else 0.0,
        "verdicts": per_run_verdicts,
        "judge_raw_samples": judge_raw_samples,
        "n_runs": len(per_run_norm),
        "n_runs_requested": n_target,
        "total_criteria": total_criteria,
    }


# ── Async variant — parallelizes chunk × run judge calls ──────────────


async def grade_against_rubric_async(
    *,
    question: str,
    model_answer: str,
    rubric_raw: Any,
    judge_fn_async,  # async (system, user) -> str
    judge_runs: int = 1,
    judge_system: Optional[str] = None,
    judge_user_template: Optional[str] = None,
    chunk_by_section: bool = True,
    max_criteria_per_chunk: int = 10,
    on_progress=None,  # callable(msg) → None, level-1 progress hook
) -> dict:
    """Async version of `grade_against_rubric` — same return shape, but
    fans out all (run × chunk) judge calls concurrently via
    `asyncio.gather` instead of iterating sequentially.

    Result-aggregation logic is identical to the sync version; only the
    judge-call loop is parallelised. For DRACO's 7 chunks × 3 runs = 21
    calls, wall clock drops from ~21×judge_latency to ~1×judge_latency
    (bounded by the slowest single call + the connection concurrency
    limit on the underlying HTTP client).
    """
    import asyncio
    import hashlib as _hashlib

    if judge_system is None or judge_user_template is None:
        from benchmarking.prompts.rubric import JUDGE_SYSTEM, JUDGE_USER_TEMPLATE

        judge_system = judge_system or JUDGE_SYSTEM
        judge_user_template = judge_user_template or JUDGE_USER_TEMPLATE

    try:
        rubric = parse_rubric(rubric_raw)
    except Exception as exc:
        # Fail LOUD: a rubric that doesn't parse would otherwise grade
        # every row 0.0 while spending judge money. _eval_one re-raises
        # RubricShapeError so the run aborts on the first bad row.
        raise RubricShapeError(f"rubric parse failed: {exc}") from exc

    answer_salt = _hashlib.md5(
        (model_answer or "").encode("utf-8", "replace")
    ).hexdigest()[:10]

    rubric_chunks = (
        _build_chunked_rubrics(rubric, max_criteria_per_chunk)
        if chunk_by_section
        else [rubric]
    )
    if not rubric_chunks:
        rubric_chunks = [rubric]

    n_target = max(1, int(judge_runs))
    total_criteria = len(_flatten_criteria(rubric))
    if total_criteria == 0:
        raise RubricShapeError(_zero_criteria_msg(rubric))

    # Build every (run, chunk) task upfront, then fire them all in
    # parallel. `gather(*, return_exceptions=True)` so one broken call
    # doesn't sink the whole row.
    import time as _t

    async def _one_call(
        run_idx: int, chunk_idx: int, chunk_rubric: dict
    ) -> tuple[int, int, str | Exception]:
        chunk_user = judge_user_template.format(
            question=question,
            expected_answer=json.dumps(chunk_rubric, ensure_ascii=False),
            model_answer=model_answer,
        )
        salted = (
            f"{chunk_user}\n\n[run={run_idx}][chunk={chunk_idx}][ans={answer_salt}]"
        )
        t0 = _t.perf_counter()
        try:
            raw = await judge_fn_async(judge_system, salted)
            if on_progress:
                on_progress(
                    f"      chunk r{run_idx}c{chunk_idx}: ✓ {(_t.perf_counter() - t0):.1f}s"
                )
            return run_idx, chunk_idx, raw
        except SpendGuardError:
            # Budget / call cap hit — propagate through asyncio.gather so
            # the run aborts instead of grading this row with a missing
            # chunk.
            raise
        except Exception as exc:
            logger.warning(
                "draco.metrics: judge failed on run %d chunk %d: %s",
                run_idx,
                chunk_idx,
                exc,
            )
            if on_progress:
                on_progress(
                    f"      chunk r{run_idx}c{chunk_idx}: ✗ FAILED ({(_t.perf_counter() - t0):.1f}s)"
                )
            return run_idx, chunk_idx, exc

    if on_progress:
        on_progress(
            f"      firing {n_target * len(rubric_chunks)} judge calls "
            f"({n_target} run(s) × {len(rubric_chunks)} chunk(s)) in parallel"
        )
    tasks = [
        _one_call(r, c, chunk)
        for r in range(n_target)
        for c, chunk in enumerate(rubric_chunks)
    ]
    results = await asyncio.gather(*tasks)

    # Bucket verdicts back by run_idx so the aggregation loop below is
    # a drop-in match for the sync version's structure.
    per_run_verdicts_acc: list[dict[str, bool]] = [dict() for _ in range(n_target)]
    per_run_raws: list[list[str]] = [list() for _ in range(n_target)]
    for run_idx, chunk_idx, raw_or_exc in results:
        if isinstance(raw_or_exc, Exception):
            per_run_raws[run_idx].append(f"<exception chunk {chunk_idx}: {raw_or_exc}>")
            continue
        if isinstance(raw_or_exc, str):
            per_run_raws[run_idx].append(raw_or_exc)
        chunk_verdicts = parse_judge_response(raw_or_exc)
        if chunk_verdicts:
            per_run_verdicts_acc[run_idx].update(chunk_verdicts)

    # ── Reuse the sync path's downstream aggregation (identical) ────
    per_run_norm: list[float] = []
    per_run_pass: list[float] = []
    per_run_verdicts: list[dict[str, bool]] = []
    per_run_axes: list[dict[str, float]] = []
    per_run_axis_pass: list[dict[str, float]] = []
    per_run_coverage: list[float] = []
    judge_raw_samples: list[dict] = []  # see sync path for shape

    for run_idx in range(n_target):
        run_verdicts = per_run_verdicts_acc[run_idx]
        run_raws = per_run_raws[run_idx]
        judge_raw_samples.append(
            {
                "run": run_idx,
                "summary": (
                    f"run={run_idx} chunks={len(rubric_chunks)} "
                    f"verdicts={len(run_verdicts)}/{total_criteria}"
                ),
                "raws": run_raws,
            }
        )
        if not run_verdicts:
            continue
        cov = len(run_verdicts) / total_criteria if total_criteria else 0.0
        if cov < 0.95 and total_criteria > 0:
            logger.warning(
                "draco.metrics: run %d still only graded %d/%d criteria "
                "(%.0f%% coverage) after %d chunk(s).",
                run_idx,
                len(run_verdicts),
                total_criteria,
                cov * 100,
                len(rubric_chunks),
            )
        per_run_norm.append(normalized_score(rubric, run_verdicts))
        per_run_pass.append(pass_rate(rubric, run_verdicts))
        per_run_verdicts.append(run_verdicts)
        per_run_axes.append(axis_scores(rubric, run_verdicts))
        per_run_axis_pass.append(axis_pass_rates(rubric, run_verdicts))
        per_run_coverage.append(cov)

    if not per_run_norm:
        return {
            "confidence": 0.0,
            "reasoning": "all judge runs failed to produce parseable verdicts",
            "grading_method": "rubric",
            "normalized_score": 0.0,
            "pass_rate": 0.0,
            "accuracy": 0.0,
            "accuracy_pass_rate": 0.0,
            "axis_scores": {},
            "axis_pass_rates": {},
            "verdicts": [],
            "verdict_coverage": 0.0,
            "verdict_coverage_std": 0.0,
            "judge_raw_samples": judge_raw_samples,
            "n_runs": 0,
            "n_runs_requested": n_target,
            "total_criteria": total_criteria,
        }

    mean_norm = mean(per_run_norm)
    mean_pass = mean(per_run_pass)
    mean_cov = mean(per_run_coverage) if per_run_coverage else 0.0
    axis_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axes]), 4)
        for a in sorted({a for axs in per_run_axes for a in axs})
    }
    axis_pass_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axis_pass]), 4)
        for a in sorted({a for axs in per_run_axis_pass for a in axs})
    }
    accuracy = _factual_axis_value(axis_means)
    accuracy_pass_rate = _factual_axis_value(axis_pass_means)

    _norm_sd = stdev(per_run_norm) if len(per_run_norm) > 1 else 0.0
    _pass_sd = stdev(per_run_pass) if len(per_run_pass) > 1 else 0.0
    return {
        # Rubric grading has no meaningful pass/fail. See module note.
        "confidence": round(mean_norm, 4),
        "reasoning": (
            f"rubric[chunked-async]: normalized={mean_norm:.3f}±{_norm_sd:.3f}, "
            f"pass_rate={mean_pass:.3f}±{_pass_sd:.3f}, accuracy={accuracy:.3f}, "
            f"coverage={mean_cov:.2f} over {len(per_run_norm)}/{n_target} run(s)"
        ),
        "grading_method": "rubric",
        "normalized_score": round(mean_norm, 4),
        "pass_rate": round(mean_pass, 4),
        "normalized_score_std": round(_norm_sd, 4) if len(per_run_norm) > 1 else 0.0,
        "pass_rate_std": round(_pass_sd, 4) if len(per_run_pass) > 1 else 0.0,
        "accuracy": round(accuracy, 4),
        "accuracy_pass_rate": round(accuracy_pass_rate, 4),
        "axis_scores": axis_means,
        "axis_pass_rates": axis_pass_means,
        "verdict_coverage": round(mean_cov, 4),
        "verdict_coverage_std": round(stdev(per_run_coverage), 4)
        if len(per_run_coverage) > 1
        else 0.0,
        "verdicts": per_run_verdicts,
        "judge_raw_samples": judge_raw_samples,
        "n_runs": len(per_run_norm),
        "n_runs_requested": n_target,
        "total_criteria": total_criteria,
    }


# ---------------------------------------------------------------------------
# Per-criterion (official DRACO) grader
# ---------------------------------------------------------------------------
# Fires ONE judge call per criterion, N times independently (judge_runs).
# Matches github.com/The-LLM-Data-Company/rubric's PerCriterionGrader.judge()
# semantics: rubric is flattened, criterion_type is derived from weight
# sign, each call is validated as `PerCriterionOutput` (Pydantic), all
# (run × criterion) calls are dispatched via a single asyncio.gather so
# wall-clock ~ 1 × judge_latency (bounded by connection pool).
#
# Cost: per row ≈ (n_criteria × judge_runs) calls. For DRACO's ~40-criterion
# rubrics × judge_runs=5 that's ~200 judge calls per (row, model). Multiply
# by n_models and n_rows to size a spend estimate before running at scale.


def _parse_per_criterion_output(raw: str) -> Optional[PerCriterionOutput]:
    """Strict Pydantic parse of a per-criterion judge reply.

    The paper's Appendix C.5 tells the judge to emit "only raw JSON starting
    with {" — so on the happy path `json.loads(raw)` + Pydantic works. In
    practice models occasionally slip a preamble in front or wrap the JSON
    in ```json fences; we lightly unwrap both before validating. Return
    None (and warn) when the reply can't be coerced into the schema at all.
    """
    if not raw:
        return None
    text = raw.strip()
    # Strip ```json / ``` fences if the judge wrapped its output.
    if "```" in text:
        text = "\n".join(
            ln for ln in text.splitlines() if not ln.strip().startswith("```")
        ).strip()
    # Fast path: whole string is the JSON object.
    for candidate in (text, _extract_first_json_object(text)):
        if candidate is None:
            continue
        try:
            if isinstance(candidate, str):
                return PerCriterionOutput.model_validate_json(candidate)
            return PerCriterionOutput.model_validate(candidate)
        except (ValidationError, json.JSONDecodeError):
            continue
    logger.warning(
        "draco.rubric: per-criterion judge reply failed Pydantic validation "
        "(len=%d, head: %r)",
        len(raw or ""),
        (raw or "")[:200],
    )
    return None


async def grade_against_rubric_per_criterion_async(
    *,
    question: str,
    model_answer: str,
    rubric_raw: Any,
    judge_fn_async,
    judge_runs: int = 5,
    judge_system: Optional[str] = None,
    judge_user_template: Optional[str] = None,
    on_progress=None,
) -> dict:
    """Paper-aligned rubric grading — one judge call per criterion, N runs.

    Same return shape as `grade_against_rubric_async` so the downstream
    stats hooks (`normalized_score`, `pass_rate`, `axis_scores`, …) don't
    care which mode produced the verdicts. What's different vs chunked:

      - Judge sees ONE criterion per call, never the full rubric.
      - Judge never sees the criterion's weight (only its `requirement`
        and `criterion_type` ∈ {positive, negative}). Weights are used
        only in-code during aggregation.
      - Output is Pydantic-validated as PerCriterionOutput; a call that
        fails validation contributes no verdict for that criterion.
      - `n_runs` matches the paper's 5 for mean ± SD.
    """
    import asyncio
    import time as _t

    if judge_system is None or judge_user_template is None:
        from benchmarking.prompts.rubric import (
            PER_CRITERION_JUDGE_SYSTEM,
            PER_CRITERION_USER_TEMPLATE,
        )

        judge_system = judge_system or PER_CRITERION_JUDGE_SYSTEM
        judge_user_template = judge_user_template or PER_CRITERION_USER_TEMPLATE

    try:
        rubric = parse_rubric(rubric_raw)
    except Exception as exc:
        # Fail LOUD — see the chunked path's parse guard for rationale.
        raise RubricShapeError(f"rubric parse failed: {exc}") from exc

    criteria = _flatten_criteria(rubric)
    total_criteria = len(criteria)
    if total_criteria == 0:
        raise RubricShapeError(_zero_criteria_msg(rubric))

    # Harness parity: emit <query>...</query> only when the question
    # is truthy — matches per_criterion_grader.py's
    #   query_text = f"<query>{query}</query>" if query else ""
    query_block = f"<query>{question}</query>" if question else ""
    n_target = max(1, int(judge_runs))
    judge_sem = _judge_call_semaphore()

    async def _one_criterion(
        run_idx: int, crit_idx: int, criterion: dict
    ) -> tuple[int, int, Optional[PerCriterionOutput], Optional[str]]:
        weight = float(criterion.get("weight", 0))
        criterion_type = "negative" if weight < 0 else "positive"
        # Prompt is byte-identical to the harness. No salt, no retry
        # nudge — variance across the N runs comes from temperature > 0
        # sampling (paper pins temp=0.2), which is what the harness
        # itself relies on. Any extra text here is paper-protocol drift.
        user = judge_user_template.format(
            criterion_type=criterion_type,
            criterion_requirement=criterion.get("requirement", ""),
            query_block=query_block,
            model_answer=model_answer or "",
        )
        t0 = _t.perf_counter()
        last_raw: Optional[str] = None
        # Total attempts = 1 initial + PER_CRITERION_VALIDATION_RETRIES.
        # Retry with the SAME user prompt — harness contract expects
        # clients to retry validation failures, but the paper's judge
        # never saw any retry-specific nudge and neither will ours.
        # Transient HTTP errors are already retried inside allm_generate;
        # this loop only handles the JSON-shape failure mode.
        for attempt in range(1 + PER_CRITERION_VALIDATION_RETRIES):
            try:
                async with judge_sem:
                    raw = await judge_fn_async(judge_system, user)
            except SpendGuardError:
                # Budget / call cap hit — propagate through asyncio.gather
                # so the run aborts instead of silently failing this
                # criterion and corrupting the row's partial score.
                raise
            except Exception as exc:
                logger.warning(
                    "draco.rubric: judge failed on run %d criterion %d (%s): %s",
                    run_idx,
                    crit_idx,
                    criterion.get("id"),
                    exc,
                )
                if on_progress:
                    on_progress(
                        f"      crit r{run_idx}c{crit_idx}: ✗ FAILED "
                        f"({(_t.perf_counter() - t0):.1f}s)"
                    )
                return run_idx, crit_idx, None, None
            last_raw = raw
            parsed = _parse_per_criterion_output(raw)
            if parsed is not None:
                if on_progress:
                    marker = "✓" if attempt == 0 else f"✓ (retry {attempt})"
                    on_progress(
                        f"      crit r{run_idx}c{crit_idx}: {marker} "
                        f"({(_t.perf_counter() - t0):.1f}s)"
                    )
                return run_idx, crit_idx, parsed, raw
        # All attempts failed validation. Drop the verdict — the
        # criterion is excluded from this run's score denominators
        # (harness aggregate() computes weights over the reports it
        # receives, so an unjudged criterion drops out of both sides).
        if on_progress:
            on_progress(
                f"      crit r{run_idx}c{crit_idx}: ✗ INVALID after "
                f"{PER_CRITERION_VALIDATION_RETRIES + 1} attempts "
                f"({(_t.perf_counter() - t0):.1f}s)"
            )
        return run_idx, crit_idx, None, last_raw

    if on_progress:
        on_progress(
            f"      firing {n_target * total_criteria} per-criterion judge calls "
            f"({n_target} run(s) × {total_criteria} criteria) in parallel"
        )
    tasks = [
        _one_criterion(r, ci, crit)
        for r in range(n_target)
        for ci, crit in enumerate(criteria)
    ]
    results = await asyncio.gather(*tasks)

    # Bucket verdicts back into per-run dicts keyed by criterion id.
    per_run_verdicts_acc: list[dict[str, bool]] = [dict() for _ in range(n_target)]
    per_run_raws: list[list[str]] = [list() for _ in range(n_target)]
    for run_idx, crit_idx, parsed, raw in results:
        if raw is not None:
            per_run_raws[run_idx].append(raw)
        if parsed is None:
            continue
        crit = criteria[crit_idx]
        met_bool = parsed.criterion_status == "MET"
        per_run_verdicts_acc[run_idx][crit["id"]] = met_bool

    # ── Aggregate per-run (identical shape to chunked path) ─────────────
    per_run_norm: list[float] = []
    per_run_pass: list[float] = []
    per_run_verdicts: list[dict[str, bool]] = []
    per_run_axes: list[dict[str, float]] = []
    per_run_axis_pass: list[dict[str, float]] = []
    per_run_coverage: list[float] = []
    # See sync grade_against_rubric for the {"run", "summary", "raws"} shape.
    judge_raw_samples: list[dict] = []

    for run_idx in range(n_target):
        rv = per_run_verdicts_acc[run_idx]
        run_raws = per_run_raws[run_idx]
        judge_raw_samples.append(
            {
                "run": run_idx,
                "summary": (
                    f"run={run_idx} criteria={total_criteria} verdicts={len(rv)}"
                ),
                "raws": run_raws,
            }
        )
        if not rv:
            continue
        cov = len(rv) / total_criteria if total_criteria else 0.0
        run_rubric = rubric
        if len(rv) < total_criteria:
            run_rubric = _restrict_rubric(rubric, set(rv))
        if cov < 0.95 and total_criteria > 0:
            logger.warning(
                "draco.rubric: run %d only graded %d/%d criteria (%.0f%% coverage) "
                "under per-criterion mode. Ungraded criteria are excluded from "
                "this run's score denominators (harness aggregate() parity); "
                "investigate judge parse failures.",
                run_idx,
                len(rv),
                total_criteria,
                cov * 100,
            )
        per_run_norm.append(normalized_score(run_rubric, rv))
        per_run_pass.append(pass_rate(run_rubric, rv))
        per_run_verdicts.append(rv)
        per_run_axes.append(axis_scores(run_rubric, rv))
        per_run_axis_pass.append(axis_pass_rates(run_rubric, rv))
        per_run_coverage.append(cov)

    if not per_run_norm:
        return {
            "confidence": 0.0,
            "reasoning": "all per-criterion runs failed validation",
            "grading_method": "rubric_per_criterion",
            "normalized_score": 0.0,
            "pass_rate": 0.0,
            "accuracy": 0.0,
            "accuracy_pass_rate": 0.0,
            "axis_scores": {},
            "axis_pass_rates": {},
            "verdicts": [],
            "verdict_coverage": 0.0,
            "verdict_coverage_std": 0.0,
            "judge_raw_samples": judge_raw_samples,
            "n_runs": 0,
            "n_runs_requested": n_target,
            "total_criteria": total_criteria,
        }

    mean_norm = mean(per_run_norm)
    mean_pass = mean(per_run_pass)
    mean_cov = mean(per_run_coverage) if per_run_coverage else 0.0
    axis_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axes]), 4)
        for a in sorted({a for axs in per_run_axes for a in axs})
    }
    axis_pass_means = {
        a: round(mean([axs.get(a, 0.0) for axs in per_run_axis_pass]), 4)
        for a in sorted({a for axs in per_run_axis_pass for a in axs})
    }
    accuracy = _factual_axis_value(axis_means)
    accuracy_pass_rate = _factual_axis_value(axis_pass_means)

    _norm_sd = stdev(per_run_norm) if len(per_run_norm) > 1 else 0.0
    _pass_sd = stdev(per_run_pass) if len(per_run_pass) > 1 else 0.0
    return {
        # Rubric grading has no meaningful pass/fail. See module note.
        "confidence": round(mean_norm, 4),
        "reasoning": (
            f"rubric[per_criterion]: normalized={mean_norm:.3f}±{_norm_sd:.3f}, "
            f"pass_rate={mean_pass:.3f}±{_pass_sd:.3f}, accuracy={accuracy:.3f}, "
            f"coverage={mean_cov:.2f} over {len(per_run_norm)}/{n_target} run(s)"
        ),
        "grading_method": "rubric_per_criterion",
        "normalized_score": round(mean_norm, 4),
        "pass_rate": round(mean_pass, 4),
        "normalized_score_std": round(_norm_sd, 4) if len(per_run_norm) > 1 else 0.0,
        "pass_rate_std": round(_pass_sd, 4) if len(per_run_pass) > 1 else 0.0,
        "accuracy": round(accuracy, 4),
        "accuracy_pass_rate": round(accuracy_pass_rate, 4),
        "axis_scores": axis_means,
        "axis_pass_rates": axis_pass_means,
        "verdict_coverage": round(mean_cov, 4),
        "verdict_coverage_std": round(stdev(per_run_coverage), 4)
        if len(per_run_coverage) > 1
        else 0.0,
        "verdicts": per_run_verdicts,
        "judge_raw_samples": judge_raw_samples,
        "n_runs": len(per_run_norm),
        "n_runs_requested": n_target,
        "total_criteria": total_criteria,
    }


# ---------------------------------------------------------------------------
# Grader module surface — Phase 3+4+5 hooks that dispatched from
# `benchmarking.graders.__init__.get_grader("rubric")`
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_eval_config() -> dict:
    """Load the active benchmark's `eval` config block, once per process.

    Memoized: `load_config` re-reads and re-validates the YAML files on
    every call, and grade-time resolvers would otherwise run it per
    (row, model) on the event loop. One process grades one benchmark, so
    caching is safe; call `_load_eval_config.cache_clear()` in tests.
    """
    import os as _os

    from config import load_config as _load_config

    benchmark = _os.environ.get("SCREAMINGFACE_BENCHMARK")
    if not benchmark:
        logger.warning(
            "draco.rubric: SCREAMINGFACE_BENCHMARK is not set — benchmark-specific "
            "eval settings (grading_mode, judge_chunk_size) fall back to the "
            "global config."
        )
    return _load_config(benchmark=benchmark).get("eval") or {}


def _resolve_grading_mode() -> str:
    """Read `eval.grading_mode` from the active benchmark's config.

    Returns "official" (per-criterion, paper-aligned; default) or
    "chunked" (the old cheap mode that batches criteria per call).
    Misconfiguration is loud: the two modes differ ~n_criteria× in judge
    spend, so a typo'd value or an unreadable config must not flip the
    mode silently.
    """
    try:
        mode_raw = _load_eval_config().get("grading_mode")
    except Exception as exc:
        logger.warning(
            "draco.rubric: failed to read eval.grading_mode (%s) — defaulting "
            "to 'official' (per-criterion; ~n_criteria × judge_runs judge "
            "calls per row).",
            exc,
        )
        return "official"

    mode = str(mode_raw or "").strip().lower()
    if mode in ("official", "per_criterion", "paper"):
        return "official"
    if mode in ("chunked", "cheap", "batch"):
        return "chunked"
    if mode:
        logger.warning(
            "draco.rubric: unrecognized eval.grading_mode=%r — defaulting to "
            "'official' (per-criterion; ~n_criteria × judge_runs judge calls "
            "per row). Valid values: 'official', 'chunked'.",
            mode_raw,
        )
    return "official"


def _resolve_chunk_size() -> int:
    """Read `eval.judge_chunk_size` from the active benchmark's config,
    falling back to 10. Called at grade time so the knob can be edited
    without touching this file."""
    try:
        _eval = _load_eval_config()
        if _eval.get("judge_chunk_size"):
            return int(_eval["judge_chunk_size"])
    except Exception:
        pass
    return 10


def grade(
    *, question, expected_answer, model_answer, judge_fn, qa_pair, judge_runs: int = 1
) -> dict:
    """Sync rubric grading — one call per (run, chunk), sequential."""
    return grade_against_rubric(
        question=question,
        model_answer=model_answer,
        rubric_raw=expected_answer,
        judge_fn=judge_fn,
        judge_runs=judge_runs,
        chunk_by_section=True,
        max_criteria_per_chunk=_resolve_chunk_size(),
    )


async def grade_async(
    *,
    question,
    expected_answer,
    model_answer,
    judge_fn,
    judge_fn_async=None,
    qa_pair,
    judge_runs: int = 1,
    on_progress=None,
) -> dict:
    """Async rubric grading — dispatches on `eval.grading_mode`.

      "official"  → per-criterion mode (paper-aligned; ~n_criteria × runs
                    calls per row). Default.
      "chunked"   → old chunked mode (~ceil(n_criteria/chunk_size) × runs
                    calls per row). Cheaper but NOT the paper's protocol.

    Both paths parallelise every call via asyncio.gather when an async
    judge is provided; falls back to the sync chunked path in a thread
    if the caller only supplied a sync `judge_fn`.
    """
    mode = _resolve_grading_mode()

    if judge_fn_async is None:
        # No async judge → fall back to sync chunked path in a thread.
        # (Per-criterion mode has no sync entry — it's designed around
        # gather; wrap the sync path if you specifically need it.)
        if mode == "official":
            logger.warning(
                "draco.rubric: grading_mode='official' requested but caller "
                "only supplied sync judge_fn — falling back to chunked path. "
                "Wire judge_fn_async to run per-criterion."
            )
        import asyncio

        return await asyncio.to_thread(
            grade,
            question=question,
            expected_answer=expected_answer,
            model_answer=model_answer,
            judge_fn=judge_fn,
            qa_pair=qa_pair,
            judge_runs=judge_runs,
        )

    if mode == "official":
        return await grade_against_rubric_per_criterion_async(
            question=question,
            model_answer=model_answer,
            rubric_raw=expected_answer,
            judge_fn_async=judge_fn_async,
            judge_runs=judge_runs,
            on_progress=on_progress,
        )

    return await grade_against_rubric_async(
        question=question,
        model_answer=model_answer,
        rubric_raw=expected_answer,
        judge_fn_async=judge_fn_async,
        judge_runs=judge_runs,
        chunk_by_section=True,
        max_criteria_per_chunk=_resolve_chunk_size(),
        on_progress=on_progress,
    )


# ---------------------------------------------------------------------------
# Phase 4 (Stats) hooks
# ---------------------------------------------------------------------------


def compute_row_metrics(group) -> dict:
    """DRACO headline metrics per rubric-graded slice.

      normalized_score   overall weighted score across the WHOLE rubric.
      pass_rate          overall unweighted fraction correctly handled.
      accuracy           normalized_score restricted to the Factual
                          Accuracy axis (the paper's `accuracy` metric —
                          continuous, weight-aware, NOT a threshold).
      accuracy_pass_rate unweighted version of accuracy.
      verdict_coverage   % of rubric criteria the judge actually graded.
                          Low coverage drags scores down even on good
                          responses, so it's surfaced for debug.

    Skips abstention/hallucination/SMI — those don't carry meaning for
    rubric-graded tasks.
    """
    import pandas as pd

    total = len(group)
    if total == 0:
        return {
            "total": 0,
            "accuracy": 0.0,
            "accuracy_std": 0.0,
            "accuracy_pass_rate": 0.0,
            "normalized_score": 0.0,
            "normalized_score_std": 0.0,
            "pass_rate": 0.0,
            "pass_rate_std": 0.0,
            "verdict_coverage": 0.0,
        }

    def _num(col: str):
        return pd.to_numeric(
            group.get(col, pd.Series(dtype=float)), errors="coerce"
        ).dropna()

    ns = _num("normalized_score")
    pr = _num("pass_rate")
    acc = _num("accuracy")
    accp = _num("accuracy_pass_rate")
    cov = _num("verdict_coverage")
    return {
        "total": total,
        "accuracy": round(float(acc.mean()), 4) if len(acc) else 0.0,
        "accuracy_std": round(float(acc.std()), 4) if len(acc) > 1 else 0.0,
        "accuracy_pass_rate": round(float(accp.mean()), 4) if len(accp) else 0.0,
        "normalized_score": round(float(ns.mean()), 4) if len(ns) else 0.0,
        "normalized_score_std": round(float(ns.std()), 4) if len(ns) > 1 else 0.0,
        "pass_rate": round(float(pr.mean()), 4) if len(pr) else 0.0,
        "pass_rate_std": round(float(pr.std()), 4) if len(pr) > 1 else 0.0,
        "verdict_coverage": round(float(cov.mean()), 4) if len(cov) else 0.0,
    }


def compute_extra_breakdowns(df, out_dir) -> dict:
    """Per-rubric-axis breakdowns: one column per axis, one row per model / judge."""
    import json as _json
    from pathlib import Path as _Path

    import pandas as pd

    if df.empty or "axis_scores" not in df.columns:
        return {}

    def _to_dict(v):
        if isinstance(v, dict):
            return v
        if isinstance(v, str) and v.strip():
            try:
                return _json.loads(v)
            except (_json.JSONDecodeError, TypeError):
                return {}
        return {}

    parsed = df["axis_scores"].map(_to_dict)
    all_axes = sorted({a for d in parsed for a in d})
    if not all_axes:
        return {}

    df = df.copy()
    for ax in all_axes:
        df[f"_axis_{ax}"] = parsed.map(lambda d, ax=ax: d.get(ax, float("nan")))

    out_dir = _Path(out_dir)
    written: dict[str, _Path] = {}

    def _by(key_col: str, out_name: str) -> None:
        if key_col not in df.columns:
            return
        rows = []
        for key, g in df.groupby(key_col, dropna=False):
            row = {key_col: key, "total": len(g)}
            for ax in all_axes:
                vals = pd.to_numeric(g[f"_axis_{ax}"], errors="coerce").dropna()
                row[ax] = round(float(vals.mean()), 4) if len(vals) else 0.0
            rows.append(row)
        frame = pd.DataFrame(rows).sort_values(key_col).reset_index(drop=True)
        if frame.empty:
            return
        path = out_dir / f"{out_name}.csv"
        frame.to_csv(path, index=False)
        written[out_name] = path

    _by("model", "by_model_axis")
    _by("judge_model", "by_judge_axis")
    return written


def plot_metric_columns() -> list[str]:
    """Bar-chart columns Phase 5 should render for rubric-graded rows."""
    return ["normalized_score", "pass_rate", "accuracy"]


def has_stacked_response_breakdown() -> bool:
    """No correct/abstain/hallucinate stacked plot for rubric grading —
    the judge doesn't produce those categories."""
    return False


def simulate(
    cfg,
    *,
    avg_tokens,
    pricing,
    overrides=None,
    k_calibration=None,
    max_tokens=4096,
    ceiling=False,
):
    """DRACO call accounting:
    Phase 2  : zero LLM calls (pure JSON reshape).
    Phase 3  : per row,
        - 1 model-answer call per `eval.models` entry
        - sum(len(panel)) + 1 (synth) calls per `eval.fusions` entry
        - judge calls per eval row × n_judges, depending on
          `eval.grading_mode`:
            official (default) — rubric_criteria × judge_runs
            chunked            — ceil(rubric_criteria / judge_chunk_size)
                                 × judge_runs

    `ceiling=True` = worst-case bound: every call's output at the cap
    the production call site actually sends, and every prompt that
    embeds a model answer priced with that answer maxed (judge reads
    the answer — for fusion rows the longer SYNTH answer; synth reads
    every panel answer). Caps come from `ceiling_token_caps` so the
    policy is shared with the generic simulator. Call counts are
    identical in both modes.
    """
    import math

    from runners.phases.run_costs import (
        DEFAULT_AVG_TOKENS,
        _add,
        _cost_for,
        _new_bucket,
        _round,
        ceiling_token_caps,
    )

    overrides = overrides or {}
    ec = cfg.get("eval", {}) or {}
    dc = cfg.get("datasets", {}) or {}

    ds_limit = dc.get("limit")
    ev_limit = overrides.get("eval_limit", ec.get("limit"))
    fallback = 100  # DRACO test split
    if ds_limit and ev_limit:
        rows = min(ds_limit, ev_limit)
    elif ev_limit:
        rows = ev_limit
    elif ds_limit:
        rows = ds_limit
    else:
        rows = fallback
    rows = overrides.get("articles", rows)
    # `eval_rows` pins the row count directly — the dry-run guidance
    # passes the probe's MEASURED dataset size so the ceiling covers
    # the full run even when config carries probe/smoke limits
    # (draco.yaml ships `eval.limit: 1`).
    rows = int(overrides.get("eval_rows") or rows)

    from config import eval_lineup_models

    # The sim must count the full lineup — `models:` alone drops the HF
    # side of a two-list transport split (openrouter_/huggingface_models).
    eval_models = overrides.get("eval_models", eval_lineup_models(ec))
    fusions = overrides.get("fusions", ec.get("fusions") or [])
    judges = overrides.get("judges", ec.get("judge_models") or [])
    judge_runs = int(overrides.get("judge_runs", ec.get("judge_runs") or 1))
    chunk_size = int(
        overrides.get("judge_chunk_size", ec.get("judge_chunk_size") or 10)
    )

    n_models = len(eval_models)
    n_fusions = len(fusions)
    n_judges = len(judges) or 1

    avg_criteria = int(overrides.get("avg_criteria_per_task", 53))

    # Judge-call accounting must mirror the active grading mode (same
    # normalization + "official" default as `_resolve_grading_mode`):
    #   official — one judge call per criterion per run (§4.2 of the
    #              paper); each reply is a single tiny verdict JSON.
    #   chunked  — ceil(criteria / chunk_size) calls per run; each reply
    #              carries ~25 output tokens per criterion in the chunk.
    _mode_raw = (
        str(overrides.get("grading_mode", ec.get("grading_mode")) or "").strip().lower()
    )
    grading_mode = (
        "chunked" if _mode_raw in ("chunked", "cheap", "batch") else "official"
    )
    per_criterion_judge_out = 64  # tokens: one verdict JSON reply
    if grading_mode == "official":
        judge_calls_per_run = avg_criteria
    else:
        judge_calls_per_run = max(1, math.ceil(avg_criteria / max(1, chunk_size)))

    model_answer_calls = rows * n_models
    fusion_panel_calls = rows * sum(len(f.get("panel") or []) for f in fusions)
    fusion_synth_calls = rows * n_fusions
    n_eval_entries = n_models + n_fusions
    judge_calls_per_eval_row = judge_calls_per_run * judge_runs
    judge_calls = rows * n_eval_entries * n_judges * judge_calls_per_eval_row

    a_in, a_out = avg_tokens.get("eval.answer", DEFAULT_AVG_TOKENS["eval.answer"])
    j_in = a_in
    j_out = (
        per_criterion_judge_out
        if grading_mode == "official"
        else max(64, chunk_size * 25)
    )
    # Synth replies run longer than solo answers (they merge a panel).
    synth_out = int(a_out * 1.5)
    # Fusion-row judges read the SYNTH answer (longer cap than a solo
    # answer); synth prompts embed every panel answer. Both stay at the
    # calibrated average in expected mode and go to their caps under
    # ceiling — the worst case IS every answer maxed out.
    fj_in = j_in
    synth_in_extra = 0
    if ceiling:
        caps = ceiling_token_caps(cfg, a_in)
        a_out = caps["answer_out"]
        synth_out = caps["synth_out"]
        j_in = caps["judge_in"]
        j_out = caps["judge_out"]
        fj_in = caps["judge_in_synth"]
        synth_in_extra = caps["synth_in_extra"]

    by_model: dict[str, dict] = {}
    by_stage: dict[str, dict] = {}
    by_fusion: dict[str, dict] = {}
    by_lineup: dict[str, dict] = {}

    def _bump(buckets, key, calls, t_in, t_out, price_model):
        if not key or calls == 0:
            return
        # Simulation models no reasoning tokens or web-search calls, so
        # the reasoning/tools components are always 0.0 here.
        ic, oc, _rc, _tc, _found = _cost_for(price_model, t_in, t_out, pricing)
        b = buckets.setdefault(key, _new_bucket())
        _add(b, calls, t_in, t_out, ic, oc)

    def _cost(price_model, t_in, t_out):
        ic, oc, _rc, _tc, _found = _cost_for(price_model, t_in, t_out, pricing)
        return ic, oc

    if n_judges > 0 and judge_calls_per_eval_row > 0:
        per_row_judge_in = judge_calls_per_eval_row * j_in
        per_row_judge_in_fusion = judge_calls_per_eval_row * fj_in
        per_row_judge_out = judge_calls_per_eval_row * j_out
        judge_model_for_attribution = judges[0] if judges else "(unknown-judge)"
    else:
        per_row_judge_in = per_row_judge_in_fusion = per_row_judge_out = 0
        judge_model_for_attribution = "(unknown-judge)"

    if n_models > 0 and rows > 0:
        for em in eval_models:
            n = rows
            ti, to = n * a_in, n * a_out
            _bump(by_stage, "eval.answer", n, ti, to, em)
            _bump(by_model, em, n, ti, to, em)
            in_c, out_c = _cost(em, ti, to)
            jin_c, jout_c = _cost(
                judge_model_for_attribution, per_row_judge_in * n, per_row_judge_out * n
            )
            b = by_lineup.setdefault(em, _new_bucket())
            _add(
                b,
                n + judge_calls_per_eval_row * n,
                ti + per_row_judge_in * n,
                to + per_row_judge_out * n,
                in_c + jin_c,
                out_c + jout_c,
            )

    for f in fusions:
        fname = f.get("name") or "(unnamed)"
        fb = by_fusion.setdefault(fname, _new_bucket())
        lb = by_lineup.setdefault(f"fusion:{fname}", _new_bucket())

        for panel_m in f.get("panel") or []:
            n = rows
            ti, to = n * a_in, n * a_out
            _bump(by_stage, "fusion.panel", n, ti, to, panel_m)
            _bump(by_model, panel_m, n, ti, to, panel_m)
            in_c, out_c = _cost(panel_m, ti, to)
            _add(fb, n, ti, to, in_c, out_c)
            _add(lb, n, ti, to, in_c, out_c)

        synth = f.get("synthesizer")
        if synth:
            n = rows
            # The synth prompt embeds every panel answer — under ceiling
            # each of those is maxed, so input grows by panel × cap.
            s_in = a_in + len(f.get("panel") or []) * synth_in_extra
            ti, to = n * s_in, n * synth_out
            _bump(by_stage, "fusion.synth", n, ti, to, synth)
            _bump(by_model, synth, n, ti, to, synth)
            in_c, out_c = _cost(synth, ti, to)
            _add(fb, n, ti, to, in_c, out_c)
            _add(lb, n, ti, to, in_c, out_c)

        jc = rows * judge_calls_per_eval_row
        jti = rows * per_row_judge_in_fusion
        jto = rows * per_row_judge_out
        jin_c, jout_c = _cost(judge_model_for_attribution, jti, jto)
        _add(fb, jc, jti, jto, jin_c, jout_c)
        _add(lb, jc, jti, jto, jin_c, jout_c)

    if n_judges > 0 and judge_calls > 0:
        # Solo-row judges read a solo answer (j_in); fusion-row judges
        # read the synth answer (fj_in). Distribute the exact token
        # total across judge models proportionally to their call share.
        solo_judge_calls = rows * n_models * n_judges * judge_calls_per_eval_row
        fusion_judge_calls = judge_calls - solo_judge_calls
        total_judge_in = solo_judge_calls * j_in + fusion_judge_calls * fj_in
        per_j = judge_calls // n_judges
        leftover = judge_calls - per_j * n_judges
        for i, jm in enumerate(judges or ["(unknown-judge)"]):
            n = per_j + (1 if i < leftover else 0)
            ti, to = round(total_judge_in * n / judge_calls), n * j_out
            _bump(by_stage, "eval.judge", n, ti, to, jm)
            _bump(by_model, jm, n, ti, to, jm)

    for m, b in by_model.items():
        _round(b)
        p = pricing.get(m, {})
        b["input_per_1m"] = p.get("input_per_1m")
        b["output_per_1m"] = p.get("output_per_1m")
    for b in by_stage.values():
        _round(b)
    for b in by_fusion.values():
        _round(b)
    for b in by_lineup.values():
        _round(b)

    total_in_tokens = sum(b["tokens_in"] for b in by_model.values())
    total_out_tokens = sum(b["tokens_out"] for b in by_model.values())
    total_in = sum(b["cost_in_usd"] for b in by_model.values())
    total_out = sum(b["cost_out_usd"] for b in by_model.values())

    total_calls = (
        model_answer_calls + fusion_panel_calls + fusion_synth_calls + judge_calls
    )

    return {
        "mode": "ceiling" if ceiling else "expected",
        "simulation_inputs": {
            "benchmark": "draco",
            "rows_in_eval": rows,
            "eval_models": list(eval_models),
            "fusions": [f.get("name") for f in fusions],
            "judges": list(judges),
            "judge_runs": judge_runs,
            "grading_mode": grading_mode,
            "judge_chunk_size": chunk_size,
            "avg_criteria_per_task": avg_criteria,
            "articles_processed": rows,
            "qa_per_article": 1,
            "extractive_mode": "n/a",
            "run_abstractive": False,
            "quality_check": False,
            "generator_model": "(none — Phase 2 is a reshape)",
            "eval_modes": list(ec.get("modes") or []),
            "evaluators": list(ec.get("evaluators") or ["direct"]),
            "eval_limit_per_gen": ev_limit,
            "k_rounds": int(ec.get("k_rounds") or 0),
            "trials": int(ec.get("trials") or 0),
            "temperatures": list(ec.get("temperatures") or []),
        },
        "predicted_qa_generated": rows,
        "predicted_qa_in_eval": rows,
        "calls": {
            "dataset.generate": 0,
            "dataset.verify": 0,
            "eval.answer": model_answer_calls,
            "fusion.panel": fusion_panel_calls,
            "fusion.synth": fusion_synth_calls,
            "eval.judge": judge_calls,
            "total": total_calls,
        },
        "total_tokens_in": total_in_tokens,
        "total_tokens_out": total_out_tokens,
        "total_tokens": total_in_tokens + total_out_tokens,
        "total_cost_in_usd": round(total_in, 6),
        "total_cost_out_usd": round(total_out, 6),
        "total_cost_usd": round(total_in + total_out, 6),
        "by_model": by_model,
        "by_stage": by_stage,
        "by_fusion": by_fusion,
        "by_lineup": by_lineup,
        "calibration": {
            "raw_avg_tokens": {
                k: {"avg_in": v[0], "avg_out": v[1]} for k, v in avg_tokens.items()
            },
            "K_calibration": k_calibration,
            "K_simulated": 1,
            "max_tokens_cap": max_tokens,
            "effective_avg": {
                "eval.answer": {"avg_in": a_in, "avg_out": a_out},
                "eval.judge": {"avg_in": j_in, "avg_out": j_out},
            },
        },
    }
