"""The only model-execution boundary used by ScreamingFace."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from screamingface.compiler import fusion_result_schema, result_schema
from screamingface.errors import EngineError, EngineUnavailable
from screamingface.model_inputs import _FusionMember


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


@dataclass(frozen=True, slots=True)
class FusionResult:
    answers: tuple[str, ...]
    answer: str


def parse_panel_result(body: str, expected_members: tuple[_FusionMember, ...]) -> PanelResult:
    payload = _result_payload(body, result_schema())
    return PanelResult(_panel_answers(payload, expected_members))


def parse_fusion_result(
    body: str,
    expected_members: tuple[_FusionMember, ...],
    expected_reducer_model: str,
) -> FusionResult:
    payload = _result_payload(body, fusion_result_schema())
    answers = _panel_answers(payload, expected_members)
    if payload.get("reducer") != "model":
        raise EngineError(
            "URL4 engine fusion result must identify reducer 'model'",
            code="invalid_result",
        )
    reducer_model = payload.get("reducer_model")
    if reducer_model != expected_reducer_model:
        raise EngineError(
            f"URL4 engine fusion result identifies reducer model {reducer_model!r}; "
            f"expected {expected_reducer_model!r}",
            code="invalid_result",
        )
    answer = payload.get("answer")
    if not isinstance(answer, str):
        raise EngineError(
            "URL4 engine fusion result answer must be text",
            code="invalid_result",
        )
    return FusionResult(answers, answer)


def _result_payload(body: str, schema: str) -> dict:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EngineError(
            "URL4 engine returned a non-JSON panel result",
            code="invalid_result",
        ) from exc
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise EngineError(
            f"URL4 engine result must use schema {schema!r}",
            code="invalid_result",
        )
    return payload


def _panel_answers(payload: dict, expected_members: tuple[_FusionMember, ...]) -> tuple[str, ...]:
    answers: list[str] = []
    for index, expected_member in enumerate(expected_members, 1):
        slot_id = payload.get(f"panel_{index}_id")
        model = payload.get(f"panel_{index}_model")
        answer = payload.get(f"panel_{index}_answer")
        if slot_id != expected_member.id:
            raise EngineError(
                f"URL4 engine result panel_{index} identifies slot {slot_id!r}; "
                f"expected {expected_member.id!r}",
                code="invalid_result",
            )
        if model != expected_member.model:
            raise EngineError(
                f"URL4 engine result panel_{index} identifies {model!r}; "
                f"expected {expected_member.model!r}",
                code="invalid_result",
            )
        if not isinstance(answer, str):
            raise EngineError(
                f"URL4 engine result panel_{index}_answer must be text",
                code="invalid_result",
            )
        answers.append(answer)
    return tuple(answers)


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
