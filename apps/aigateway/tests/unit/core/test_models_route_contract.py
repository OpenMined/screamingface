"""Phase 2 (OME-479): /v1/models locked contract + canonical-id conformance.

Exercises the real registry through the app so the mechanism is proven across
every registered provider WITHOUT hardcoding any provider's inventory.
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi.testclient import TestClient

_LOCKED_FIELDS = {
    "id",
    "object",
    "owned_by",
    "supported_parameters",
    "supported_tools",
    "unsupported_parameter_behavior",
    "parameter_contract_url",
}


def _rows(client: TestClient) -> list[dict]:
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data, "at least one provider must contribute a model row"
    return data


def test_v1_models_rows_carry_locked_contract_fields(authenticated_client: TestClient) -> None:
    for row in _rows(authenticated_client):
        assert _LOCKED_FIELDS <= set(row)
        assert row["object"] == "model"
        assert row["unsupported_parameter_behavior"] == "reject"
        # deterministic, sorted, deduplicated arrays.
        for key in ("supported_parameters", "supported_tools"):
            assert isinstance(row[key], list)
            assert row[key] == sorted(row[key])
            assert len(row[key]) == len(set(row[key]))
        # same-origin relative URL whose query value round-trips to the id.
        url = row["parameter_contract_url"]
        assert url.startswith("/v1/model-parameters?model=")
        assert unquote(url.split("model=", 1)[1]) == row["id"]


def test_every_model_id_is_canonical_and_resolves_to_its_owner(
    authenticated_client: TestClient,
) -> None:
    for row in _rows(authenticated_client):
        # dispatchable unchanged: the chat route requires a provider prefix.
        assert "/" in row["id"]
        # resolves to the owning plugin (registry is keyed by provider); the
        # unique-registration invariant means this also proves no collision.
        assert row["id"].split("/", 1)[0] == row["owned_by"]


def test_anthropic_ids_are_provider_prefixed(authenticated_client: TestClient) -> None:
    anthropic_ids = [r["id"] for r in _rows(authenticated_client) if r["owned_by"] == "anthropic"]
    assert anthropic_ids, "anthropic provider should be registered with default models"
    assert all(mid.startswith("anthropic/") for mid in anthropic_ids)
    # AC#1: the previously-unprefixed display id is now canonical.
    assert "anthropic/claude-opus-4-8" in anthropic_ids
