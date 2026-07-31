"""The benchmarks installed in this url4-cloud deployment."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["Catalog"])


class BenchmarkEntry(BaseModel):
    """One addressable benchmark in the Engine catalogue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    object: Literal["benchmark"] = "benchmark"


class BenchmarkList(BaseModel):
    """The OpenAI-style list envelope shared with ``GET /v1/models``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    object: Literal["list"] = "list"
    default: str | None
    data: tuple[BenchmarkEntry, ...]


@router.get("/v1/benchmarks")
def list_benchmarks(request: Request) -> BenchmarkList:
    """Return installed IDs and the explicitly configured evaluation default."""

    return BenchmarkList(
        default=request.app.state.default_benchmark,
        data=tuple(BenchmarkEntry(id=value) for value in request.app.state.benchmarks),
    )


@router.get("/v1/benchmarks/{benchmark_id}/manifest", response_class=Response)
def benchmark_manifest(benchmark_id: str, request: Request) -> Response:
    """Return the immutable YAML descriptor used by the Client compiler."""

    benchmark = request.app.state.benchmarks.get(benchmark_id)
    if benchmark is None:
        raise HTTPException(status_code=404, detail=f"unknown benchmark {benchmark_id!r}")
    return Response(content=benchmark.manifest, media_type="application/yaml")


__all__ = ["router"]
