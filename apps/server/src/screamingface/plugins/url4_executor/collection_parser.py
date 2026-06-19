"""Collection parser — split fetched content into a list of items.

Used by SF-92 (source expansion) and SF-91 (collection iteration) to
parse the body of a fetched URL/blob into individual items.

Supports three formats, detected by content inspection:

1. **JSON array** — body starts with ``[``. Each element becomes a string
   (JSON-encoded if it's an object/array, bare if it's a string/number).
2. **JSONL** — body contains newlines and each non-empty line is valid JSON.
   Each line becomes one item.
3. **CSV** — body contains commas and the first line looks like a header.
   Each row (after the header) becomes a JSON object string keyed by
   column names.

The parser is intentionally simple — it handles the three formats Kevin
specified and nothing else. Complex formats should be pre-processed
into one of these three before being used in url4 expressions.
"""

from __future__ import annotations

import csv
import io
import json
import logging

logger = logging.getLogger(__name__)


def parse_collection(body: str) -> list[str]:
    """Parse *body* into a list of string items.

    Auto-detects the format (JSON array, JSONL, CSV) based on content.
    Returns a list of strings — each string is one "item" from the
    collection. For structured items (JSON objects, CSV rows), the
    string is a JSON-encoded representation so downstream consumers
    can parse individual fields with ``json.loads()``.

    Raises ``ValueError`` if the body cannot be parsed as any
    supported format.
    """
    body = body.strip()
    if not body:
        return []

    # Reject HTML loudly. An HTML page served where a data file was expected is
    # the signature of a soft-404 / SPA fallback (e.g. a missing dataset URL
    # resolving to the marketing site's index). Without this guard the plain-text
    # fallback below would turn each HTML line into an "item", silently producing
    # a 0-accuracy "degraded" run instead of a clear failure (SF-292).
    if body[:512].lstrip().lower().startswith(("<!doctype html", "<html")):
        raise ValueError(
            "collection source returned an HTML page, not a data file "
            "(JSON array, JSONL, or CSV expected) — the dataset URL is likely "
            "missing or misrouted to an HTML fallback"
        )

    # Try JSON array first
    if body.startswith("["):
        try:
            data = json.loads(body)
            if isinstance(data, list):
                return [_item_to_str(item) for item in data]
        except json.JSONDecodeError:
            pass

    # Try JSONL (each line is a JSON value)
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    if lines and _looks_like_jsonl(lines):
        items = []
        for line in lines:
            try:
                parsed = json.loads(line)
                items.append(_item_to_str(parsed))
            except json.JSONDecodeError:
                # Not valid JSONL — fall through to CSV
                break
        else:
            return items

    # Try CSV (first line = header, subsequent lines = rows)
    if "," in body and len(lines) >= 2:
        try:
            reader = csv.DictReader(io.StringIO(body))
            items = []
            for row in reader:
                items.append(json.dumps(dict(row)))
            if items:
                return items
        except csv.Error:
            pass

    # Fallback: treat each non-empty line as a plain text item
    return [line for line in lines if line]


def _item_to_str(item) -> str:
    """Convert a parsed JSON item to a string representation.

    - Strings are returned as-is (no extra quoting).
    - Numbers, booleans, null are JSON-encoded.
    - Objects and arrays are JSON-encoded.
    """
    if isinstance(item, str):
        return item
    return json.dumps(item)


def _looks_like_jsonl(lines: list[str]) -> bool:
    """Heuristic: does the content look like JSONL?

    Returns True if at least the first line starts with ``{`` or ``[``
    or is a JSON primitive (quoted string, number, boolean, null).
    """
    if not lines:
        return False
    first = lines[0].strip()
    if first.startswith(("{", "[", '"')):
        return True
    # Check for JSON primitives
    try:
        json.loads(first)
        return True
    except json.JSONDecodeError:
        return False
