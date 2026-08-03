"""Benchmark discovery and the one-fetch Engine-owned expression resource."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import JSONResponse, Response

from url4_cloud.auth import PROBLEM_MEDIA_TYPE
from url4_cloud.benchmarks import BENCHMARKS, DEFAULT_BENCHMARK_ID, assets_root
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


def _etag(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()[:32]


def _response(value: object, if_none_match: str | None) -> Response:
    body = _json_bytes(value)
    etag = _etag(body)
    headers = {"ETag": f'"{etag}"', "Cache-Control": _CACHE_CONTROL}
    if validator_matches(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _catalog() -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for benchmark in sorted(BENCHMARKS.values(), key=lambda value: value.id):
        entry: dict[str, object] = {
            "object": "benchmark",
            "id": benchmark.id,
            "title": benchmark.title,
            "description": benchmark.description,
            "href": f"/v1/benchmarks/{benchmark.id}",
        }
        if benchmark.methods:
            # Additive: single-protocol entries stay byte-identical.
            entry["methods"] = list(benchmark.method_names())
            entry["default_method"] = benchmark.default_method
        entries.append(entry)
    return entries


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
    method: Annotated[
        str | None,
        Query(description="Execution method; omitted means the Benchmark's default."),
    ] = None,
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
    if method is not None and method not in benchmark.method_names():
        return _problem(
            404,
            "Unknown method",
            f"Benchmark {selected_id!r} has no method {method!r}",
        )
    return _response(benchmark.resource(limit, method=method), if_none_match)


class _CasesUnavailableError(Exception):
    """The prepared cases asset is missing or unusable on this control plane."""


@router.get(
    "/v1/benchmarks/{benchmark_id}/cases",
    tags=["Catalog"],
    summary="Read one page of a Benchmark's cases",
)
async def list_benchmark_cases(
    benchmark_id: Annotated[str, Path(description="A catalog Benchmark id, or 'default'.")],
    limit: Annotated[int, Query(ge=1, le=200, description="Page size.")] = 50,
    offset: Annotated[int, Query(ge=0, description="Cases to skip.")] = 0,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Response:
    # FEATURE: benchmark researcher discovery (OME-723) — the SDK and the future web
    # frontend read real prompts through this one paginated contract before evaluating.
    selected_id = DEFAULT_BENCHMARK_ID if benchmark_id == "default" else benchmark_id
    benchmark = BENCHMARKS.get(selected_id)
    if benchmark is None:
        return _problem(
            404,
            "Unknown benchmark",
            f"no Benchmark is installed under {benchmark_id!r}",
        )
    try:
        rows = _case_rows(selected_id)
    except _CasesUnavailableError as exc:
        # WHY: a control plane deployed without the assets must fail loudly with the
        # node-route error code — an empty list would read as "benchmark has no cases".
        return _problem(
            503,
            "Benchmark unavailable",
            str(exc),
            code="benchmark_unavailable",
        )
    return _response(
        {
            "object": "list",
            "benchmark": selected_id,
            "revision": benchmark.revision,
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "data": rows[offset : offset + limit],
        },
        if_none_match,
    )


def _case_rows(benchmark_id: str) -> list[dict[str, object]]:
    """Read the family's prepared ``cases.json`` down to ``id`` + ``input`` rows.

    INVARIANT (answer-key discipline): exactly ``id`` and ``input`` pass through —
    every other prepared column (e.g. draco's ``domain``) stays inside the Engine.
    """
    path = assets_root(os.environ) / benchmark_id / "cases.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise _CasesUnavailableError(
            f"could not read the prepared cases for {benchmark_id!r}: {exc}"
        ) from exc
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise _CasesUnavailableError(
            f"the prepared cases for {benchmark_id!r} are not JSON: {exc}"
        ) from exc
    if not isinstance(value, list):
        raise _CasesUnavailableError(f"the prepared cases for {benchmark_id!r} must be an array")
    rows: list[dict[str, object]] = []
    for index, row in enumerate(value):
        if not isinstance(row, Mapping) or "id" not in row or "input" not in row:
            raise _CasesUnavailableError(
                f"prepared case {index} for {benchmark_id!r} lacks the id/input contract"
            )
        rows.append({"id": row["id"], "input": row["input"]})
    return rows


def _problem(status: int, title: str, detail: str, *, code: str | None = None) -> JSONResponse:
    content: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
    }
    if code is not None:
        content["code"] = code
    return JSONResponse(
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        content=content,
    )


__all__ = ["router"]
