"""``GET /v1/benchmarks`` — the benchmark catalog, and the manifests it indexes.

Unlike `/v1/models`, which proxies aigateway per caller, these two routes are identical for every
caller: a manifest describes a benchmark, not an entitlement, and holds nothing private (the
weighted rubrics behind `routes.criteria` are never declared as a route and never appear here).
That is what makes the responses `public`-cacheable rather than `private`, and what makes the
validator a plain content hash rather than something scoped to an identity.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Path
from fastapi.responses import JSONResponse, Response

from url4_cloud import manifests

router = APIRouter()

# Manifests change only with a release, and a stale one costs a caller nothing worse than an
# out-of-date description — but `must-revalidate` keeps a cache from serving one past its TTL, so
# a corrected judge or route reaches callers on the next request rather than whenever a cache
# feels like it.
_CACHE_CONTROL = "public, max-age=300, must-revalidate"

_PROBLEM_JSON = "application/problem+json"

_LIST_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"description": "Every published benchmark manifest, summarised."},
    304: {"description": "The catalog is unchanged since the supplied `If-None-Match`."},
}
_MANIFEST_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {"description": "The manifest, verbatim, as `text/plain`."},
    304: {"description": "The manifest is unchanged since the supplied `If-None-Match`."},
    404: {"description": "No manifest is published under that id.", "content": {_PROBLEM_JSON: {}}},
}


def _matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 §13.1.2 — `If-None-Match` is a LIST, and `*` matches any existing representation.

    Comparison is weak per the RFC, so `W/"x"` matches `"x"`; we only ever emit strong tags, but a
    cache is free to relay a weakened one back.
    """
    if not if_none_match:
        return False
    for candidate in if_none_match.split(","):
        value = candidate.strip()
        if value == "*" or value.removeprefix("W/") == etag.removeprefix("W/"):
            return True
    return False


def _catalog() -> list[dict[str, str]]:
    return [
        {
            "id": key,
            "title": manifests.field(text, "title") or key,
            "description": manifests.field(text, "description") or "",
            "href": f"/v1/benchmarks/{key}",
        }
        for key, text in sorted(manifests.MANIFESTS.items())
    ]


@router.get(
    "/v1/benchmarks",
    tags=["Catalog"],
    summary="List the published benchmark manifests",
    responses=_LIST_RESPONSES,
    description=(
        "Summarise every benchmark this deployment publishes: its id, title, description, and a "
        "link to the full manifest.\n\n"
        "The response is an OBJECT, not a bare array, so a `next_cursor` can be added without "
        "breaking clients. The set is fixed at build time and small, so it is not paginated "
        "today."
    ),
)
async def list_benchmarks(
    if_none_match: Annotated[
        str | None, Header(alias="If-None-Match", description="Conditional-request validator.")
    ] = None,
) -> Response:
    """Summarise every published benchmark, with a link to each full manifest."""
    entries = _catalog()
    # Derived from the summaries rather than the manifest bodies: this validator must change when
    # what THIS route returns changes, and a body edit that leaves title/description alone does
    # not alter the catalog.
    etag = manifests.etag_of(repr(entries))
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse({"benchmarks": entries}, headers=headers)


@router.get(
    "/v1/benchmarks/{benchmark_id}",
    tags=["Catalog"],
    summary="Fetch one benchmark manifest",
    response_class=Response,
    responses=_MANIFEST_RESPONSES,
    description=(
        "Return the manifest verbatim as `text/plain`.\n\n"
        "The manifest IS a string — wrapping it in JSON would only make every caller unescape it "
        "back. It names the data routes the benchmark's cases and criteria are served from, the "
        "judge and its grading protocol, and the tools a candidate may use."
    ),
)
async def get_benchmark_manifest(
    benchmark_id: Annotated[
        str, Path(description="The manifest's `id`, as listed by `GET /v1/benchmarks`.")
    ],
    if_none_match: Annotated[
        str | None, Header(alias="If-None-Match", description="Conditional-request validator.")
    ] = None,
) -> Response:
    """Return one manifest verbatim as `text/plain`, or 404 if no such benchmark is published."""
    # INVARIANT: a registry lookup, never a path join. The id is a dict key, so a traversal-shaped
    # id is simply absent rather than dangerous — there is no filesystem behind this route.
    text = manifests.MANIFESTS.get(benchmark_id)
    if text is None:
        return JSONResponse(
            status_code=404,
            media_type=_PROBLEM_JSON,
            content={
                "type": "about:blank",
                "title": "Unknown benchmark",
                "status": 404,
                # The id is echoed so a caller can tell a typo from an unpublished benchmark. It
                # is caller-supplied, and FastAPI serialises it as a JSON string value, so it
                # cannot break out of the field.
                "detail": f"no manifest is published under {benchmark_id!r}",
            },
        )
    etag = manifests.etag_of(text)
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)
