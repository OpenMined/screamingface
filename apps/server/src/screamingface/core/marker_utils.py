"""Helpers for editing text files that carry marker-delimited blocks.

Several intercept plugins mutate files on the host system (``/etc/hosts``,
shell rc files) by appending a block of lines fenced by a pair of
comment markers. Removing that block later means scanning the file and
stripping every line from ``begin`` through ``end`` inclusive.

This helper is a single parameterized implementation of that scan so
each plugin no longer rolls its own.
"""

from __future__ import annotations


def strip_marker_block(content: str, begin: str, end: str) -> str:
    """Return ``content`` with every ``begin``...``end`` block removed.

    A line matches a marker when its right-stripped form equals the
    given marker string — this tolerates trailing whitespace / newlines.
    Both marker lines are themselves removed. Lines outside any block
    are preserved verbatim (original line endings included).
    """
    result: list[str] = []
    inside = False
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip()
        if stripped == begin:
            inside = True
            continue
        if stripped == end:
            inside = False
            continue
        if not inside:
            result.append(line)
    return "".join(result)
