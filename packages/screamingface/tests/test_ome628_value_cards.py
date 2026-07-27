"""OME-628 — _repr_html_ cards for Connection, Case, and Rubric.

FEATURE: notebook rich display for the remaining small public value objects.
STORY: as a researcher, I inspect a connection, a case, or a rubric grader in a cell and see a
branded card instead of a bare dataclass repr.
INVARIANT: cards render only real fields the object holds — never fabricated metrics; injected
text is HTML-escaped.
"""

from __future__ import annotations

import screamingface as sf
from screamingface.connections import Connection

_FABRICATED = ("context window", "ability", "tok/s", "tokens/s", "$/m", "price")


def test_connection_repr_html_shows_real_state() -> None:
    connection = Connection(
        provider="gemini",
        display_name="Google Gemini",
        auth_methods=("oauth", "api_key"),
        status="connected",
        auth_method="api_key",
        account_label="researcher@example.com",
    )

    html = connection._repr_html_()

    assert "class='sf-ui" in html
    assert "Google Gemini" in html
    assert "gemini" in html
    assert "connected" in html
    assert "api_key" in html
    assert "researcher@example.com" in html
    lowered = html.lower()
    for banned in _FABRICATED:
        assert banned not in lowered


def test_connection_card_escapes_injected_account_label() -> None:
    connection = Connection(
        provider="gemini",
        display_name="Google Gemini",
        auth_methods=("api_key",),
        status="connected",
        auth_method="api_key",
        account_label="<script>alert(1)</script>",
    )

    html = connection._repr_html_()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_case_repr_html_shows_id_input_reference_metadata() -> None:
    case = sf.Case("c1", "What is 2+2?", reference="4", metadata={"topic": "math"})

    html = case._repr_html_()

    assert "class='sf-ui" in html
    assert "c1" in html
    assert "What is 2+2?" in html
    assert "4" in html  # reference
    assert "topic" in html and "math" in html  # metadata


def test_case_card_escapes_injected_input() -> None:
    case = sf.Case("c1", "<script>alert(1)</script>", reference="4")

    html = case._repr_html_()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_rubric_repr_html_shows_model_prompt_passes_params() -> None:
    rubric = sf.graders.Rubric(
        model="gemini/3.1-pro-preview",
        prompt="Judge the answer.",
        passes=3,
        params={"temperature": 0.0},
    )

    html = rubric._repr_html_()

    assert "class='sf-ui" in html
    assert "gemini/3.1-pro-preview" in html
    assert "Judge the answer." in html
    assert "3" in html  # passes
    assert "temperature" in html and "0.0" in html
    lowered = html.lower()
    for banned in _FABRICATED:
        assert banned not in lowered


def test_rubric_card_escapes_injected_prompt() -> None:
    rubric = sf.graders.Rubric(model="gemini/3.1-pro-preview", prompt="<script>alert(1)</script>")

    html = rubric._repr_html_()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
