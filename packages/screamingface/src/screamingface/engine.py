"""The only model-execution boundary used by ScreamingFace."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from screamingface.compiler import result_schema
from screamingface.errors import EngineError, EngineUnavailable


class EnginePort(Protocol):
    async def evaluate(self, expression: str) -> str: ...


@dataclass(slots=True)
class Url4EngineClient:
    """Send complete URL4 expressions to one engine evaluation endpoint."""

    base_url: str = "http://127.0.0.1:4404"
    eval_path: str = "/v1"
    timeout: float = 30.0
    client: httpx.AsyncClient | None = field(default=None, repr=False)

    async def evaluate(self, expression: str) -> str:
        url = f"{self.base_url.rstrip('/')}{self.eval_path}"
        owned = self.client is None
        client = self.client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.get(url, params={"q": expression})
        except httpx.HTTPError as exc:
            message = f"URL4 engine at {self.base_url} is unavailable: {exc}"
            raise EngineUnavailable(message) from exc
        finally:
            if owned:
                await client.aclose()
        if response.is_success:
            return response.text
        code, message = _error_details(response)
        raise EngineError(
            message,
            code=code,
            status_code=response.status_code,
            request_expression=expression,
        )


@dataclass(frozen=True, slots=True)
class PanelResult:
    answers: tuple[str, ...]


def parse_panel_result(body: str, expected_models: tuple[str, ...]) -> PanelResult:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EngineError(
            "URL4 engine returned a non-JSON panel result",
            code="invalid_result",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != result_schema():
        raise EngineError(
            f"URL4 engine result must use schema {result_schema()!r}",
            code="invalid_result",
        )
    answers: list[str] = []
    for index, expected_model in enumerate(expected_models, 1):
        model = payload.get(f"panel_{index}_model")
        answer = payload.get(f"panel_{index}_answer")
        if model != expected_model:
            raise EngineError(
                f"URL4 engine result panel_{index} identifies {model!r}; "
                f"expected {expected_model!r}",
                code="invalid_result",
            )
        if not isinstance(answer, str):
            raise EngineError(
                f"URL4 engine result panel_{index}_answer must be text",
                code="invalid_result",
            )
        answers.append(answer)
    return PanelResult(tuple(answers))


def _error_details(response: httpx.Response) -> tuple[str, str]:
    code = "engine_error"
    message = f"URL4 engine returned HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return code, message
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return code, message
    if isinstance(error.get("code"), str):
        code = error["code"]
    if isinstance(error.get("message"), str):
        message = error["message"]
    return code, message
