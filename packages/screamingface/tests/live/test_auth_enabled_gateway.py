"""Opt-in proof that sf.setup authenticates against an auth-enabled AI Gateway."""

from __future__ import annotations

import os

import pytest

import screamingface as sf

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("SCREAMINGFACE_AUTH_LIVE_TEST") != "1",
        reason="set SCREAMINGFACE_AUTH_LIVE_TEST=1 for an auth-enabled local gateway",
    ),
]


def test_username_password_setup_creates_authenticated_session() -> None:
    try:
        session = sf.setup(
            gateway=os.environ["SCREAMINGFACE_GATEWAY_URL"],
            username=os.environ.get("SCREAMINGFACE_GATEWAY_USERNAME", "admin"),
            password=os.environ["SCREAMINGFACE_GATEWAY_PASSWORD"],
            interactive=False,
        )

        assert isinstance(session, sf.Session)
        assert session.mode == "live"
        assert session.gateway_url == os.environ["SCREAMINGFACE_GATEWAY_URL"]
        assert isinstance(session.connections(), tuple)
    finally:
        sf.shutdown()
