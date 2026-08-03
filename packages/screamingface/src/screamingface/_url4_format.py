"""Exact, quote-aware rich display for canonical URL4."""

from __future__ import annotations

from html import escape

_OPEN = "({"
_CLOSE = ")}"


def recipe_details_html(url4: str) -> str:
    """Render exact URL4 as collapsed, reflowed text with an exact copy source."""

    pretty = escape(_pretty_url4(url4))
    raw = escape(url4, quote=True)
    copy = (
        "<button type='button' class='sf-url4__copy' title='Copy URL4' "
        f'data-url4="{raw}" '
        'onclick="event.stopPropagation();navigator.clipboard&&navigator.clipboard.writeText('
        "this.getAttribute('data-url4'));var b=this;b.textContent='copied';"
        "setTimeout(function(){b.textContent='copy';},1200);return false;\">copy</button>"
    )
    return (
        "<details class='sf-url4'><summary class='sf-summary'>"
        "<span class='sf-card__k'>url4</span>"
        f"{copy}</summary><pre class='sf-url4__pre'>{pretty}</pre></details>"
    )


def _pretty_url4(text: str) -> str:
    """Add structural whitespace without changing quoted URL4 text."""

    output: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            index = _copy_quoted(text, index, output)
        elif char in _OPEN and index + 1 < len(text) and text[index + 1] in _CLOSE:
            output.append(char + text[index + 1])
            index += 2
        elif char in _OPEN:
            depth += 1
            output.append(char + "\n" + "  " * depth)
            index = _skip_space(text, index + 1)
        elif char in _CLOSE:
            depth = max(0, depth - 1)
            output.append("\n" + "  " * depth + char)
            index += 1
        elif char == ",":
            output.append(char + "\n" + "  " * depth)
            index = _skip_space(text, index + 1)
        else:
            output.append(char)
            index += 1
    return "".join(output)


def _copy_quoted(text: str, index: int, output: list[str]) -> int:
    output.append(text[index])
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            output.append(text[index : index + 2])
            index += 2
            continue
        output.append(char)
        index += 1
        if char == "'":
            break
    return index


def _skip_space(text: str, index: int) -> int:
    while index < len(text) and text[index] == " ":
        index += 1
    return index


__all__: list[str] = []
