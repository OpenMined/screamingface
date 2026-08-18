"""The cache policy's two published contracts describe themselves (plan Batch 8).

FEATURE: a run's cache intent has two carriers — the `Cache-Control` request header on `GET /`
and the `cache` field on the `ai.url4.attach` frame — and a client discovers each from a
different document. A carrier nobody can find is a carrier nobody uses, which leaves the whole
feature to be discovered by reading screamingface-engine's source.

STORY: as an SDK author I can read `/openapi.json` and `/asyncapi.json` and learn that caching is
ON by default, how to turn it off on either carrier, and which one wins when both speak.

These are served artifacts, not prose: `/openapi.json` and `/asyncapi.json` are
endpoints, so the documents are part of the app's behaviour and testable as such.
`apps/screamingface-engine/README.md` is prose and is deliberately NOT asserted
here — pinning wording would make an editorial improvement a red build.
"""

from __future__ import annotations

from screamingface_engine.app import create_app
from screamingface_engine.schemas.asyncapi import build_asyncapi


def _get_root_header(name: str) -> dict:
    parameters = create_app().openapi()["paths"]["/"]["get"]["parameters"]
    return next(p for p in parameters if p["in"] == "header" and p["name"] == name)


# ── the HTTP carrier ──────────────────────────────────────────────────────────────────────


def test_the_cache_control_header_is_a_documented_parameter_of_the_run_start() -> None:
    # Regression pin on the ingress contract itself: the parameter is what a generated client
    # turns into a callable argument, so losing it silently removes the carrier from every SDK.
    parameter = _get_root_header("Cache-Control")

    assert parameter["required"] is False
    assert parameter["description"]


def test_the_cache_control_parameter_names_every_directive_it_honours() -> None:
    # Each of these maps to a DIFFERENT outcome at the url4 edge, and a caller guessing between
    # them pays for the guess in cache hits.
    description = _get_root_header("Cache-Control")["description"]

    for directive in ("no-store", "no-cache", "max-age", "url4-use-cache"):
        assert directive in description, f"undocumented directive: {directive}"


def test_the_api_description_explains_response_caching() -> None:
    # The parameter description says what the directives do; the API description is where a
    # reader learns the two facts that are NOT visible from one parameter — that caching is on by
    # default, and that a second carrier exists on the WebSocket.
    description = create_app().openapi()["info"]["description"]

    assert "Cache-Control" in description
    assert "ai.url4.attach" in description


# ── the WebSocket carrier ─────────────────────────────────────────────────────────────────


def test_the_attach_frame_schema_carries_the_cache_field() -> None:
    schemas = build_asyncapi()["components"]["schemas"]

    assert "cache" in schemas["AttachData"]["properties"]
    assert schemas["AttachData"]["properties"]["cache"]["description"]
    assert schemas["CachePolicy"]["properties"].keys() == {"participate", "max_age"}


def test_the_asyncapi_description_explains_the_attach_frames_cache_field() -> None:
    # The schema says the field EXISTS; nothing in it can say that the first attach wins, or that
    # the HTTP header overrides this frame — both are properties of the exchange, which is what
    # this document's description is for.
    description = build_asyncapi()["info"]["description"]

    assert "cache" in description
    assert "Cache-Control" in description
