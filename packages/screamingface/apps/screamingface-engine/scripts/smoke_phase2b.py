"""No-mock smoke checks for a running Phase 2B Docker stack."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ENGINE_URL = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404").rstrip("/")


def _get(path: str, expression: str | None = None) -> tuple[int, str]:
    query = "" if expression is None else "?" + urllib.parse.urlencode({"q": expression})
    request = urllib.request.Request(f"{ENGINE_URL}{path}{query}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=130) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def main() -> None:
    health_status, health = _get("/healthz")
    assert (health_status, health) == (200, "ok")

    expression = (
        "(member_answers={member_1:'A',member_2:'B',member_3:'A'},"
        "recipe_answer=/reducers/majority-vote($member_answers),"
        "{schema:'screamingface.recipe-result.v1',answer:'$recipe_answer'})"
    )
    reducer_status, reducer_body = _get("/v1", expression)
    assert reducer_status == 200, reducer_body
    assert json.loads(reducer_body) == {
        "schema": "screamingface.recipe-result.v1",
        "answer": "A",
    }

    model_status, model_body = _get(
        "/codex/gpt-5.5",
        "(What is 2 + 2?)!'Answer briefly'",
    )
    if model_status == 200:
        assert model_body.strip(), "model route returned blank success text"
        gateway_result = "provider-backed model response received"
    else:
        assert model_status == 502, model_body
        assert "AI Gateway returned HTTP" in model_body, model_body
        gateway_result = "engine surfaced the credential-free AI Gateway response"

    print("Phase 2B Docker smoke passed:")
    print("- complete URL4 reducer expression returned the exact winner")
    print(f"- {gateway_result}")


if __name__ == "__main__":
    main()
