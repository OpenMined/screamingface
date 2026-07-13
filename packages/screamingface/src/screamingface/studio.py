"""The Studio surface — the friendly notebook front-end over the engine.

Adds on top of the engine core:

* **``provider/model`` source ids** — ``anthropic/claude-opus-4.8`` instead of
  ``an-1``. The full form is ``owner/provider/model``; ``owner`` defaults to
  ``local`` and is hidden — the federation seam.
* **``sf.models``** — the catalog *service* (`list` / `get`), returning plain id
  strings. WHY a service, not a Pool: the prototype's `sf.models` was both a
  service and a collection; the SDK keeps the collection internal (models.py).
* **``Fusion`` / ``Run``** — sklearn-style constructors compiling to the
  engine's `FusionCore`, and the payoff read-out.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from .datasets import Benchmark, load_benchmark
from .engine import EngineBackend
from .fusion_core import FusionCore
from .models import ALL_MODELS, Model, catalog, get_model
from .results import RunResult

DEFAULT_JUDGE_PROMPT = (
    "You are the judge. Read the candidate answers from each model in the loop "
    "and return the single best final answer."
)

# ── provider/model id scheme ────────────────────────────────────────────────

_PROVIDER_SLUG = {
    "anthropic": "anthropic",
    "openai": "openai",
    "deepmind": "google",
    "perplexity": "perplexity",
    "openrouter": "open_router",
    "hf": "hugging_face",
}
_SLUG_PROVIDER = {v: k for k, v in _PROVIDER_SLUG.items()}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", s.lower()).strip("-")


def _build_aliases() -> tuple[dict[str, str], dict[str, str]]:
    fwd: dict[str, str] = {}  # "anthropic/claude-opus-4.8" -> "an-1"
    rev: dict[str, str] = {}  # "an-1" -> "anthropic/claude-opus-4.8"
    for mid, m in ALL_MODELS.items():
        alias = f"{_PROVIDER_SLUG.get(m.provider_id, m.provider_id)}/{_slug(m.name)}"
        fwd[alias] = mid
        rev[mid] = alias
    return fwd, rev


_ALIAS_TO_ID, _ID_TO_ALIAS = _build_aliases()


def whoami() -> str:
    """The current owner/node. Everything is ``local`` until you federate."""
    return "local"


def _to_short(ref: str | Model) -> str:
    """Resolve a source id (provider/model, owner/provider/model, or short) → short id."""
    if isinstance(ref, Model):
        return ref.id
    r = str(ref).strip()
    parts = r.split("/")
    if len(parts) == 3:  # owner/provider/model -> drop owner (assumed local)
        r = "/".join(parts[1:])
    if r in _ALIAS_TO_ID:
        return _ALIAS_TO_ID[r]
    if r in ALL_MODELS:
        return r
    raise KeyError(f"Unknown model {ref!r}. Try sf.models.list() or sf.models.list(search=...).")


def source_id(m: str | Model) -> str:
    """Canonical ``provider/model`` id for a model or short id."""
    mid = m.id if isinstance(m, Model) else _to_short(m)
    return _ID_TO_ALIAS.get(mid, mid)


# ── sf.models — the catalog service ──────────────────────────────────────────


class ModelsService:
    """Discovery service over the catalog: ids in, ids out."""

    def list(
        self,
        search: str = "",
        provider: str | None = None,
        max_price: float | None = None,
        min_ctx: int = 0,
        sort: str | None = None,
        desc: bool | None = None,
    ) -> list[str]:
        """List ``provider/model`` ids, filtered & sorted.

        ``max_price`` caps the combined in+out price per M tokens; ``sort`` is
        one of price / context / ability / name (ability and context default to
        descending — you usually want the biggest first).
        """
        prov = _SLUG_PROVIDER.get(provider, provider) if provider else None
        pool = catalog.filter(search=search, provider=prov, max_price=max_price, min_ctx=min_ctx)
        if sort:
            if desc is None:
                desc = sort in ("ability", "context", "ctx")
            pool = pool.sort_by(sort, desc=desc)
        return [source_id(m) for m in pool]

    def get(self, ref: str | Model) -> Model:
        """Look up one model by its ``provider/model`` id and return its card."""
        return get_model(_to_short(ref))

    def __repr__(self) -> str:
        return f"sf.models ({len(ALL_MODELS)} models — .list() / .get(id))"


models = ModelsService()


# ── Fusion ────────────────────────────────────────────────────────────────────


class Fusion:
    """The friendly fusion constructor. Compiles to an engine ``FusionCore``."""

    def __init__(
        self,
        name: str,
        models: Sequence[str | Model] = (),  # noqa: PLR0913 — mirrors the notebook contract
        reduce: str = "majority_vote",
        judge: str | Model | None = None,
        prompt: str | None = None,
        judge_prompt: str | None = None,
        loop: str = "parallel",
    ):
        self._core = FusionCore(name)
        self.prompt = prompt
        self.judge_prompt = judge_prompt or DEFAULT_JUDGE_PROMPT
        for m in models:
            self._core.add(_to_short(m))
        # INVARIANT (spec I3): judge membership is validated here, at construction.
        self._core.reduce(reduce, judge=_to_short(judge) if judge else None)
        self._core.loop(loop)

    # ── views ──
    @property
    def name(self) -> str:
        return self._core.name

    @property
    def models(self) -> list[str]:
        return [source_id(m) for m in self._core.models]

    @property
    def judge(self) -> str | None:
        j = self._core.judge
        return source_id(j) if j else None

    @property
    def url(self) -> str:
        """The recipe as a shareable string — the fusion's identity (spec I6)."""
        parts = "+".join(self.models)
        url = (
            f"url4://{self.name}?models={parts}"
            f"&reduce={self._core.reduce_strategy}&loop={self._core.loop_mode}"
        )
        if self.judge:
            url += f"&judge={self.judge}"
        return url

    def evaluate(
        self,
        benchmark: Benchmark | str,
        first: int | None = None,
        seed: int = 0,
        correlation: float = 0.35,
        backend: EngineBackend | None = None,
    ) -> Run:
        """Run this fusion on a benchmark; ``first=None`` means the full set.

        Reproducible by ``seed`` (spec I1). ``backend`` injects a custom
        `EngineBackend` (the real-engine seam); default is the simulator.
        """
        from .evaluate import evaluate as _evaluate

        if isinstance(benchmark, str):
            benchmark = load_benchmark(benchmark, n=(first or 10_000_000), seed=seed)
        res = _evaluate(self._core, benchmark, seed=seed, backend=backend, correlation=correlation)
        return Run(res, self)

    def __repr__(self) -> str:
        return (
            f"Fusion({self.name!r}, {len(self._core.slots)} models, "
            f"reduce={self._core.reduce_strategy})"
        )


