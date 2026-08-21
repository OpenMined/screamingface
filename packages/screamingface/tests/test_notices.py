from __future__ import annotations

import pytest

from screamingface._notices import ClientNotice


def test_client_notice_has_stable_machine_and_human_representations() -> None:
    notice = ClientNotice(
        code="partial_submission",
        severity="warning",
        title="Partial submission",
        body="This score is not directly comparable with a full-run score.",
    )

    assert notice.message == (
        "Partial submission. This score is not directly comparable with a full-run score."
    )


@pytest.mark.parametrize("severity", ["error", "success", "", 1, None])
def test_client_notice_rejects_unknown_severities(severity: object) -> None:
    with pytest.raises((TypeError, ValueError), match="severity"):
        ClientNotice(
            code="partial_submission",
            severity=severity,  # type: ignore[arg-type]
            title="Partial submission",
            body="Comparison caveat.",
        )


@pytest.mark.parametrize("field", ["code", "title", "body"])
def test_client_notice_rejects_empty_identity_or_copy(field: str) -> None:
    values = {
        "code": "partial_submission",
        "severity": "warning",
        "title": "Partial submission",
        "body": "Comparison caveat.",
    }
    values[field] = "   "

    with pytest.raises(ValueError, match=field):
        ClientNotice(**values)  # type: ignore[arg-type]
