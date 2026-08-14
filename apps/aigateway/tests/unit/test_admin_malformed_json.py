"""OME-387 regression coverage for malformed JSON on the admin surface."""

from __future__ import annotations

from ipaddress import ip_network

from fastapi.testclient import TestClient

ADMIN = "admin@openmined.org"


def test_admin_malformed_json_returns_sanitized_422(client) -> None:
    client.app.state.settings.auth_mode = "cloudflare_headers"
    client.app.state.settings.allowed_networks = (ip_network("10.0.0.0/8"),)
    client.app.state.settings.admin_emails = frozenset({ADMIN})
    admin_client = TestClient(client.app, client=("10.1.2.3", 50000))
    marker = "raw-api-secret-marker"

    response = admin_client.post(
        "/v1/admin/accounts",
        content=f'{{"email":"{marker}"',
        headers={"Content-Type": "application/json", "X-User-Email": ADMIN},
    )

    assert response.status_code == 422
    # INVARIANT: malformed request bytes can contain credentials and never echo to the caller.
    assert marker not in response.text