# ── Run — the payoff read-out ────────────────────────────────────────────────


class Run:
    """A completed evaluation: score / baseline / gain over one benchmark."""

    def __init__(self, result: RunResult, fusion: Fusion):
        self.result = result
        self.fusion = fusion

    @property
    def score(self) -> float:
        return round(self.result.score, 1)

    @property
    def baseline(self) -> float:
        return round(self.result.baseline, 1)

    @property
    def gain(self) -> float:
        # INVARIANT: gain = score − baseline — the headline number.
        return round(self.result.gain_over_best, 1)

    @property
    def seed(self) -> int:
        return self.result.seed

    @property
    def sample_size(self) -> int:
        return self.result.sample_size

    @property
    def benchmark_name(self) -> str:
        return self.result.benchmark_name

    @property
    def cost(self) -> float:
        return round(self.result.total_cost, 4)

    @property
    def url(self) -> str:
        """The recipe pinned to this run's benchmark, sample size, and seed."""
        return (
            f"{self.fusion.url}&benchmark={self.result.benchmark_id}"
            f"&n={self.sample_size}&seed={self.seed}"
        )

    def __repr__(self) -> str:
        return (
            f"Run({self.fusion.name!r} on {self.benchmark_name!r}: "
            f"score={self.score}  gain={self.gain:+}  cost=${self.cost:g})"
        )
