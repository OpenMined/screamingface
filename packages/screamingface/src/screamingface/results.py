"""Immutable, provenance-carrying benchmark run results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape


@dataclass(frozen=True)
class RunFailure:
    question_id: str
    model: str
    code: str
    message: str


@dataclass(frozen=True)
class ModelResult:
    model: str
    score: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    failures: int = 0


@dataclass(frozen=True)
class Run:
    benchmark: str
    dataset_source: str
    mode: str
    models: tuple[str, ...]
    url: str
    sample_size: int
    seed: int
    score: float
    baseline: float
    gain: float
    cost_usd: float
    fusion_name: str = "fusion"
    reduce: str = "majority_vote"
    judge: str | None = None
    incomplete: int = 0
    profiles: tuple[tuple[str, str], ...] = ()
    pricing_source: str = "estimate:SDK catalog"
    pricing_as_of: str = "2026-07-16"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_results: tuple[ModelResult, ...] = ()
    failures: tuple[RunFailure, ...] = ()
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC), compare=False, repr=False
    )

    def _repr_html_(self) -> str:
        return _run_html(self)


def _run_html(run: Run) -> str:
    simulated = run.mode == "mock"
    mode_color = "#8a5a00" if simulated else "#137333"
    mode_label = "MOCK · NO PROVIDER CLAIM" if simulated else "LIVE PROVIDER RUN"
    cost_value = "$0.000" if simulated else f"${run.cost_usd:.4f}"
    cost_label = "no provider spend" if simulated else "estimated cost"
    metrics = "".join(
        [
            _metric(run.score, "fusion accuracy"),
            _metric(run.gain, "gain over best", signed=True),
            _metric(run.baseline, "best single"),
            _metric(cost_value, cost_label),
        ]
    )
    recipe = f"reduce {escape(run.reduce)}"
    if run.judge:
        recipe += f" · judge {_model_name(run.judge)}"
    model_rows = "".join(
        _model_result_html(result, result.score == run.baseline) for result in run.model_results
    )
    incomplete = (
        ""
        if run.incomplete == 0
        else (
            "<div style='margin-top:.65rem;padding:.5rem .65rem;border-radius:5px;"
            "background:#fef7e0;color:#7a4d00'>"
            f"{run.incomplete} incomplete question rows · {len(run.failures)} recorded failures"
            "</div>"
        )
    )
    models = (
        ""
        if not model_rows
        else (
            "<div style='border-top:1px solid #dadce0;margin-top:.8rem;padding-top:.7rem'>"
            "<div style='font-size:.82rem;color:#5f6368;margin-bottom:.35rem'>"
            "PER-MODEL ACCURACY</div>"
            f"{model_rows}</div>"
        )
    )
    dataset = escape(run.dataset_source)
    return (
        "<div style='font-family:system-ui,-apple-system,sans-serif;max-width:980px;"
        "border:1px solid #dadce0;border-radius:10px;padding:16px 18px;"
        "box-shadow:0 2px 8px rgba(60,64,67,.08)'>"
        "<div style='display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap'>"
        f"<div><div style='font-size:.75rem;font-weight:700;color:{mode_color}'>"
        f"{mode_label}</div><div style='font-size:1.15rem;font-weight:700'>"
        f"{escape(run.fusion_name)}</div></div>"
        f"<div style='color:#3c4043'>{escape(run.benchmark)} · n={run.sample_size} · "
        f"seed {run.seed}</div></div>"
        "<div style='display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));"
        f"gap:.75rem;margin:.9rem 0'>{metrics}</div>"
        f"{_score_bar(run.score)}"
        f"<div style='margin-top:.55rem;color:#3c4043'>{recipe}</div>"
        f"{models}{incomplete}"
        "<div style='margin-top:.75rem;padding-top:.6rem;border-top:1px solid #eceff1;"
        "font-size:.75rem;color:#70757a'>"
        f"Dataset: {dataset} · pricing: {escape(run.pricing_source)} "
        f"({escape(run.pricing_as_of)}) · {run.total_tokens:,} tokens"
        "</div></div>"
    )


def _metric(value: float | str, label: str, *, signed: bool = False) -> str:
    if isinstance(value, str):
        rendered = value
        color = "#202124"
    else:
        rendered = f"{value:+.1f}" if signed else f"{value:.1f}"
        color = (
            "#137333"
            if signed and value > 0
            else ("#b3261e" if signed and value < 0 else "#202124")
        )
    return (
        "<div><div style='font-size:1.35rem;font-weight:700;"
        f"color:{color}'>{rendered}</div>"
        f"<div style='font-size:.8rem;color:#5f6368'>{escape(label)}</div></div>"
    )


def _score_bar(score: float) -> str:
    width = min(100.0, max(0.0, score))
    return (
        "<div style='height:8px;background:#e8eaed;border-radius:999px;overflow:hidden'>"
        f"<div style='height:100%;width:{width:.1f}%;background:#202124'></div></div>"
    )


def _model_result_html(result: ModelResult, best: bool) -> str:
    width = min(100.0, max(0.0, result.score))
    name = escape(_model_name(result.model))
    provider = escape(_provider_name(result.model))
    best_label = " <span style='color:#a15c00'>best</span>" if best else ""
    failures = f" · {result.failures} failures" if result.failures else ""
    return (
        "<div style='display:grid;grid-template-columns:minmax(180px,1.2fr) 3fr 70px;"
        "gap:.7rem;align-items:center;padding:.35rem 0'>"
        f"<div><strong>{name}</strong><div style='font-size:.72rem;color:#70757a'>"
        f"{provider}{failures}</div></div>"
        "<div style='height:7px;background:#e8eaed;border-radius:999px;overflow:hidden'>"
        f"<div style='height:100%;width:{width:.1f}%;background:#5f6368'></div></div>"
        f"<div style='text-align:right;font-weight:700'>{result.score:.1f}{best_label}</div></div>"
    )


def _provider_name(model: str) -> str:
    provider = model.split("/", 1)[0]
    names = {
        "anthropic": "Anthropic",
        "codex": "OpenAI Codex",
        "gemini-cli": "Google Gemini",
        "huggingface": "Hugging Face",
        "open_router": "OpenRouter",
        "openrouter": "OpenRouter",
    }
    return names.get(provider, provider.replace("-", " ").replace("_", " ").title())


def _model_name(model: str) -> str:
    raw = model.rsplit("/", 1)[-1].split(":", 1)[0]
    name = raw.replace("-", " ").replace("_", " ").title()
    name = re.sub(r"(?<=\d) (?=\d)", ".", name)
    return re.sub(r"\b(Gpt|Ai|Api)\b", lambda match: match.group(1).upper(), name)
