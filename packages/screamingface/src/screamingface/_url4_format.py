"""Full-form, reflowed rendering of a compiled URL4 recipe.

FEATURE: the Model/Fusion card recipe becomes readable by indentation while keeping the EXACT
url4 text — nothing is extracted or paraphrased, only whitespace is added at structural
boundaries.
INVARIANT: reflow is quote- and escape-aware (url4 quotes with `\\\\` and `\\'`), so an intent
string's own `(){},` are never treated as structure. The result is rendered inside a <pre>,
which JupyterLab's MathJax skips — so `$member_*` references are shown literally, not typeset.
"""

from __future__ import annotations

from html import escape

_OPEN = "({"
_CLOSE = ")}"


def recipe_details_html(recipe_url4: str) -> str:
    """Render the recipe as a collapsed <details> with the full url4 reflowed in a <pre>."""

    pretty = escape(_pretty_url4(recipe_url4))
    # WHY: the copy source is the EXACT original (no added whitespace), carried in a data-
    # attribute so the fixed onclick JS interpolates no recipe text (no injection, no escaping
    # of the JS string). getAttribute returns the attribute value already HTML-unescaped.
    raw_attr = escape(recipe_url4, quote=True)
    copy = (
        "<button type='button' class='sf-url4__copy' title='Copy the url4 recipe' "
        f'data-url4="{raw_attr}" '
        'onclick="event.stopPropagation();navigator.clipboard&&navigator.clipboard.writeText('
        "this.getAttribute('data-url4'));var b=this;b.textContent='copied';"
        "setTimeout(function(){b.textContent='copy';},1200);return false;\">copy</button>"
    )
    return (
        "<details class='sf-url4'>"
        "<summary class='sf-summary'><span class='sf-card__k'>url4 recipe</span>"
        f"{copy}</summary>"
        f"<pre class='sf-url4__pre'>{pretty}</pre>"
        "</details>"
    )


def _pretty_url4(text: str) -> str:
    """Reflow url4 by indenting on (){} and top-level commas, preserving every character.

    Quote-aware: inside a `'…'` intent, `\\` escapes the next character and structural
    characters are copied verbatim.
    """

    out: list[str] = []
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        char = text[i]
        if char == "'":  # a quoted intent — copy verbatim, then resume structural reflow
            i = _copy_quoted(text, i, out)
        elif char in _OPEN and i + 1 < n and text[i + 1] in _CLOSE:
            out.append(char + text[i + 1])  # keep an empty () / {} inline
            i += 2
        elif char in _OPEN:
            depth += 1
            out.append(char + "\n" + "  " * depth)
            i = _skip_space(text, i + 1)
        elif char in _CLOSE:
            depth = max(0, depth - 1)
            out.append("\n" + "  " * depth + char)
            i += 1
        elif char == ",":
            out.append(char + "\n" + "  " * depth)
            i = _skip_space(text, i + 1)
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _copy_quoted(text: str, i: int, out: list[str]) -> int:
    """Copy a `'…'` span verbatim (honouring `\\` escapes); return the index past it."""

    out.append(text[i])
    i += 1
    n = len(text)
    while i < n:
        char = text[i]
        if char == "\\" and i + 1 < n:
            out.append(text[i : i + 2])  # an escaped char (e.g. \\' or \\\\) is never a delimiter
            i += 2
            continue
        out.append(char)
        i += 1
        if char == "'":
            break
    return i


def _skip_space(text: str, i: int) -> int:
    # Drop a single run of spaces right after a break so lines don't start with stray padding.
    while i < len(text) and text[i] == " ":
        i += 1
    return i


__all__ = ["recipe_details_html"]
