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
    name: str | None = None


@dataclass(frozen=True)
class ModelResult:
    model: str
    score: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    failures: int = 0
    name: str | None = None
    metrics: tuple[tuple[str, float], ...] = ()


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
    engine: str = "mock"
    fusion_name: str = "fusion"
    reducer: str = "majority_vote"
    tie_breaker: str | None = None
    incomplete: int = 0
    profiles: tuple[tuple[str, str], ...] = ()
    pricing_source: str = "estimate:SDK catalog"
    pricing_as_of: str = "2026-07-16"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model_results: tuple[ModelResult, ...] = ()
    failures: tuple[RunFailure, ...] = ()
    primary_metric: str = "accuracy"
    metrics: tuple[tuple[str, float], ...] = ()
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC), compare=False, repr=False
    )

    def _repr_html_(self) -> str:
        return _run_html(self)


def _run_html(run: Run) -> str:
    mock_engine = run.engine == "mock"
    engine_note = (
        "local URL4 mock · no provider-quality claim" if mock_engine else "HTTP URL4 engine"
    )
    cost_value = "$0.000" if mock_engine else f"${run.cost_usd:.4f}"
    cost_label = "no provider spend" if mock_engine else "estimated cost"
    metrics = "".join(
        [
            _metric(run.score, f"fusion {_metric_label(run.primary_metric)}"),
            _metric(run.gain, "gain over best", signed=True),
            _metric(run.baseline, "best single"),
            _metric(cost_value, cost_label),
        ]
    )
    recipe = f"reducer {escape(run.reducer)}"
    if run.tie_breaker:
        recipe += f" · tie breaker {_model_name(run.tie_breaker)}"
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
            "<div style='border-top:1px solid #e0e3e7;margin-top:.9rem;padding-top:.8rem'>"
            "<div style='font-size:.72rem;font-weight:700;letter-spacing:.04em;"
            "color:#5f6368;margin-bottom:.3rem'>"
            f"PER-MODEL {escape(_metric_label(run.primary_metric).upper())}</div>"
            f"{model_rows}</div>"
        )
    )
    dataset = escape(run.dataset_source)
    pricing_date = "" if run.pricing_as_of == "n/a" else f" · as of {escape(run.pricing_as_of)}"
    return (
        "<div style='font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;"
        "max-width:760px;color:#202124;background:#fff;border:1px solid #e0e3e7;"
        "border-radius:10px;padding:18px;box-shadow:0 2px 10px rgba(60,64,67,.10)'>"
        f"<div><div style='font-size:1.05rem;font-weight:700'>{escape(run.fusion_name)}</div>"
        f"<div style='margin-top:.2rem;font-size:.78rem;color:#5f6368'>"
        f"{escape(run.benchmark)} · {run.sample_size} questions · seed {run.seed}</div></div>"
        "<div style='display:grid;grid-template-columns:repeat(4,minmax(105px,1fr));"
        f"gap:.5rem;margin:1rem 0 .75rem'>{metrics}</div>"
        "<div style='padding:.55rem .7rem;background:#f8f9fa;border:1px solid #eceff1;"
        f"border-radius:7px;font-size:.78rem;color:#3c4043'>{recipe} · {engine_note}</div>"
        f"{models}{incomplete}"
        "<div style='margin-top:.8rem;padding-top:.65rem;border-top:1px solid #eceff1;"
        "font-size:.72rem;color:#70757a'>"
        f"Dataset: {dataset} ({escape(run.mode)}) · Engine: {escape(_engine_label(run.engine))} · "
        f"{escape(run.pricing_source)}{pricing_date} · "
        f"{run.total_tokens:,} tokens"
        "</div></div>"
    )


def _engine_label(engine: str) -> str:
    if engine == "mock":
        return "in-process deterministic URL4 node"
    if engine == "custom":
        return "custom URL4 client"
    return engine


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
        "<div style='min-width:0;padding:.62rem .7rem;background:#f8f9fa;"
        "border:1px solid #eceff1;border-radius:7px'>"
        f"<div style='font-size:1.18rem;line-height:1.2;font-weight:700;color:{color}'>"
        f"{rendered}</div>"
        f"<div style='margin-top:.15rem;font-size:.72rem;color:#5f6368'>{escape(label)}</div>"
        "</div>"
    )


def _metric_label(metric: str) -> str:
    return metric.replace("_", " ")


def _model_result_html(result: ModelResult, best: bool) -> str:
    width = min(100.0, max(0.0, result.score))
    name = escape(result.name or _model_name(result.model))
    model_detail = (
        f"{_model_name(result.model)} · {_provider_name(result.model)}"
        if result.name
        else _provider_name(result.model)
    )
    provider = escape(model_detail)
    best_label = (
        " <span style='display:inline-block;padding:.08rem .32rem;border-radius:999px;"
        "background:#fef7e0;color:#8a5a00;font-size:.65rem'>best</span>"
        if best
        else ""
    )
    failures = f" · {result.failures} failures" if result.failures else ""
    return (
        "<div style='display:grid;grid-template-columns:minmax(165px,1.25fr) 2fr 72px;"
        "gap:.7rem;align-items:center;padding:.48rem 0'>"
        f"<div style='font-size:.82rem'><strong>{name}</strong>"
        "<div style='font-size:.7rem;color:#70757a'>"
        f"{provider}{failures}</div></div>"
        "<div style='height:6px;background:#e8eaed;border-radius:999px;overflow:hidden'>"
        f"<div style='height:100%;width:{width:.1f}%;background:#5f6368'></div></div>"
        f"<div style='text-align:right;font-size:.8rem;font-weight:700'>"
        f"{result.score:.1f}{best_label}</div></div>"
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
