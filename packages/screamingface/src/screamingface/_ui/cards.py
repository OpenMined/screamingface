"""Escaped notebook HTML for Client authoring values and catalogues."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from typing import TYPE_CHECKING

from screamingface._ui.card_style import CARD_STYLE

if TYPE_CHECKING:
    from screamingface.discovery import Benchmark, CaseInfo, ModelInfo
    from screamingface.fusion import Fusion
    from screamingface.model import Model
    from screamingface.recipe import Recipe


def model_card_html(model: Model) -> str:
    """Render only authoring fields actually held by one Model."""

    fields = _field("route", _mono(model.model)) + _field(
        "provider", escape(_provider_of(model.model))
    )
    if model.prompt is not None:
        fields += _field("prompt", escape(model.prompt), wide=True)
    if model.params:
        fields += _field("params", _params(model.params), wide=True)
    return (
        f"{CARD_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace model'>"
        "<div class='sf-card__accent sf-card__accent--solid'></div>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(model.name)}</span>"
        "<span class='sf-card__kicker'>model</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def fusion_card_html(fusion: Fusion) -> str:
    """Render the Benchmark-independent Fusion topology."""

    members = "".join(_member_detail(member) for member in fusion.members)
    synthesis = ""
    if fusion.synthesizer is not None or fusion.prompt is not None or fusion.params:
        fields = ""
        if fusion.synthesizer is not None:
            fields += _field("synthesizer", _mono(fusion.synthesizer), wide=True)
        if fusion.prompt is not None:
            fields += _field("prompt", escape(fusion.prompt), wide=True)
        if fusion.params:
            fields += _field("params", _params(fusion.params), wide=True)
        synthesis = _section("synthesis", f"<div class='sf-card__grid'>{fields}</div>")
    return (
        f"{CARD_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace fusion'>"
        "<div class='sf-card__accent'></div>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(fusion.name)}</span>"
        "<span class='sf-card__kicker'>fusion</span></div>"
        f"{_section('members', members)}{synthesis}</div>"
    )


def models_rows_html(records: Sequence[ModelInfo]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No models match.</div>"
    return "".join(
        "<div class='sf-catalog__row'>"
        f"<div class='sf-catalog__id'>{escape(record.id)}</div>"
        f"{_tags(_chip(record.provider))}</div>"
        for record in records
    )


def benchmarks_rows_html(records: Sequence[Benchmark]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No benchmarks match.</div>"
    return "".join(
        "<div class='sf-catalog__row'>"
        f"<div class='sf-catalog__id'>{escape(record.title)}</div>"
        f"{_tags(_chip(record.id) + _chip(f'{record.case_count} cases'))}"
        f"<div class='sf-card__hint'>{escape(record.description)}</div></div>"
        for record in records
    )


def cases_rows_html(records: Sequence[CaseInfo]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No cases match.</div>"
    # WHY the --case modifier: the base row grid is title+tags proportioned; a case
    # row is chip + long prompt, so the chip hugs the left at natural width and the
    # prompt takes the remaining line length.
    return "".join(
        "<div class='sf-catalog__row sf-catalog__row--case'>"
        f"{_tags(_chip(f'case {record.id}'))}"
        f"<div class='sf-card__hint'>{escape(record.input)}</div></div>"
        for record in records
    )


def benchmark_card_html(benchmark: Benchmark) -> str:
    """Render the identity card a researcher reads before evaluating."""

    fields = (
        _field("id", _mono(benchmark.id))
        + _field("cases", escape(str(benchmark.case_count)))
        + _field("revision", _mono(benchmark.revision))
        + _field("description", escape(benchmark.description), wide=True)
    )
    return (
        f"{CARD_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace benchmark'>"
        "<div class='sf-card__accent sf-card__accent--solid'></div>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(benchmark.title)}</span>"
        "<span class='sf-card__kicker'>benchmark</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def catalog_html(title: str, aria: str, count: int, rows: str) -> str:
    """Wrap escaped rows in the static fallback used outside interactive notebooks."""

    return (
        f"{CARD_STYLE}<div class='sf-ui sf-catalog' aria-label='{escape(aria)}'>"
        "<div class='sf-card__accent sf-card__accent--solid'></div>"
        f"<div class='sf-catalog__head'><div class='sf-catalog__title'>{escape(title)}</div>"
        f"<div class='sf-catalog__count'>{count}</div></div>{rows}</div>"
    )


def _field(label: str, value_html: str, *, wide: bool = False) -> str:
    css = "sf-card__field wide" if wide else "sf-card__field"
    return (
        f"<div class='{css}'><div class='sf-card__k'>{escape(label)}</div>"
        f"<div class='sf-card__v'>{value_html}</div></div>"
    )


def _section(title: str, body: str) -> str:
    return (
        f"<div class='sf-section'><div class='sf-section__title'>{escape(title)}</div>{body}</div>"
    )


def _member_detail(member: Recipe) -> str:
    route = getattr(member, "model", None)
    if route is None:
        detail = "<div class='sf-card__hint'>nested fusion</div>"
    else:
        detail = f"<div class='sf-detail__route'>{escape(str(route))}</div>"
    return (
        "<div class='sf-detail__item'>"
        f"<div class='sf-detail__name'>{escape(member.name)}</div>{detail}</div>"
    )


def _provider_of(route: str) -> str:
    head = route.split("/", 1)[0]
    return head if head and head != route else "—"


def _mono(value: str) -> str:
    return f"<span class='sf-mono'>{escape(value)}</span>"


def _params(values: Mapping[str, object]) -> str:
    return _mono(", ".join(f"{name}={value}" for name, value in values.items()))


def _chip(value: str) -> str:
    return f"<span class='sf-chip'>{escape(value)}</span>"


def _tags(chips: str) -> str:
    return f"<div class='sf-catalog__tags'>{chips}</div>"


__all__: list[str] = []
