"""The model catalog and benchmark registry.

Everything in this module is *data* ported verbatim from the original
Model Fusion Studio design prototype (``src/app/App.tsx``): the model pools
for every provider, per-model pricing & context windows (``MODEL_META``),
each model's base ability (``BASE_SCORES``), the provider registry, and the
benchmark list.

Nothing here calls a network or a model. It is the static "what exists in the
world" layer that the rest of the library composes on top of.
"""

from __future__ import annotations

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Model pools, one per provider. (id, name, provider_id, provider_name, tag)
# ─────────────────────────────────────────────────────────────────────────────

# Each entry is (id, name, tag). The provider id/name are attached below.
_POOLS: dict[str, list[tuple]] = {
    "openrouter": [
        ("or-1", "Claude Opus 4", None),
        ("or-2", "Claude Sonnet 4.6", None),
        ("or-3", "Gemini 2.5 Pro", None),
        ("or-4", "GPT-4o", None),
        ("or-5", "Llama 4 Scout", None),
        ("or-6", "DeepSeek-R1", None),
    ],
    "hf": [
        ("hf-1", "Mistral 7B Instruct", None),
        ("hf-2", "Zephyr 7B Beta", None),
    ],
    "anthropic": [
        ("an-1", "Claude Opus 4.8", None),
        ("an-2", "Claude Sonnet 4.6", None),
        ("an-3", "Claude Haiku 4.5", None),
    ],
    "openai": [
        ("oa-1", "GPT-5", None),
        ("oa-2", "GPT-4o", None),
        ("oa-3", "o3", None),
        ("oa-4", "GPT-4o Mini", None),
    ],
    "deepmind": [
        ("dm-1", "Gemini 2.5 Pro", None),
        ("dm-2", "Gemini 2.5 Flash", None),
        ("dm-3", "Gemini 2.0 Flash", None),
    ],
    "perplexity": [
        ("px-1", "Sonar Pro", None),
        ("px-2", "Sonar Reasoning", None),
        ("px-3", "Sonar Large", None),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Provider registry
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    kind: str  # "local" | "session" | "hub" | "api"
    group: str
    description: str
    color: str


PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in [
        Provider(
            "anthropic",
            "Anthropic",
            "api",
            "Providers",
            "Claude models, direct from the API",
            "#CA492C",
        ),
        Provider("openai", "OpenAI", "api", "Providers", "GPT & o-series models", "#53BEA9"),
        Provider(
            "deepmind",
            "Google DeepMind",
            "api",
            "Providers",
            "Gemini models, direct from the API",
            "#6976AE",
        ),
        Provider(
            "perplexity",
            "Perplexity",
            "api",
            "Providers",
            "Sonar online & reasoning models",
            "#175C6D",
        ),
        Provider(
            "openrouter", "OpenRouter", "hub", "Hubs", "300+ models behind one API key", "#937098"
        ),
        Provider(
            "hf",
            "HuggingFace Inference",
            "api",
            "Hubs",
            "Serverless open-source inference",
            "#F79763",
        ),
    ]
}

GROUP_ORDER = ["Providers", "Hubs"]

# Provider colors that appear in seed leaderboard entries but have no model pool.
_EXTRA_COLORS = {"moonshot": "#563B59", "xai": "#464158", "meta": "#6976AE"}


def provider_color(provider_id: str) -> str:
    p = PROVIDERS.get(provider_id)
    if p:
        return p.color
    return _EXTRA_COLORS.get(provider_id, "#B8520A")


# ─────────────────────────────────────────────────────────────────────────────
# Per-model metadata: pricing (USD / 1M tokens), context window, blurb, ability.
# `ability` is the model's base accuracy on a *hard* benchmark (GPQA-scale),
# reinterpreted from the prototype's BASE_SCORES. The simulator adjusts it per
# benchmark via a difficulty offset (see backend.py).
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelMeta:
    price_in: float  # USD per million input tokens
    price_out: float  # USD per million output tokens
    ctx: int  # context window, tokens
    ability: float  # base accuracy on a hard benchmark, 0-100
    desc: str = ""


_META: dict[str, dict] = {
    # Anthropic
    "an-1": dict(
        price_in=5,
        price_out=25,
        ctx=200000,
        ability=38.4,
        desc="Anthropic's most capable model for hard reasoning and code.",
    ),
    "an-2": dict(
        price_in=3,
        price_out=15,
        ctx=200000,
        ability=33.1,
        desc="Balanced speed and quality for everyday tasks.",
    ),
    "an-3": dict(
        price_in=1,
        price_out=5,
        ctx=200000,
        ability=22.0,
        desc="Fast and cheap for high-throughput workloads.",
    ),
    # OpenAI
    "oa-1": dict(
        price_in=1.25,
        price_out=10,
        ctx=400000,
        ability=37.2,
        desc="OpenAI's flagship reasoning model.",
    ),
    "oa-2": dict(price_in=2.5, price_out=10, ctx=128000, ability=31.4),
    "oa-3": dict(
        price_in=2, price_out=8, ctx=200000, ability=36.8, desc="Reasoning-tuned o-series model."
    ),
    "oa-4": dict(
        price_in=0.15,
        price_out=0.6,
        ctx=128000,
        ability=24.0,
        desc="Small, inexpensive, surprisingly capable.",
    ),
    # Google DeepMind
    "dm-1": dict(
        price_in=1.25,
        price_out=10,
        ctx=1048576,
        ability=35.6,
        desc="Long-context multimodal flagship.",
    ),
    "dm-2": dict(price_in=0.3, price_out=2.5, ctx=1048576, ability=27.2),
    "dm-3": dict(price_in=0.1, price_out=0.4, ctx=1048576, ability=23.5),
    # Perplexity
    "px-1": dict(
        price_in=3,
        price_out=15,
        ctx=200000,
        ability=29.0,
        desc="Online model with live web grounding.",
    ),
    "px-2": dict(price_in=1, price_out=5, ctx=127000, ability=32.4),
    "px-3": dict(price_in=1, price_out=1, ctx=127000, ability=26.5),
    # OpenRouter
    "or-1": dict(price_in=15, price_out=75, ctx=200000, ability=34.2),
    "or-2": dict(price_in=3, price_out=15, ctx=200000, ability=31.0),
    "or-3": dict(price_in=1.25, price_out=10, ctx=1048576, ability=35.6),
    "or-4": dict(price_in=2.5, price_out=10, ctx=128000, ability=31.4),
    "or-5": dict(
        price_in=0.08,
        price_out=0.3,
        ctx=327680,
        ability=24.0,
        desc="Efficient open MoE — very cheap at scale.",
    ),
    "or-6": dict(
        price_in=0.55, price_out=2.19, ctx=131072, ability=30.1, desc="Open reasoning model."
    ),
    # HuggingFace
    "hf-1": dict(price_in=0.05, price_out=0.1, ctx=32768, ability=16.0),
    "hf-2": dict(price_in=0.05, price_out=0.1, ctx=8192, ability=14.5),
}

MODEL_META: dict[str, ModelMeta] = {mid: ModelMeta(**m) for mid, m in _META.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Benchmarks
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BenchmarkSpec:
    id: str
    name: str
    domain: str
    questions: int  # nominal full size (for display)
    kind: str  # "mcq" | "free"
    # accuracy points added to a model's base (GPQA-scale) ability on this
    # benchmark; positive = easier than GPQA. Keeps simulated scores realistic.
    difficulty_delta: float


BENCHMARKS: dict[str, BenchmarkSpec] = {
    b.id: b
    for b in [
        BenchmarkSpec("gpqa", "GPQA Diamond", "Science", 448, "mcq", 0.0),
        BenchmarkSpec("mmlu", "MMLU Pro", "Multi-domain", 12000, "mcq", 49.0),
        BenchmarkSpec("heval", "HumanEval+", "Coding", 164, "free", 56.0),
        BenchmarkSpec("arc", "ARC-Challenge", "Reasoning", 1172, "mcq", 45.0),
        BenchmarkSpec("math", "MATH-500", "Math", 500, "free", 30.0),
    ]
}


# ─────────────────────────────────────────────────────────────────────────────
# Convenience name <-> id maps (benchmark names appear on the leaderboard)
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARK_BY_NAME: dict[str, BenchmarkSpec] = {b.name: b for b in BENCHMARKS.values()}


def benchmark_spec(key: str) -> BenchmarkSpec:
    """Look up a benchmark by id ('gpqa') or display name ('GPQA Diamond')."""
    if key in BENCHMARKS:
        return BENCHMARKS[key]
    if key in BENCHMARK_BY_NAME:
        return BENCHMARK_BY_NAME[key]
    raise KeyError(
        f"Unknown benchmark {key!r}. Known: {sorted(BENCHMARKS)} "
        f"or names {sorted(BENCHMARK_BY_NAME)}."
    )
