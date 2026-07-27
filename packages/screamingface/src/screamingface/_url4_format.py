"""Readable, collapsible rendering of a compiled URL4 recipe.

FEATURE: the Model/Fusion card recipe line becomes a structured, syntax-highlighted view.
INVARIANT: this is a display path — it must never raise. An unparseable recipe (or any
`url4.Url4Error`) degrades to the exact raw string, which is honest, not a fail-open.

Classes referenced here (`.sf-url4*`) are defined in `_card_display._STYLE`, which every card
prepends — this module emits only markup, never the stylesheet.
"""

from __future__ import annotations

from html import escape

import url4

# Fixed copy-button JS. WHY: the recipe text is read from the sibling hidden <pre> via
# textContent, so no recipe data is interpolated into this attribute — no injection surface and
# no JS-string escaping of arbitrary intents. event.stopPropagation keeps the click from toggling
# the surrounding <details>.
_COPY_JS = (
    "event.stopPropagation();"
    "navigator.clipboard&&navigator.clipboard.writeText("
    "this.closest('.sf-url4').querySelector('.sf-url4__raw').textContent);"
    "var b=this;b.textContent='copied';"
    "setTimeout(function(){b.textContent='copy';},1200);return false;"
)


def recipe_details_html(recipe_url4: str) -> str:
    """Render a compiled URL4 recipe as a collapsed-by-default details block with copy."""

    raw = escape(recipe_url4)
    structured = _structured_html(recipe_url4)
    if structured is not None:
        body = f"{structured}<pre class='sf-url4__raw' hidden>{raw}</pre>"
    else:
        # Fallback: show the raw recipe (also the copy source) when it cannot be parsed.
        body = f"<pre class='sf-url4__raw'>{raw}</pre>"
    copy = (
        "<button type='button' class='sf-url4__copy' title='Copy the url4 recipe' "
        f'onclick="{_COPY_JS}">copy</button>'
    )
    return (
        "<details class='sf-url4'>"
        "<summary class='sf-url4__summary'>"
        "<span class='sf-card__k'>url4 recipe</span>"
        f"{copy}</summary>"
        f"<div class='sf-url4__body'>{body}</div></details>"
    )


def _structured_html(recipe_url4: str) -> str | None:
    try:
        node = url4.build(recipe_url4)
    except url4.Url4Error:
        # WHY: never let a parser edge case break a repr — fall back to the raw string.
        return None
    if isinstance(node, url4.Expression):
        blocks = "".join(_source_html(source) for source in node.sources)
        return f"<div class='sf-url4__nodes'>{blocks}{_output_html(node.intent)}</div>"
    return f"<div class='sf-url4__nodes'>{_value_html(node)}</div>"


def _source_html(source: url4.Node) -> str:
    # Expression.sources is typed as Node; in practice each is a Source. Anything else is
    # rendered by its value path so an unexpected shape still displays instead of crashing.
    if not isinstance(source, url4.Source):
        return f"<div class='sf-url4__node'>{_value_html(source)}</div>"
    name = escape(source.name or "·")
    return (
        "<div class='sf-url4__node'>"
        f"<div class='sf-url4__nhead'><span class='sf-url4__name'>{name}</span>"
        f"{_weight_html(source.weight)}</div>"
        f"{_value_html(source.value)}</div>"
    )


def _weight_html(weight: object) -> str:
    if weight is None or weight == 0.0 or (isinstance(weight, dict) and not weight):
        return ""
    return f"<span class='sf-url4__weight'>weight {escape(str(weight))}</span>"


def _value_html(value: url4.Node) -> str:
    if isinstance(value, (url4.RelExpr, url4.RemoteExpr)):
        return _expr_html(value)
    if isinstance(value, url4.StructObject):
        return f"<div class='sf-url4__struct'>{escape(value.raw)}</div>"
    return f"<div class='sf-url4__leaf'>{escape(url4.render(value))}</div>"


def _expr_html(expr: url4.RelExpr | url4.RemoteExpr) -> str:
    authority = getattr(expr, "authority", None)
    route = f"//{authority}{expr.path}" if authority else expr.path
    parts = [f"<div class='sf-url4__route'>{escape(route)}</div>"]
    for key, value in expr.params:
        suffix = "" if value is None else f"<span class='sf-url4__pv'> = {escape(value)}</span>"
        parts.append(
            f"<div class='sf-url4__param'><span class='sf-url4__pk'>{escape(key)}</span>"
            f"{suffix}</div>"
        )
    if expr.context:
        parts.append(f"<div class='sf-url4__ctx'>context ({escape(expr.context)})</div>")
    if expr.intent is not None:
        parts.append(f"<div class='sf-url4__intent'>{escape(_intent_text(expr.intent))}</div>")
    return "".join(parts)


def _output_html(intent: url4.Node | None) -> str:
    if intent is None:
        return ""
    return (
        "<div class='sf-url4__output'><span class='sf-card__k'>output</span> "
        f"<span class='sf-mono'>{escape(_intent_text(intent))}</span></div>"
    )


def _intent_text(intent: url4.Node) -> str:
    return intent.value if isinstance(intent, url4.Text) else url4.render(intent)


__all__ = ["recipe_details_html"]
