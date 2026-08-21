"""A tiny, safe markdown-subset renderer for the untrusted model answer.

FEATURE: the answer in a Report is prose — headings, lists, emphasis, code — so it reads as
rendered markdown, not a literal `##`/`**`/`` ` `` dump in a monospace box.

INVARIANT: the input is UNTRUSTED model output. Every character is HTML-escaped BEFORE it is
placed in the output, and this module only ever emits its own fixed tag set — so a `<script>`
in the source can only ever become the inert text `&lt;script&gt;`, and a link is rendered as
an anchor only when its scheme is http(s)/mailto. Raw HTML never survives.

The supported subset is deliberately small (the panel is a summary, not a document viewer):
tamed headings (h4–h6), unordered/ordered lists, blockquotes, fenced + inline code,
`**bold**`/`*italic*` (asterisks only — see WHY below), safe links, and paragraphs.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape

__all__: list[str] = []

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_ITEM = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_ITEM = re.compile(r"^\s*\d+\.\s+(.*)$")
# WHY: only http(s)/mailto may become a live anchor — everything else (javascript:, data:, …)
# is left as inert escaped text so a crafted link can never carry an active scheme.
_SAFE_SCHEME = re.compile(r"^(?:https?:|mailto:)", re.IGNORECASE)

_CODE_SPAN = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
# WHY: emphasis is asterisks-only. Underscore emphasis would turn `estimator_test` and
# `__init__` in technical answers into mangled italics — a common, ugly false positive.
_ITALIC = re.compile(r"\*([^*]+)\*")
# The code-span placeholder uses NULs, which cannot occur in the escaped text (stripped below).
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def render_markdown(text: str) -> str:
    """Render an untrusted markdown string to safe HTML (see the module INVARIANT)."""

    if not text:
        return ""
    # Remove NULs up front so untrusted input can never forge a code-span placeholder.
    lines = text.replace("\x00", "").split("\n")
    parts: list[str] = []
    index = 0
    while index < len(lines):
        index, block = _next_block(lines, index)
        if block:
            parts.append(block)
    return "".join(parts)


def _next_block(lines: list[str], index: int) -> tuple[int, str]:
    """Consume ONE block starting at `index`, returning (next index, html; "" for a blank)."""

    line = lines[index]
    if not line.strip():
        return index + 1, ""
    for matches, consume in _BLOCK_RULES:
        if matches(line):
            return consume(lines, index)
    return _paragraph(lines, index)


def _heading(lines: list[str], index: int) -> tuple[int, str]:
    match = _HEADING.match(lines[index])
    if match is None:  # defensive — the rule predicate already matched this line
        return index + 1, ""
    level = min(3 + len(match.group(1)), 6)
    return index + 1, f"<h{level}>{_inline(escape(match.group(2).strip()))}</h{level}>"


def _fenced_code(lines: list[str], index: int) -> tuple[int, str]:
    """Consume a ``` fence (to its close, or to end-of-text if unclosed). No inline markup."""

    index += 1
    body: list[str] = []
    while index < len(lines) and lines[index].strip() != "```":
        body.append(lines[index])
        index += 1
    index += 1  # step past the closing fence (or harmlessly past the end)
    return index, f"<pre class='sf-md__pre'><code>{escape(chr(10).join(body))}</code></pre>"


def _list(lines: list[str], index: int, item: re.Pattern[str], tag: str) -> tuple[int, str]:
    items: list[str] = []
    while index < len(lines) and (match := item.match(lines[index])):
        items.append(f"<li>{_inline(escape(match.group(1).strip()))}</li>")
        index += 1
    return index, f"<{tag}>{''.join(items)}</{tag}>"


def _unordered(lines: list[str], index: int) -> tuple[int, str]:
    return _list(lines, index, _UL_ITEM, "ul")


def _ordered(lines: list[str], index: int) -> tuple[int, str]:
    return _list(lines, index, _OL_ITEM, "ol")


def _blockquote(lines: list[str], index: int) -> tuple[int, str]:
    rows: list[str] = []
    while index < len(lines) and lines[index].strip().startswith(">"):
        rows.append(_inline(escape(re.sub(r"^\s*>\s?", "", lines[index]))))
        index += 1
    return index, f"<blockquote>{'<br>'.join(rows)}</blockquote>"


def _is_block_start(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith(("```", ">"))
        or bool(_HEADING.match(line) or _UL_ITEM.match(line) or _OL_ITEM.match(line))
    )


def _paragraph(lines: list[str], index: int) -> tuple[int, str]:
    rows: list[str] = []
    while index < len(lines) and not _is_block_start(lines[index]):
        rows.append(_inline(escape(lines[index])))
        index += 1
    return index, f"<p>{'<br>'.join(rows)}</p>"


def _inline(text: str) -> str:
    """Inline spans over ALREADY-ESCAPED text: code, links, bold, italic.

    Code spans are pulled out first so markdown inside them stays literal, then restored last.
    """

    codes: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        codes.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = _CODE_SPAN.sub(_stash, text)
    text = _LINK.sub(_anchor, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return _PLACEHOLDER.sub(lambda match: codes[int(match.group(1))], text)


def _anchor(match: re.Match[str]) -> str:
    """A link becomes an anchor only for a safe scheme; otherwise its literal text is kept."""

    label, url = match.group(1), match.group(2)
    if not _SAFE_SCHEME.match(url):
        return match.group(0)
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'


# Ordered block rules: (does this line open the block?, consume it). First match wins; an
# unmatched line falls through to a paragraph in _next_block. Kept flat so the dispatcher
# stays a single loop rather than a return-per-block-type ladder.
_BLOCK_RULES: list[tuple[Callable[[str], bool], Callable[[list[str], int], tuple[int, str]]]] = [
    (lambda line: line.strip().startswith("```"), _fenced_code),
    (lambda line: _HEADING.match(line) is not None, _heading),
    (lambda line: _UL_ITEM.match(line) is not None, _unordered),
    (lambda line: _OL_ITEM.match(line) is not None, _ordered),
    (lambda line: line.strip().startswith(">"), _blockquote),
]
