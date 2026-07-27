"""Static branded cards and catalogs for ScreamingFace notebook display.

FEATURE: notebook rich display for Model/Fusion/Benchmark and the engine catalog.
INVARIANT: these renderers use ONLY fields the SDK actually holds or the engine advertises.
They never emit price, context-window, or ability-score data — that data does not exist, and
inventing it would violate the SDK's "simulated but honest" stance.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from html import escape
from typing import TYPE_CHECKING

from screamingface._card_style import CARD_STYLE as _STYLE

if TYPE_CHECKING:
    from screamingface._profile import BenchmarkRecord, ModelRecord
    from screamingface.benchmark import Benchmark, Case
    from screamingface.connections import Connection
    from screamingface.fusion import Fusion
    from screamingface.graders import Grader, Rubric
    from screamingface.model import Model

# A prompt/route longer than this collapses into a <details>; shorter renders inline.
_LONG_LIMIT = 140


def _field(label: str, value_html: str, *, wide: bool = False) -> str:
    css = "sf-card__field wide" if wide else "sf-card__field"
    return (
        f"<div class='{css}'><div class='sf-card__k'>{escape(label)}</div>"
        f"<div class='sf-card__v'>{value_html}</div></div>"
    )


def _provider_of(route: str) -> str:
    # WHY: model routes namespace the provider as the first path segment (e.g. gemini/2.5-flash).
    # This is a real advertised field, not an inferred metric.
    head = route.split("/", 1)[0]
    return head if head and head != route else "—"


def _params_text(params: Mapping[str, object]) -> str:
    if not params:
        return "<span class='sf-card__hint'>none</span>"
    return escape(", ".join(f"{key}={value}" for key, value in params.items()))


def _mono(text: str) -> str:
    return f"<span class='sf-mono'>{escape(text)}</span>"


def _long_value(text: str) -> str:
    """A field VALUE (no label): inline when short, else a collapsed <details> with a preview."""

    if len(text) <= _LONG_LIMIT:
        return escape(text)
    preview = escape(" ".join(text[:90].split())) + "…"
    return (
        "<details class='sf-more'><summary class='sf-summary'>"
        f"<span class='sf-more__preview'>{preview}</span>"
        f"<span class='sf-card__hint'> · {len(text)} chars</span></summary>"
        f"<div class='sf-more__full'>{escape(text)}</div></details>"
    )


def _prompt_block(prompt: str, *, label: str = "prompt") -> str:
    """A LABELLED prompt line for detail sections: inline when short, else collapsed."""

    if not prompt:
        return ""
    if len(prompt) <= _LONG_LIMIT:
        return f"<div class='sf-detail__params'>{escape(label)}: {escape(prompt)}</div>"
    preview = escape(" ".join(prompt[:90].split())) + "…"
    return (
        "<details class='sf-more'><summary class='sf-summary'>"
        f"<span class='sf-card__k'>{escape(label)}</span> "
        f"<span class='sf-more__preview'>{preview}</span>"
        f"<span class='sf-card__hint'> · {len(prompt)} chars</span></summary>"
        f"<div class='sf-more__full'>{escape(prompt)}</div></details>"
    )


def model_card_html(model: Model) -> str:
    """Render one Model as a branded card of its real authoring fields."""

    fields = "".join(
        (
            _field("route", _mono(model.model)),
            _field("provider", escape(_provider_of(model.model))),
            _field("prompt", _long_value(model.prompt), wide=True),
            _field("params", _params_text(model.params), wide=True),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace model'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(model.name)}</span>"
        "<span class='sf-card__kicker'>model</span></div>"
        f"<div class='sf-card__grid'>{fields}</div>"
        f"{_recipe_html(model.url4)}</div>"
    )


def fusion_card_html(fusion: Fusion) -> str:
    """Render one Fusion as a branded card: members, reducer, and the url4 recipe."""

    members = "".join(_member_row(member) for member in fusion.members)
    fields = "".join(
        (
            _field("reducer", escape(_reducer_label(fusion.reducer))),
            _field("members", f"{len(fusion.members)}"),
            _field(
                "member recipes",
                f"<ul class='sf-card__list'>{members}</ul>",
                wide=True,
            ),
            _field(
                "model ids",
                f"<span class='sf-mono'>{escape(', '.join(fusion.model_ids))}</span>",
                wide=True,
            ),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace fusion'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(fusion.name)}</span>"
        "<span class='sf-card__kicker'>fusion</span></div>"
        f"<div class='sf-card__grid'>{fields}</div>"
        f"{_fusion_detail_html(fusion)}"
        f"{_recipe_html(fusion.url4)}</div>"
    )


def benchmark_card_html(benchmark: Benchmark) -> str:
    """Render one Benchmark verbosely: every interesting field, long ones collapsed."""

    tools = ", ".join(tool.id for tool in benchmark.tools) or "none"
    tool_calls = "—" if benchmark.max_tool_calls is None else str(benchmark.max_tool_calls)
    fields = "".join(
        (
            _field("id", _mono(benchmark.id)),
            _field("aggregator", escape(benchmark.aggregator.kind.replace("_", " "))),
            _field("tools", _mono(tools)),
            _field("max tool calls", escape(tool_calls)),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace benchmark'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(benchmark.title)}</span>"
        "<span class='sf-card__kicker'>benchmark</span></div>"
        f"<div class='sf-card__grid'>{fields}</div>"
        f"{_section('grader', _grader_detail(benchmark.grader))}"
        f"{_benchmark_routes(benchmark)}</div>"
    )


def connection_card_html(connection: Connection) -> str:
    """Render one sanitized Connection as a branded status card."""

    account = connection.account_label or "—"
    method = connection.auth_method or "—"
    fields = "".join(
        (
            _field("provider", f"<span class='sf-mono'>{escape(connection.provider)}</span>"),
            _field("status", escape(connection.status.replace("_", " "))),
            _field("auth method", escape(method)),
            _field("account", escape(account)),
            _field(
                "auth methods",
                f"<span class='sf-mono'>{escape(', '.join(connection.auth_methods))}</span>",
                wide=True,
            ),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace connection'>"
        f"<div class='sf-card__head'>"
        f"<span class='sf-card__title'>{escape(connection.display_name)}</span>"
        "<span class='sf-card__kicker'>connection</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def case_card_html(case: Case) -> str:
    """Render one benchmark Case as a branded card of its authoring fields."""

    fields = "".join(
        (
            _field("input", escape(case.input), wide=True),
            _field(
                "reference",
                f"<span class='sf-mono'>{escape(_json(case.reference))}</span>",
                wide=True,
            ),
            _field(
                "metadata",
                f"<span class='sf-mono'>{escape(_json(case.metadata))}</span>",
                wide=True,
            ),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace case'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(case.id)}</span>"
        "<span class='sf-card__kicker'>case</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def rubric_card_html(rubric: Rubric) -> str:
    """Render one Rubric grader as a branded card: judge model, passes, params, prompt."""

    fields = "".join(
        (
            _field("model", _mono(rubric.model)),
            _field("passes", str(rubric.passes)),
            _field("params", _params_text(rubric.params), wide=True),
            _field("prompt", _long_value(rubric.prompt), wide=True),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace rubric grader'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(rubric.model)}</span>"
        "<span class='sf-card__kicker'>rubric grader</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _recipe_html(recipe_url4: str) -> str:
    from screamingface._url4_format import recipe_details_html

    return f"<div class='sf-card__recipe'>{recipe_details_html(recipe_url4)}</div>"


def _member_row(member: object) -> str:
    name = escape(str(getattr(member, "name", "")))
    route = getattr(member, "model", None)
    detail = (
        f"<span class='sf-card__hint'>{escape(str(route))}</span>"
        if route is not None
        else "<span class='sf-card__hint'>(fusion)</span>"
    )
    return f"<li><span class='sf-mono'>{name}</span> {detail}</li>"


def _reducer_label(reducer: object) -> str:
    kind = str(getattr(reducer, "kind", "reducer")).replace("_", " ")
    route = getattr(reducer, "model", None)
    return f"{kind} · {route}" if route is not None else kind


def _section(title: str, body_html: str) -> str:
    """An always-visible titled detail section (not collapsed)."""

    return (
        f"<div class='sf-section'><div class='sf-section__title'>{escape(title)}</div>"
        f"{body_html}</div>"
    )


def _fusion_detail_html(fusion: Fusion) -> str:
    """Separate, always-visible members and reducer sections (long prompts still collapse)."""

    items = "".join(_member_detail(member) for member in fusion.members)
    return _section("members", items) + _section("reducer", _reducer_detail(fusion.reducer))


def _member_detail(member: object) -> str:
    name = escape(str(getattr(member, "name", "")))
    route = getattr(member, "model", None)
    if route is None:  # a nested Fusion has no single route
        return (
            f"<div class='sf-detail__item'><div class='sf-detail__name'>{name}</div>"
            "<div class='sf-card__hint'>nested fusion — see its own card</div></div>"
        )
    params = _params_text(getattr(member, "params", {}))
    return (
        f"<div class='sf-detail__item'><div class='sf-detail__name'>{name}</div>"
        f"<div class='sf-detail__route'>{escape(str(route))}</div>"
        f"<div class='sf-detail__params'>params: {params}</div>"
        f"{_prompt_block(str(getattr(member, 'prompt', '')))}</div>"
    )


def _reducer_detail(reducer: object) -> str:
    kind = str(getattr(reducer, "kind", "reducer")).replace("_", " ")
    header = f"<div class='sf-detail__name'>{escape(kind)}</div>"
    route = getattr(reducer, "model", None)
    if route is None:  # deterministic reducer (e.g. MajorityVote)
        return (
            f"<div class='sf-detail__item'>{header}"
            "<div class='sf-card__hint'>deterministic — no prompt or params</div></div>"
        )
    params = _params_text(getattr(reducer, "params", {}))
    return (
        f"<div class='sf-detail__item'>{header}"
        f"<div class='sf-detail__route'>{escape(str(route))}</div>"
        f"<div class='sf-detail__params'>params: {params}</div>"
        f"{_prompt_block(str(getattr(reducer, 'prompt', '')))}</div>"
    )


def _grader_detail(grader: Grader) -> str:
    kind = str(getattr(grader, "kind", "grader")).replace("_", " ")
    model = getattr(grader, "model", None)
    if model is None:  # deterministic grader (e.g. ExactChoice)
        return f"{escape(kind)} <span class='sf-card__hint'>(deterministic)</span>"
    passes = getattr(grader, "passes", None)
    head = f"{escape(kind)} · model {_mono(str(model))}"
    if passes is not None:
        head += f" · {passes} pass{'' if passes == 1 else 'es'}"
    params = _params_text(getattr(grader, "params", {}))
    return (
        f"<div class='sf-detail__params'>{head}</div>"
        f"<div class='sf-detail__params'>params: {params}</div>"
        f"{_prompt_block(str(getattr(grader, 'prompt', '')))}"
    )


def _benchmark_routes(benchmark: Benchmark) -> str:
    routes = {
        "cases": benchmark._cases_route,
        "grader": benchmark._grader_route,
        "aggregator": benchmark._aggregator_route,
        "tool policy": benchmark._tool_policy_route,
        "candidate": benchmark._candidate_route,
        "candidate aggregator": benchmark._candidate_aggregator_route,
    }
    rows = "".join(
        f"<div class='sf-detail__params'>{escape(label)}: {_mono(route)}</div>"
        for label, route in routes.items()
        if route is not None
    )
    if not rows:
        return ""
    return (
        "<details class='sf-section'><summary class='sf-summary'>"
        "<span class='sf-section__title'>engine routes</span></summary>"
        f"{rows}</details>"
    )


# --- catalogs -----------------------------------------------------------------------------


def models_rows_html(records: Sequence[ModelRecord]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No models match.</div>"
    rows = []
    for record in records:
        tools = ", ".join(record.supported_tools) or "no tools"
        rows.append(
            "<div class='sf-catalog__row'>"
            f"<div class='sf-catalog__id'>{escape(record.id)}</div>"
            f"<div class='sf-catalog__meta'>{escape(record.provider)} · {escape(tools)}</div>"
            "</div>"
        )
    return "".join(rows)


def benchmarks_rows_html(records: Sequence[BenchmarkRecord]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No benchmarks match.</div>"
    rows = []
    for record in records:
        tools = ", ".join(record.tools) or "no tools"
        rows.append(
            "<div class='sf-catalog__row'>"
            "<div>"
            f"<div class='sf-catalog__id'>{escape(record.id)}</div>"
            f"<div class='sf-catalog__sub'>{escape(record.title)}</div></div>"
            f"<div class='sf-catalog__meta'>{escape(tools)}</div>"
            "</div>"
        )
    return "".join(rows)


def catalog_html(title: str, aria: str, count: int, rows: str) -> str:
    """Wrap catalog rows in a standalone static catalog card (the widget-less fallback)."""

    return (
        f"{_STYLE}<div class='sf-ui sf-catalog' aria-label='{escape(aria)}'>"
        f"<div class='sf-catalog__head'><div class='sf-catalog__title'>{escape(title)}</div>"
        f"<div class='sf-catalog__count'>{count}</div></div>"
        f"{rows}</div>"
    )


__all__ = [
    "benchmark_card_html",
    "benchmarks_rows_html",
    "case_card_html",
    "catalog_html",
    "connection_card_html",
    "fusion_card_html",
    "model_card_html",
    "models_rows_html",
    "rubric_card_html",
]
