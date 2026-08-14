"""Discovery for flat, Engine-owned executable Benchmark resources."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request
from fastapi.responses import Response

from url4_cloud.auth import ProblemException
from url4_cloud.benchmarks import BenchmarkRegistry
from url4_cloud.rest.conditional import validator_matches

router = APIRouter()

_CACHE_CONTROL = "public, max-age=300, must-revalidate"


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _response(value: object, if_none_match: str | None) -> Response:
    body = _json_bytes(value)
    etag = hashlib.sha256(body).hexdigest()[:32]
    headers = {"ETag": f'"{etag}"', "Cache-Control": _CACHE_CONTROL}
    if validator_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _registry(request: Request) -> BenchmarkRegistry:
    return request.app.state.benchmarks


@router.get(
    "/v1/benchmarks",
    tags=["Catalog"],
    summary="List the installed Benchmarks",
)
async def list_benchmarks(
    request: Request,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    return _response(
        {"object": "list", "data": [benchmark.catalog_entry() for benchmark in _registry(request)]},
        if_none_match,
    )


@router.get(
    "/v1/benchmarks/{benchmark_id}",
    tags=["Catalog"],
    summary="Fetch one Engine-owned Benchmark expression",
)
async def get_benchmark(
    request: Request,
    benchmark_id: Annotated[str, Path(description="An explicit installed Benchmark id.")],
    limit: Annotated[int | None, Query(ge=1, description="Exact selected case count.")] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    benchmark = _registry(request).get(benchmark_id)
    if benchmark is None:
        raise ProblemException(
            status=404,
            title="Unknown benchmark",
            detail=f"no Benchmark is installed under {benchmark_id!r}",
        )
    if limit is not None and limit > benchmark.case_count:
        raise ProblemException(
            status=422,
            title="Invalid benchmark selection",
            detail=f"limit must be between 1 and {benchmark.case_count} for {benchmark.id!r}",
        )
    return _response(benchmark.resource(limit), if_none_match)


__all__ = ["router"]
