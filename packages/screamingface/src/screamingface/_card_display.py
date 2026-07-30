"""Escaped notebook HTML for Client authoring values and catalogues."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import TYPE_CHECKING

from screamingface._card_style import CARD_STYLE
from screamingface.reducers import Reducer, Synthesis

if TYPE_CHECKING:
    from screamingface.discovery import BenchmarkInfo, ModelInfo
    from screamingface.fusion import Fusion
    from screamingface.model import Model
    from screamingface.recipe import Recipe

_LONG_LIMIT = 140


def model_card_html(model: Model) -> str:
    """Render only authoring fields actually held by one Model."""

    fields = (
        _field("route", _mono(model.model))
        + _field("provider", escape(_provider_of(model.model)))
        + _field("instructions", _long_value(model.instructions), wide=True)
        + _field("temperature", _optional(model.temperature))
        + _field("reasoning", _optional(model.reasoning))
        + _field("max output tokens", _optional(model.max_output_tokens))
    )
    return (
        f"{CARD_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace model'>"
        "<div class='sf-card__accent sf-card__accent--solid'></div>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(model.name)}</span>"
        "<span class='sf-card__kicker'>model</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
    )


def fusion_card_html(fusion: Fusion) -> str:
    """Render direct members and Synthesis as separate visible sections."""

    members = "".join(_member_detail(member) for member in fusion.members)
    return (
        f"{CARD_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace fusion'>"
        "<div class='sf-card__accent'></div>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(fusion.name)}</span>"
        "<span class='sf-card__kicker'>fusion</span></div>"
        f"{_section('members', members)}"
        f"{_section('synthesis', _synthesis_detail(fusion.reducer))}</div>"
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


def benchmarks_rows_html(records: Sequence[BenchmarkInfo]) -> str:
    if not records:
        return "<div class='sf-catalog__empty'>No benchmarks match.</div>"
    return "".join(_benchmark_row(record) for record in records)


def catalog_html(title: str, aria: str, count: int, rows: str) -> str:
    """Wrap escaped rows in the static fallback used outside interactive notebooks."""

    return (
        f"{CARD_STYLE}<div class='sf-ui sf-catalog' aria-label='{escape(aria)}'>"
        "<div class='sf-card__accent sf-card__accent--solid'></div>"
        f"<div class='sf-catalog__head'><div class='sf-catalog__title'>{escape(title)}</div>"
        f"<div class='sf-catalog__count'>{count}</div></div>{rows}</div>"
    )


def _benchmark_row(record: BenchmarkInfo) -> str:
    case_label = f"{record.case_count} case" + ("" if record.case_count == 1 else "s")
    details = (
        "<details><summary class='sf-summary'>"
        "<span class='sf-card__k'>manifest</span></summary>"
        f"<div class='sf-detail__route'>{escape(record.manifest_digest)}</div></details>"
    )
    chips = _chip(case_label) + _chip(record.primary_metric) + _chip(record.score_direction)
    return (
        "<div class='sf-catalog__row'><div>"
        f"<div class='sf-catalog__id'>{escape(record.id)}</div>"
        f"<div class='sf-catalog__sub'>{escape(record.title)}</div>{details}</div>"
        f"{_tags(chips)}</div>"
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


def _synthesis_detail(reducer: Reducer) -> str:
    if not isinstance(reducer, Synthesis):
        return f"<div class='sf-detail__item'>{escape(repr(reducer))}</div>"
    params = (
        _param("temperature", reducer.temperature)
        + _param("reasoning", reducer.reasoning)
        + _param("max output tokens", reducer.max_output_tokens)
    )
    return (
        "<div class='sf-detail__item'>"
        f"<div class='sf-detail__route'>{escape(reducer.model)}</div>"
        f"{_prompt_block(reducer.instructions)}{params}</div>"
    )


def _param(label: str, value: object | None) -> str:
    if value is None:
        return ""
    return f"<div class='sf-detail__params'>{escape(label)}: {escape(str(value))}</div>"


def _prompt_block(value: str | None) -> str:
    if value is None:
        return "<div class='sf-card__hint'>default instructions</div>"
    return f"<div class='sf-detail__params'>instructions: {_long_value(value)}</div>"


def _long_value(value: str | None) -> str:
    if value is None:
        return "<span class='sf-card__hint'>default</span>"
    if len(value) <= _LONG_LIMIT:
        return escape(value)
    preview = escape(" ".join(value[:90].split())) + "…"
    return (
        "<details><summary class='sf-summary'>"
        f"<span class='sf-card__hint'>{preview} · {len(value)} chars</span></summary>"
        f"<div class='sf-more__full'>{escape(value)}</div></details>"
    )


def _provider_of(route: str) -> str:
    head = route.split("/", 1)[0]
    return head if head and head != route else "—"


def _optional(value: object | None) -> str:
    if value is None:
        return "<span class='sf-card__hint'>default</span>"
    return escape(str(value))


def _mono(value: str) -> str:
    return f"<span class='sf-mono'>{escape(value)}</span>"


def _chip(value: str) -> str:
    return f"<span class='sf-chip'>{escape(value)}</span>"


def _tags(chips: str) -> str:
    return f"<div class='sf-catalog__tags'>{chips}</div>"


__all__: list[str] = []
