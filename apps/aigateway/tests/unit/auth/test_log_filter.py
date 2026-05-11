from __future__ import annotations

import logging

from uvicorn.logging import AccessFormatter

from aigateway.core.auth.log_filter import (
    RedactProvisioningTokenFilter,
    install_provisioning_token_redaction,
)


def test_redacts_provisioning_token_header(caplog) -> None:
    logger = logging.getLogger("aigateway.test.redact")
    logger.addFilter(RedactProvisioningTokenFilter())
    token = "super-secret-token"
    with caplog.at_level(logging.INFO, logger="aigateway.test.redact"):
        logger.info("X-Aigw-Provisioning-Token: %s", token)
    assert token not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_does_not_redact_plain_header_name_mentions() -> None:
    record = logging.LogRecord(
        "aigateway.test.redact",
        logging.INFO,
        "",
        1,
        "Checking X-Aigw-Provisioning-Token header presence",
        (),
        None,
    )
    RedactProvisioningTokenFilter().filter(record)
    assert record.getMessage() == "Checking X-Aigw-Provisioning-Token header presence"


def test_process_wide_redaction_handles_child_loggers(caplog) -> None:
    install_provisioning_token_redaction()
    logger = logging.getLogger("aigateway.routes.accounts.child")
    token = "super-secret-token"
    with caplog.at_level(logging.INFO):
        logger.info("X-Aigw-Provisioning-Token: %s", token)
    assert token not in caplog.text
    assert token not in "\n".join(record.getMessage() for record in caplog.records)
    assert "[REDACTED]" in caplog.text


def test_redacts_raw_asgi_header_tuple(caplog) -> None:
    install_provisioning_token_redaction()
    logger = logging.getLogger("third_party.asgi")
    token = "tuple-secret-token"
    with caplog.at_level(logging.INFO):
        logger.info("headers=%r", [(b"x-aigw-provisioning-token", token.encode())])
    assert token not in caplog.text
    assert token not in "\n".join(record.getMessage() for record in caplog.records)
    assert "[REDACTED]" in caplog.text


def test_redacts_structured_header_args_without_rendering_first() -> None:
    token = "structured-secret-token"
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        "headers=%r extra=%r raw=%r",
        (
            [[b"x-aigw-provisioning-token", token.encode()]],
            {"X-Aigw-Provisioning-Token": token, "safe": "value"},
            b"X-Aigw-Provisioning-Token: byte-secret",
        ),
        None,
    )

    RedactProvisioningTokenFilter().filter(record)

    assert token not in record.getMessage()
    assert "byte-secret" not in record.getMessage()
    assert "safe" in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_ignores_non_header_keys_in_structured_args() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        "value=%r",
        ({b"not-the-provisioning-header": "kept", "nested": ("ok",)},),
        None,
    )

    RedactProvisioningTokenFilter().filter(record)

    assert "kept" in record.getMessage()
    assert "ok" in record.getMessage()


def test_preserves_uvicorn_access_log_args() -> None:
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:12345", "GET", "/healthz", "1.1", 200),
        None,
    )
    RedactProvisioningTokenFilter().filter(record)

    assert record.args == ("127.0.0.1:12345", "GET", "/healthz", "1.1", 200)
    formatted = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s').format(
        record
    )
    assert "GET /healthz HTTP/1.1" in formatted
