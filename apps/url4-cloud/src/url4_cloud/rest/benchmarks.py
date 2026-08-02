"""Benchmark discovery and the one-fetch Engine-owned expression resource."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import JSONResponse, Response

from url4_cloud.benchmarks import BENCHMARKS, DEFAULT_BENCHMARK_ID

router = APIRouter()

_CACHE_CONTROL = "public, max-age=300, must-revalidate"
_PROBLEM_JSON = "application/problem+json"


def _matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    return any(
        candidate.strip() == "*" or candidate.strip().removeprefix("W/") == etag.removeprefix("W/")
        for candidate in if_none_match.split(",")
    )


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def _response(value: object, if_none_match: str | None) -> Response:
    body = _json_bytes(value)
    etag = _etag(body)
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if _matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _catalog() -> list[dict[str, str]]:
    return [
        {
            "object": "benchmark",
            "id": benchmark.id,
            "title": benchmark.title,
            "description": benchmark.description,
            "href": f"/v1/benchmarks/{benchmark.id}",
        }
        for benchmark in sorted(BENCHMARKS.values(), key=lambda value: value.id)
    ]


@router.get(
    "/v1/benchmarks",
    tags=["Catalog"],
    summary="List the installed Benchmarks",
)
async def list_benchmarks(
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    return _response(
        {
            "object": "list",
            "default": DEFAULT_BENCHMARK_ID,
            "data": _catalog(),
        },
        if_none_match,
    )


@router.get(
    "/v1/benchmarks/{benchmark_id}",
    tags=["Catalog"],
    summary="Fetch one Engine-owned Benchmark expression",
)
async def get_benchmark(
    benchmark_id: Annotated[str, Path(description="A catalog Benchmark id, or 'default'.")],
    limit: Annotated[int | None, Query(ge=1, description="Maximum selected cases.")] = None,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    selected_id = DEFAULT_BENCHMARK_ID if benchmark_id == "default" else benchmark_id
    benchmark = BENCHMARKS.get(selected_id)
    if benchmark is None:
        return _problem(
            404,
            "Unknown benchmark",
            f"no Benchmark is installed under {benchmark_id!r}",
        )
    return _response(benchmark.resource(limit), if_none_match)


def _problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type=_PROBLEM_JSON,
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
        },
    )


__all__ = ["router"]
