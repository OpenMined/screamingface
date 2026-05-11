from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor


def _assert_secret_not_logged(caplog, secret: str) -> None:
    assert secret not in caplog.text
    assert secret not in "\n".join(record.getMessage() for record in caplog.records)


def test_create_account_success_and_duplicate(client, caplog) -> None:
    headers = {"X-Aigw-Provisioning-Token": "p" * 32}
    with caplog.at_level(logging.INFO, logger="aigateway.routes.accounts"):
        response = client.post(
            "/v1/accounts",
            headers=headers,
            json={"username": "alice", "password": "alicepass123", "display_name": "Alice"},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "alice"
    assert "password" not in body
    assert "password_hash" not in body
    assert "account_created username=alice" in caplog.text
    _assert_secret_not_logged(caplog, headers["X-Aigw-Provisioning-Token"])

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="aigateway.routes.accounts"):
        duplicate = client.post(
            "/v1/accounts",
            headers=headers,
            json={"username": "alice", "password": "alicepass123"},
        )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "username already exists"
    assert "provisioning_token_rejected status_code=409 username=alice" in caplog.text
    _assert_secret_not_logged(caplog, headers["X-Aigw-Provisioning-Token"])


def test_missing_and_wrong_provisioning_token_match(client, caplog) -> None:
    payload = {"username": "alice", "password": "alicepass123"}
    wrong_token = "wrong-token-value"
    with caplog.at_level(logging.INFO, logger="aigateway.routes.accounts"):
        missing = client.post("/v1/accounts", json=payload)
        wrong = client.post(
            "/v1/accounts",
            headers={"X-Aigw-Provisioning-Token": wrong_token},
            json=payload,
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert wrong.content == missing.content
    assert wrong.json()["detail"]["code"] == "invalid_provisioning_token"
    assert caplog.text.count("provisioning_token_rejected status_code=401") == 2
    _assert_secret_not_logged(caplog, wrong_token)


def test_provisioning_disabled_returns_503(client, caplog) -> None:
    client.app.state.settings.provisioning_token = None
    token = "p" * 32
    with caplog.at_level(logging.INFO, logger="aigateway.routes.accounts"):
        response = client.post(
            "/v1/accounts",
            headers={"X-Aigw-Provisioning-Token": token},
            json={"username": "alice", "password": "alicepass123"},
        )
    assert response.status_code == 503
    assert "Provisioning is disabled" in response.text
    assert "provisioning_token_rejected status_code=503" in caplog.text
    _assert_secret_not_logged(caplog, token)


def test_create_account_validation(client, caplog) -> None:
    headers = {"X-Aigw-Provisioning-Token": "p" * 32}
    with caplog.at_level(logging.INFO, logger="aigateway.routes.accounts"):
        short = client.post(
            "/v1/accounts", headers=headers, json={"username": "a", "password": "x"}
        )
        missing = client.post("/v1/accounts", headers=headers, json={"username": "a"})
        overlong = client.post(
            "/v1/accounts",
            headers=headers,
            json={"username": "a", "password": "a" * 73},
        )
    assert short.status_code == 422
    assert missing.status_code == 422
    assert overlong.status_code == 422
    assert "password" in missing.text
    assert caplog.text.count("provisioning_token_rejected status_code=422") == 3
    _assert_secret_not_logged(caplog, headers["X-Aigw-Provisioning-Token"])


def test_created_account_can_login(client) -> None:
    client.post(
        "/v1/accounts",
        headers={"X-Aigw-Provisioning-Token": "p" * 32},
        json={"username": "alice", "password": "alicepass123"},
    )
    response = client.post(
        "/v1/auth/login",
        json={"username": "alice", "password": "alicepass123"},
    )
    assert response.status_code == 200
    assert response.json()["token"]


def test_concurrent_duplicate_username_returns_409(client) -> None:
    headers = {"X-Aigw-Provisioning-Token": "p" * 32}

    def _create() -> int:
        return client.post(
            "/v1/accounts",
            headers=headers,
            json={"username": "alice", "password": "alicepass123"},
        ).status_code

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: _create(), range(4)))

    assert sorted(statuses) == [201, 409, 409, 409]


def test_provisioning_token_not_logged(client, caplog) -> None:
    token = "p" * 32
    client.post(
        "/v1/accounts",
        headers={"X-Aigw-Provisioning-Token": token},
        json={"username": "alice", "password": "alicepass123"},
    )
    assert token not in caplog.text
    assert token not in "\n".join(record.getMessage() for record in caplog.records)
