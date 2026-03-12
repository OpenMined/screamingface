"""Mock url4 executor with caching.

The real url4 execution will be implemented later. For now, this returns
a static enrichment prompt that includes the url4 URL for traceability.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cache: dict[str, str] = {}


async def resolve_url4_context(url4_url: str) -> str:
    """Resolve a url4 URL to a context string, using a module-level cache."""
    if url4_url in _cache:
        return _cache[url4_url]
    result = await _execute_url4(url4_url)
    _cache[url4_url] = result
    return result


async def _execute_url4(url4_url: str) -> str:
    """Execute a url4 URL and return the resulting prompt.

    This is the seam — replace with real implementation later.
    Signature stays: async (str) -> str.
    """
    logger.info("Resolving url4 context (mock): %s", url4_url)
    return f"You are working on a project managed by ScreamingFace. Context source: {url4_url}"


def clear_cache() -> None:
    """Clear the url4 resolution cache. Intended for testing."""
    _cache.clear()
