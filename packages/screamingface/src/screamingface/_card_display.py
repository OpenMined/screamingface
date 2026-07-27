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

from screamingface._display import STYLE

if TYPE_CHECKING:
    from screamingface._profile import BenchmarkRecord, ModelRecord
    from screamingface.benchmark import Benchmark, Case
    from screamingface.connections import Connection
    from screamingface.fusion import Fusion
    from screamingface.graders import Rubric
    from screamingface.model import Model

_STYLE = (
    STYLE
    + """<style>
.sf-card{border:1px solid var(--sf-line-2);background:var(--sf-bg)}
.sf-card__head{display:flex;align-items:baseline;gap:8px;padding:10px 12px;
  border-bottom:1px solid var(--sf-line)}
.sf-card__title{font-size:15px;font-weight:600}
.sf-card__kicker{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--sf-gain)}
.sf-card__grid{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--sf-line);
  border-bottom:1px solid var(--sf-line)}
.sf-card__field{background:var(--sf-bg);padding:8px 12px;min-width:0}
.sf-card__field.wide{grid-column:1 / -1}
.sf-card__k{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--sf-ink-3)}
.sf-card__v{margin-top:2px;overflow-wrap:anywhere}
.sf-card__hint{color:var(--sf-ink-3)}
.sf-card__list{margin:2px 0 0;padding:0;list-style:none}
.sf-card__list li{padding:1px 0}
.sf-card__recipe{padding:8px 12px;background:var(--sf-surface)}
.sf-card__recipe code{display:block;margin-top:2px;font-size:11px;
  font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--sf-ink);
  white-space:pre-wrap;overflow-wrap:anywhere;background:transparent;border:0;padding:0}
.sf-mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.sf-catalog{border:1px solid var(--sf-line-2)}
.sf-catalog-widget.widget-vbox{border:0!important;box-shadow:none!important}
.sf-catalog__head{display:flex;align-items:center;gap:8px;height:44px;padding:0 12px;
  border-bottom:1px solid var(--sf-line-2)}
.sf-catalog__title{font-size:13px;font-weight:600}
.sf-catalog__count{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;color:var(--sf-ink-3)}
.sf-catalog__row{display:grid;grid-template-columns:minmax(0,2fr) 1fr;gap:12px;
  align-items:center;padding:8px 12px;border-bottom:1px solid var(--sf-line)}
.sf-catalog__row:last-child{border-bottom:0}
.sf-catalog__id{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  font-weight:600;overflow-wrap:anywhere}
.sf-catalog__sub{color:var(--sf-ink-2)}
.sf-catalog__meta{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  color:var(--sf-ink-3);text-align:right;overflow-wrap:anywhere}
.sf-catalog__empty{padding:16px 12px;color:var(--sf-ink-3);text-align:center;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px}
.sf-catalog-widget .widget-text input{border-radius:0!important;box-shadow:none!important;
  background-image:none!important;height:32px!important;padding:0 8px!important;
  border:1px solid var(--sf-line-2)!important;background:var(--sf-bg)!important;
  color:var(--sf-ink)!important;
  font:12px/1 "IBM Plex Mono",ui-monospace,monospace!important}
.sf-catalog-widget .widget-text{width:auto!important;margin:8px 12px!important}
.sf-url4{border:0}
.sf-url4__summary{cursor:pointer;display:flex;align-items:center;gap:8px;list-style:none}
.sf-url4__summary::-webkit-details-marker{display:none}
.sf-url4__summary::before{content:'▸';color:var(--sf-ink-3);font-size:10px}
.sf-url4[open] .sf-url4__summary::before{content:'▾'}
.sf-url4__copy{margin-left:auto;cursor:pointer;border-radius:0;
  border:1px solid var(--sf-line-2);background:var(--sf-bg);color:var(--sf-ink-2);
  padding:2px 8px;font:11px/1 "IBM Plex Mono",ui-monospace,monospace}
.sf-url4__copy:hover{border-color:var(--sf-ink-3);color:var(--sf-ink)}
.sf-url4__body{margin-top:8px}
.sf-url4__nodes{display:flex;flex-direction:column;gap:6px}
.sf-url4__node{border-left:2px solid var(--sf-line-2);padding:1px 0 1px 10px}
.sf-url4__nhead{display:flex;align-items:baseline;gap:8px}
.sf-url4__name{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  font-weight:600;color:var(--sf-gain)}
.sf-url4__weight{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:10px;
  color:var(--sf-ink-3)}
.sf-url4__route{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  color:var(--sf-ink);overflow-wrap:anywhere}
.sf-url4__param,.sf-url4__ctx,.sf-url4__leaf,.sf-url4__struct{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;color:var(--sf-ink-2);
  padding-left:10px;overflow-wrap:anywhere}
.sf-url4__struct{white-space:pre-wrap}
.sf-url4__pk{color:var(--sf-ink-3)}
.sf-url4__intent{font-size:12px;color:var(--sf-ink-2);background:var(--sf-surface);
  padding:4px 8px;margin-top:2px;white-space:pre-wrap;overflow-wrap:anywhere}
.sf-url4__output{margin-top:6px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px}
.sf-url4__raw{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;
  color:var(--sf-ink-3);white-space:pre-wrap;overflow-wrap:anywhere;
  margin:8px 0 0;background:transparent;border:0;padding:0}
</style>"""
)


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


def model_card_html(model: Model) -> str:
    """Render one Model as a branded card of its real authoring fields."""

    fields = "".join(
        (
            _field("route", f"<span class='sf-mono'>{escape(model.model)}</span>"),
            _field("provider", escape(_provider_of(model.model))),
            _field("prompt", escape(model.prompt), wide=True),
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
        f"{_recipe_html(fusion.url4)}</div>"
    )


def benchmark_card_html(benchmark: Benchmark) -> str:
    """Render one Benchmark as a branded card of its real definition fields."""

    tools = ", ".join(tool.id for tool in benchmark.tools) or "none"
    tool_calls = "—" if benchmark.max_tool_calls is None else str(benchmark.max_tool_calls)
    fields = "".join(
        (
            _field("id", f"<span class='sf-mono'>{escape(benchmark.id)}</span>"),
            _field("grader", escape(benchmark.grader.kind.replace("_", " "))),
            _field("aggregator", escape(benchmark.aggregator.kind.replace("_", " "))),
            _field("max tool calls", escape(tool_calls)),
            _field("tools", f"<span class='sf-mono'>{escape(tools)}</span>", wide=True),
        )
    )
    return (
        f"{_STYLE}<div class='sf-ui sf-card' aria-label='ScreamingFace benchmark'>"
        f"<div class='sf-card__head'><span class='sf-card__title'>{escape(benchmark.title)}</span>"
        "<span class='sf-card__kicker'>benchmark</span></div>"
        f"<div class='sf-card__grid'>{fields}</div></div>"
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
            _field("model", f"<span class='sf-mono'>{escape(rubric.model)}</span>"),
            _field("passes", str(rubric.passes)),
            _field("params", _params_text(rubric.params), wide=True),
            _field("prompt", escape(rubric.prompt), wide=True),
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
