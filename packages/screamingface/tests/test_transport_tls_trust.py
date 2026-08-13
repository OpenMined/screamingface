"""Both halves of the transport verify against the same roots.

The Client reaches one Engine two ways — HTTPS for the capability and the catalog, a
WebSocket for the Run stream — and they used to disagree about which certificate
authorities to trust. `httpx` resolves `SSL_CERT_FILE`, then `SSL_CERT_DIR`, and otherwise
falls back to the `certifi` bundle installed with this package; `websockets`, given no
context, trusts OpenSSL's own CA paths. They agree while those environment variables are
set and diverge in the default case, which is the common one.

Where they disagree the Run mints its capability over HTTPS and then fails to open a
WebSocket to the SAME host with `SSLCertVerificationError`. A python.org macOS build whose
`Install Certificates.command` was never run has nothing in OpenSSL's paths at all — and
because a local Engine is `ws://`, the split never appeared except against a hosted one.

Self-contained by design (sdlc rule 5).
"""

from __future__ import annotations

import httpx

from screamingface._engine.transport import _websocket_ssl_context


def test_the_websocket_trusts_exactly_what_the_http_half_trusts() -> None:
    # STORY: as a researcher on a hosted Engine, my Run does not die at the handshake for a
    # certificate the very same process just accepted moments earlier over HTTPS.
    context = _websocket_ssl_context("https://fusion.example.ai")

    assert context is not None
    assert context.get_ca_certs() == httpx.create_ssl_context().get_ca_certs()


def test_the_websocket_trust_store_is_not_empty() -> None:
    # The failure this guards is not "the wrong roots" but "no roots at all": an unconfigured
    # OpenSSL store verifies nothing and rejects every certificate presented to it.
    context = _websocket_ssl_context("https://fusion.example.ai")

    assert context is not None
    assert context.get_ca_certs(), "the WebSocket would trust nothing and refuse every Engine"


def test_a_local_engine_over_plain_http_is_given_no_context() -> None:
    # `websockets` refuses an SSL context on a `ws://` URI, so local mode must get None —
    # and this is why the trust split never showed up against a local Engine.
    assert _websocket_ssl_context("http://127.0.0.1:9108") is None
