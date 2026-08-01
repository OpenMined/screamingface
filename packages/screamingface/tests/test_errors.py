from __future__ import annotations

import pytest

import screamingface as sf


@pytest.mark.parametrize(
    "error",
    [
        sf.ScreamingFaceError("An expected SDK operation failed"),
        sf.AuthenticationError(
            "SF Engine authentication is required",
            code="authentication_required",
            status=401,
            permanent=True,
        ),
        sf.PlanningError(
            "Could not load the Benchmark manifest",
            code="engine_contract_error",
            permanent=False,
        ),
        sf.ExecutionError(
            "SF Engine WebSocket disconnected",
            code="websocket_disconnected",
            permanent=False,
        ),
        sf.ProviderConnectionError(
            "The provider connection was rejected",
            provider="openrouter",
            code="connection_rejected",
            status=401,
            permanent=True,
        ),
    ],
)
def test_every_handled_error_has_concise_ipython_rendering(
    error: sf.ScreamingFaceError,
) -> None:
    cause = RuntimeError("low-level implementation detail")

    try:
        raise error from cause
    except sf.ScreamingFaceError as caught:
        rendered = "".join(caught._render_traceback_())

    assert rendered.startswith(f"{type(error).__name__}: {error}")
    assert "low-level implementation detail" not in rendered
    assert "Traceback" not in rendered
    assert error.__cause__ is cause
    assert isinstance(error.code, str) and error.code
    assert f"Code: {error.code}" in rendered
    assert error.retryable is (None if error.permanent is None else not error.permanent)


def test_handled_error_renders_an_actionable_hint_and_code() -> None:
    error = sf.EngineUnavailableError(
        "Could not reach the SF Engine provider connections",
        engine_url="http://127.0.0.1:9108",
    )

    assert error.code == "engine_unreachable"
    assert error.engine_url == "http://127.0.0.1:9108"
    assert error.permanent is False
    assert error.retryable is True
    assert isinstance(error, sf.ScreamingFaceError)
    assert not isinstance(error, sf.ProviderConnectionError)
    assert error.user_message == (
        "Could not reach the SF Engine provider connections\n\n"
        "Hint: Start the local Engine with `uv run url4-cloud serve --local`, "
        "or configure a different `engine_url`."
    )
    assert "EngineUnavailableError: Could not reach" in "".join(error._render_traceback_())
    assert "Code: engine_unreachable" in "".join(error._render_traceback_())


def test_public_error_categories_have_stable_fallback_codes() -> None:
    assert sf.ScreamingFaceError("failed").code == "screamingface_error"
    assert sf.AuthenticationError("failed").code == "authentication_failed"
    assert sf.PlanningError("failed").code == "planning_failed"
    assert sf.ExecutionError("failed").code == "execution_failed"
    assert sf.ProviderConnectionError("failed").code == "provider_connection_failed"


def test_programmer_errors_keep_normal_python_tracebacks() -> None:
    assert not hasattr(ValueError("invalid argument"), "_render_traceback_")
