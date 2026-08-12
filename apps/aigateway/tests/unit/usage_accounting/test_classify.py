"""OME-303 §9.20 — outcome classification is CORE-OWNED and provider-neutral.

The architecture rule (core never imports a plugin) is what makes this enforceable: no
provider can redefine what ``conversion_error`` means. These tests pin both halves — the
vocabulary is closed, and nothing provider- or attacker-controlled leaks into it.
"""

from __future__ import annotations

import httpx
import pytest

from aigateway.core.loader import load_plugins
from aigateway.core.registry import ProviderRegistry
from aigateway.core.usage_accounting._classify import (
    FAILURE_CODES,
    classify_conversion_failure,
    classify_transport_failure,
    outcome_for_status,
)


def _provider_taxonomy_terms(registry: ProviderRegistry) -> set[str]:
    terms: set[str] = set()
    for plugin in registry.all():
        for name in (plugin.custom_llm_provider, plugin.provider_display_name):
            normalized = "".join(
                character.lower() if character.isalnum() else " " for character in name
            )
            words = normalized.split()
            terms.add("".join(words))
            terms.add("_".join(words))
        provider_words = plugin.custom_llm_provider.replace("-", "_").split("_")
        terms.add(provider_words[0].lower())
    return terms


class TestOutcomeForStatus:
    @pytest.mark.parametrize("status", [200, 201, 204, 299])
    def test_two_hundreds_succeed(self, status: int) -> None:
        assert outcome_for_status(status) == "succeeded"

    @pytest.mark.parametrize("status", [300, 400, 401, 429, 500, 529, 599])
    def test_everything_else_valid_is_a_provider_error(self, status: int) -> None:
        assert outcome_for_status(status) == "provider_error"

    @pytest.mark.parametrize("status", [None, "200", 0, 99, 600, 1000, -1, 1.5, True, object()])
    def test_an_unvalidatable_status_is_indeterminate_not_a_failure(self, status: object) -> None:
        """A send with no validatable status produced no proof of what happened to it.

        It may have been received and billed, or never have arrived. Calling that
        ``provider_error`` would assert the provider rejected work it may well have
        performed; calling it ``succeeded`` is worse. ``indeterminate`` is the only
        honest answer, and Engine can treat it conservatively.
        """
        assert outcome_for_status(status) == "indeterminate"

    def test_boolean_true_is_not_read_as_status_one(self) -> None:
        # bool is an int subclass; a naive range check would let True through as 1.
        assert outcome_for_status(True) == "indeterminate"


class TestTransportFailureClassification:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (httpx.ConnectTimeout("x"), "transport_timeout"),
            (httpx.ReadTimeout("x"), "transport_timeout"),
            (httpx.WriteTimeout("x"), "transport_timeout"),
            (httpx.PoolTimeout("x"), "transport_timeout"),
            (httpx.ConnectError("x"), "transport_connect_error"),
            (httpx.ReadError("x"), "transport_read_error"),
            (httpx.RemoteProtocolError("x"), "transport_read_error"),
        ],
    )
    def test_real_httpx_exceptions_land_in_the_right_bucket(
        self, exc: BaseException, expected: str
    ) -> None:
        # INVARIANT: `ConnectTimeout` must read as a TIMEOUT, not a connect error —
        # "Timeout" is checked first precisely because the name contains both words.
        outcome, code = classify_transport_failure(exc)
        assert outcome == "transport_error"
        assert code == expected

    def test_an_unknown_exception_falls_back_without_raising(self) -> None:
        outcome, code = classify_transport_failure(RuntimeError("something odd"))
        assert (outcome, code) == ("transport_error", "transport_error")

    def test_the_exception_message_never_reaches_the_failure_code(self) -> None:
        """The single most important property here.

        ``str(exc)`` carries provider- and network-controlled text, and the failure code
        is published verbatim in the response. Classifying on the message would turn an
        upstream error string into a gateway output channel.
        """
        hostile = httpx.ConnectError("Bearer sk-ant-SECRET connecting to internal.host:5432")
        _outcome, code = classify_transport_failure(hostile)
        assert code == "transport_connect_error"
        assert "SECRET" not in code
        assert "internal.host" not in code

    def test_a_message_that_impersonates_another_category_is_ignored(self) -> None:
        # Classification is by TYPE. A ConnectError whose text says "Timeout" is still a
        # connect error — otherwise upstream text could steer our taxonomy.
        _outcome, code = classify_transport_failure(httpx.ConnectError("Timeout Read"))
        assert code == "transport_connect_error"

    def test_every_produced_code_is_in_the_closed_vocabulary(self) -> None:
        candidates: list[BaseException] = [
            httpx.ConnectTimeout("x"),
            httpx.ConnectError("x"),
            httpx.ReadError("x"),
            httpx.RemoteProtocolError("x"),
            RuntimeError("x"),
            ValueError("x"),
            OSError("x"),
        ]
        for exc in candidates:
            _outcome, code = classify_transport_failure(exc)
            assert code in FAILURE_CODES, f"{type(exc).__name__} produced an unvocabularied code"


class TestConversionFailure:
    def test_conversion_failure_is_its_own_outcome(self) -> None:
        """§9.20 — not a transport error and not a provider error.

        The provider already produced — and very likely BILLED — a response; only the
        gateway's own conversion of it failed. Collapsing it into ``provider_error``
        would tell Engine the provider rejected work it actually performed, and the
        operator would under-count real spend.
        """
        assert classify_conversion_failure() == ("conversion_error", "response_conversion_failed")

    def test_it_takes_no_provider_argument_at_all(self) -> None:
        # The strongest possible form of "provider-neutral": there is no seam through
        # which a provider could influence the answer.
        import inspect

        assert inspect.signature(classify_conversion_failure).parameters == {}

    def test_its_code_is_in_the_closed_vocabulary(self) -> None:
        _outcome, code = classify_conversion_failure()
        assert code in FAILURE_CODES


class TestTheVocabularyIsClosed:
    def test_compound_provider_names_contribute_individual_terms(self) -> None:
        registry = ProviderRegistry()
        load_plugins(registry)
        terms = _provider_taxonomy_terms(registry)
        assert "gemini-cli" not in terms
        assert "cli" not in terms
        assert "face" not in terms
        assert {"gemini", "geminicli", "gemini_cli", "huggingface", "hugging_face"} <= terms

    def test_no_provider_name_appears_in_any_failure_code(self) -> None:
        # A code naming a provider would mean the taxonomy had leaked out of core.
        registry = ProviderRegistry()
        load_plugins(registry)
        forbidden_terms = _provider_taxonomy_terms(registry) | {"litellm", "openai"}
        assert forbidden_terms > {"litellm", "openai"}, "the guard loaded no provider plugins"
        for code in FAILURE_CODES:
            lowered = code.lower()
            for term in forbidden_terms:
                assert term not in lowered

    def test_core_classification_does_not_import_any_plugin(self) -> None:
        # The repo architecture rule, asserted rather than assumed.
        import aigateway.core.usage_accounting._classify as classify_module

        source = classify_module.__file__
        assert source is not None
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        assert "plugins" not in text
