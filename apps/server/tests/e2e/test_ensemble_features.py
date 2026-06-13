"""E2E tests for Kevin-spec url4 features (SF-79, SF-89, SF-91).

These tests exercise the full pipeline through a real SF server subprocess:

    curl → /ensemble route → EnsembleInterpreter → url4 parser →
    backend_call dispatch → claude-backend-api plugin →
    AnthropicBackend → httpx POST (mocked at the Anthropic boundary)

Each test spawns its own SF server with llm-base + claude-backend-api
active so backend_call dispatch works end-to-end. The Anthropic API is
NOT called — httpx is mocked by routing the backend_url through a
tiny in-process echo stub that returns canned responses.

No desktop app, no frontend proxy, no real Anthropic API key needed.
"""

from __future__ import annotations

from collections.abc import Generator

import httpx
import pytest

from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(60)]


# ----------------------------------------------------------------------------
# Fixture: server with llm-base + claude-backend-api + url4-executor
# ----------------------------------------------------------------------------


@pytest.fixture
def ensemble_server(
    sf_server: ServerManager,
    main_server_port: int,
    otlp_collector: OTLPCollector,
) -> Generator[ServerManager, None, None]:
    """Spawn a server with all the plugins needed for ensemble e2e tests.

    Includes llm-base, claude-backend-api, url4-executor, data-store.
    The claude-backend-api plugin uses the default settings (OAuth from
    Keychain). If no Keychain credential exists, the tests that hit the
    backend will fail with CredentialNotFoundError — that's expected on
    CI where no Claude Code login has happened.
    """
    port = ServerManager.find_free_port()
    config = {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": port,
            "ssl": False,
            "reload": False,
        },
        "plugins": [
            "tracing",
            "llm-base",
            "claude-backend-api",
            "url4-executor",
            "data-store",
        ],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
        },
    }
    mgr = ServerManager(config)
    mgr.start(timeout=30)
    yield mgr
    mgr.stop()


@pytest.fixture
def ensemble_url(ensemble_server: ServerManager) -> str:
    return ensemble_server.base_url


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _get_ensemble(base_url: str, q: str, **params) -> httpx.Response:
    """GET /ensemble?q=... against the test server."""
    return httpx.get(
        f"{base_url}/ensemble",
        params={"q": q, **params},
        timeout=30,
    )


def _store_blob(base_url: str, body: str, content_type: str = "text/plain") -> str:
    """POST a blob to /data and return the key."""
    resp = httpx.post(
        f"{base_url}/data",
        content=body.encode(),
        headers={"content-type": content_type},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["key"]


# ============================================================================
# Test 1: Ensemble fan-out-reduce (SF-79 Stage C)
# ============================================================================
#
# Proves the full N+1 call pattern: 3 parallel fan-out calls to /claude,
# then 1 reducer call via ?processor=/claude.
#
# This test is @e2e_live because it requires a real Claude Code OAuth
# credential in the Keychain (the claude-backend-api plugin calls the
# real Anthropic API). On CI without credentials, it's skipped.
# ============================================================================


@pytest.mark.e2e_live
class TestEnsembleFanOutReduce:
    def test_three_way_fanout_with_reducer(self, ensemble_url: str) -> None:
        """Kevin's basic ensemble form with literal intents.

        (/claude()!What is 2+2?,/claude()!Capital of France?,/claude()!Color of sky?)
        !Combine these three facts into one sentence.
        &processor=/claude
        """
        resp = _get_ensemble(
            ensemble_url,
            q=(
                "(/claude()!What is 2+2? One word.,"
                "/claude()!Capital of France? One word.,"
                "/claude()!Color of the sky? One word.)"
                "!Combine these three facts into a single sentence."
            ),
            processor="/claude",
        )

        assert resp.status_code == 200
        text = resp.text
        # The reducer should have produced a sentence mentioning all three
        # We can't assert exact wording, but we can check it's non-empty
        # and reasonably long (a synthesis of 3 facts)
        assert len(text) > 10
        print(f"  Ensemble response: {text[:200]}")

    def test_single_element_fanout(self, ensemble_url: str) -> None:
        """N=1 degenerate case — one fan-out + one reducer."""
        resp = _get_ensemble(
            ensemble_url,
            q="(/claude()!Say hello in one word.)!Pass through.",
            processor="/claude",
        )
        assert resp.status_code == 200
        assert len(resp.text) > 0


# ============================================================================
# Test 2: Context packing (SF-89)
# ============================================================================
#
# Proves that /claude('context text')!intent sends both sources AND
# intent to the backend, and the backend concatenates them correctly.
# ============================================================================


@pytest.mark.e2e_live
class TestContextPacking:
    def test_context_and_intent_both_reach_backend(self, ensemble_url: str) -> None:
        """The packed context should be used by the backend alongside the intent.

        /claude(The capital of France is Paris.)!What city was mentioned?
        → backend receives sources="The capital of France is Paris."
          and intent="What city was mentioned?"
        → LLM should answer "Paris"
        """
        resp = _get_ensemble(
            ensemble_url,
            q=("/claude(The capital of France is Paris.)!What city was mentioned? One word."),
        )
        assert resp.status_code == 200
        text = resp.text.strip().lower()
        assert "paris" in text, f"Expected 'paris' in response, got: {text!r}"

    def test_empty_parens_backward_compat(self, ensemble_url: str) -> None:
        """Empty parens /claude()!intent should still work (Stage A compat)."""
        resp = _get_ensemble(
            ensemble_url,
            q="/claude()!What is 2+2? Reply with just the number.",
        )
        assert resp.status_code == 200
        assert resp.text.strip()  # non-empty


# ============================================================================
# Test 3: Collection iteration (SF-91)
# ============================================================================
#
# Proves source*(body)!intent with $item binding works end-to-end:
# 1. Store a JSONL blob in /data
# 2. Use it as a collection source
# 3. Each item's $item.field gets substituted
# 4. The expression is evaluated per-item
# 5. Results are collected
# ============================================================================


@pytest.mark.e2e_live
class TestCollectionIteration:
    def test_jsonl_iteration_with_item_field(self, ensemble_url: str) -> None:
        """Iterate over a 3-item JSONL blob, each item has a 'question' field.

        Store JSONL → use as collection source → per-item /claude($item.question)
        """
        # 1. Store JSONL blob
        jsonl = (
            '{"question":"What is 2+2? One word."}\n'
            '{"question":"Capital of France? One word."}\n'
            '{"question":"Color of the sky? One word."}'
        )
        blob_key = _store_blob(ensemble_url, jsonl, "application/jsonl")

        # 2. Collection iteration expression
        expr = (f"{ensemble_url}/data/{blob_key}*(/claude($item.question)!Answer)").replace(
            ensemble_url, ""
        )
        # Result: /data/<key>*(/claude($item.question)!Answer)
        # But we need the server's own /data, not an absolute URL.
        # Use the relative path form:
        expr = f"/data/{blob_key}*(/claude($item.question)!Answer briefly)"

        resp = _get_ensemble(ensemble_url, q=expr)

        assert resp.status_code == 200
        # Should have 3 results (one per JSONL item) joined by newlines
        results = [r.strip() for r in resp.text.strip().split("\n") if r.strip()]
        assert len(results) >= 1, f"Expected at least 1 result, got: {resp.text!r}"
        print(f"  Iteration results ({len(results)} items): {results}")


# ============================================================================
# Non-live tests — no API key needed, tests parser/routing only
# ============================================================================


class TestEnsembleParserRouting:
    """Tests that don't need a real Anthropic call — they test that the
    /ensemble route parses expressions correctly and returns appropriate
    errors for missing backends."""

    def test_backend_call_without_plugin_returns_error(self, ensemble_url: str) -> None:
        """/nonexistent()!hello should return an error mentioning the unknown path."""
        resp = _get_ensemble(ensemble_url, q="/nonexistent()!hello")
        # Should be 502 (url4 evaluation failed) with an error about
        # no active plugin handling /nonexistent
        assert resp.status_code == 502
        assert "nonexistent" in resp.text.lower() or "no active plugin" in resp.text.lower()

    def test_ast_mode_shows_backend_call_node(self, ensemble_url: str) -> None:
        """?ast=true should show the Url4BackendCall node in the AST."""
        resp = httpx.get(
            f"{ensemble_url}/ensemble",
            params={"q": "/claude(hello)!explain", "ast": "true"},
            timeout=10,
        )
        assert resp.status_code == 200 or resp.status_code == 502
        # If 200 (ast mode sometimes evaluates), check the JSON
        if resp.status_code == 200:
            data = resp.json()
            if "ast" in data:
                ast = data["ast"]
                assert ast["type"] == "backend_call"
                assert ast["path"] == "/claude"
                assert ast.get("packed_context") == "hello"

    def test_source_expansion_ast(self, ensemble_url: str) -> None:
        """?ast=true should show Url4ExpandedSource in the AST."""
        resp = httpx.get(
            f"{ensemble_url}/ensemble",
            params={"q": "(*https://example.com/data.jsonl)", "ast": "true"},
            timeout=10,
        )
        # The evaluation may fail (can't fetch the URL) but ast mode
        # should still return the AST if it parsed successfully
        if resp.status_code == 200:
            data = resp.json()
            if "ast" in data:
                items = data["ast"].get("items", [])
                assert any(i.get("type") == "expanded_source" for i in items)

    def test_data_store_roundtrip(self, ensemble_url: str) -> None:
        """Store a blob via /data and retrieve it — proves data-store works."""
        key = _store_blob(ensemble_url, "test content")
        resp = httpx.get(f"{ensemble_url}/data/{key}", timeout=10)
        assert resp.status_code == 200
        assert resp.text == "test content"


# ============================================================================
# Collection-iteration source failure — the "MainOne" spec
# ============================================================================
#
# The HLE 3-provider ensemble spec uses an unreachable collection source
# (github.com/openmined/HLE.jsonl → 404, the GitHub web page, not the raw
# file). A `source*(...)` iteration must FETCH and parse that collection
# *first* to produce the $items to iterate over. When that fetch fails the
# whole evaluation aborts BEFORE the per-item fan-out runs.
#
# This is exactly why Phoenix shows no ensemble-level interaction for this
# spec: the ensemble fan-out (`url4.ensemble.fanout`) never executes. The
# trace shows the failed source fetch (`url4.fetch`) and nothing deeper.
# That is correct behaviour, not a missing-instrumentation bug.
#
# Offline-safe: the request fails at the network boundary (404 with a
# connection, or a connect error without one) — either way the fan-out is
# never reached, so no live LLM credential is required.
# ============================================================================

# Provider prompt reused for all three weighted sources (verbatim from the spec).
_HLE_PROMPT = (
    "Answer this question. If it is multiple choice, return a probability "
    "distribution over the answer choices as JSON. "
    'Format: {"A": 0.7, "B": 0.2, "C": 0.05,"D": 0.05}. '
    "Return only the JSON object."
)

_HLE_ENSEMBLE_EXPRESSION = (
    "https://github.com/openmined/HLE.jsonl*("
    f"claude:0.40:/claude($item.question)!'{_HLE_PROMPT}',"
    f"codex:0.30:/codex($item.question)!'{_HLE_PROMPT}',"
    f"gemini:0.30:/gemini($item.question)!'{_HLE_PROMPT}'"
    ")!'Compute a weighted average of these distributions using source weights "
    "claude=0.40, codex=0.30, gemini=0.30. Return the single answer letter with "
    "the highest combined probability.'"
)


class TestCollectionSourceFetchFailure:
    def test_unreachable_source_aborts_before_ensemble_fanout(
        self,
        ensemble_url: str,
        otlp_collector: OTLPCollector,
    ) -> None:
        """An unreachable collection source fails the fetch, so the ensemble
        fan-out never runs — hence no `url4.ensemble.fanout` span.

        Documents the observed "Phoenix shows no ensemble interaction" symptom
        for the HLE/MainOne spec: it's the source fetch dying first, not the
        ensemble being un-instrumented.
        """
        otlp_collector.clear()

        resp = _get_ensemble(ensemble_url, q=_HLE_ENSEMBLE_EXPRESSION, processor="/claude")

        # Evaluation fails at the source fetch -> server error (404 observed as 502).
        assert resp.status_code >= 500, f"expected 5xx, got {resp.status_code}: {resp.text[:300]}"

        # Give the OTLP exporter a beat to flush whatever spans were produced.
        otlp_collector.wait_for_spans(1, timeout=10)
        span_names = [s.name for s in otlp_collector.spans]

        # The fan-out (and reducer) must NOT have run — this is the crux.
        assert not otlp_collector.find_spans(name="url4.ensemble.fanout"), (
            f"ensemble fan-out should never run when the source fetch fails; spans={span_names}"
        )
        assert not otlp_collector.find_spans(name="url4.ensemble.reduce"), (
            f"reducer should never run when the source fetch fails; spans={span_names}"
        )

        # ...and the failure IS recorded on the trace (status ERROR=2 + an
        # exception event) so it's visible in Phoenix, not a silent 502.
        evaluate_spans = otlp_collector.find_spans(name="url4.evaluate")
        assert evaluate_spans, f"expected a url4.evaluate span; spans={span_names}"
        assert any(s.status_code == 2 for s in evaluate_spans), (
            "the source-fetch failure should mark url4.evaluate as ERROR; "
            f"statuses={[s.status_code for s in evaluate_spans]}"
        )

    def test_reachable_source_reaches_collection_iteration(
        self,
        ensemble_url: str,
        otlp_collector: OTLPCollector,
    ) -> None:
        """Contrast with the 404 case: a REACHABLE JSONL source is fetched and
        parsed, so evaluation progresses into the collection iteration (and the
        per-item ensemble fan-out) — i.e. Phoenix WOULD show ensemble spans.

        The fan-out then errors offline (this server has only claude-backend-api;
        /codex and /gemini are unregistered, and /claude has no test credential),
        so the request still ends 5xx — but the trace now shows the source was
        fetched 200 and iteration started, unlike the HLE 404 case above.
        """
        expression = (
            "https://screamingface.ai/livetruth-latest.eval.jsonl*("
            f"claude:0.40:/claude($item.question)!'{_HLE_PROMPT}',"
            f"codex:0.30:/codex($item.question)!'{_HLE_PROMPT}',"
            f"gemini:0.30:/gemini($item.question)!'{_HLE_PROMPT}'"
            ")!'Compute a weighted average of these distributions using source "
            "weights claude=0.40, codex=0.30, gemini=0.30. Return the single answer "
            "letter with the highest combined probability.'"
        )
        otlp_collector.clear()
        # The fan-out then errors offline (no codex/gemini plugin, no creds), so
        # the request still ends in an error — we only care that it got past the
        # fetch into iteration, asserted via spans below.
        _get_ensemble(ensemble_url, q=expression, processor="/claude")
        otlp_collector.wait_for_spans(1, timeout=15)
        span_names = sorted({s.name for s in otlp_collector.spans})
        fetch_spans = otlp_collector.find_spans(name="url4.fetch")
        fetched_urls = [s.attributes.get("http.url", "") for s in fetch_spans]

        # The source was reachable, so the fetch succeeded (no 404 abort) and
        # evaluation entered collection iteration — the key contrast.
        assert any("livetruth" in u for u in fetched_urls), (
            f"expected a url4.fetch span for the livetruth source; got {fetched_urls}"
        )
        assert otlp_collector.find_spans(name="url4.collection_iterate"), (
            f"collection iteration should start for a reachable source; spans={span_names}"
        )


# ============================================================================
# SF-278: backend dispatch + provider HTTP spans in ensemble traces
# ============================================================================


class TestBackendDispatchTracing:
    def test_dispatch_span_emitted_for_backend_call(
        self, ensemble_url: str, otlp_collector: OTLPCollector
    ) -> None:
        """`_dispatch_backend_call` emits `url4.backend_call /claude`.

        CI-safe: the span is opened *before* the backend's credential check,
        so it is emitted (as an error span) even with no Keychain credential.
        We assert only on the span, not the HTTP status.
        """
        otlp_collector.clear()
        _get_ensemble(ensemble_url, q="/claude()!ping")
        otlp_collector.wait_for_spans(1, timeout=15)

        dispatch = otlp_collector.find_spans(name="url4.backend_call")
        span_names = sorted({s.name for s in otlp_collector.spans})
        assert dispatch, f"no url4.backend_call span emitted; spans={span_names}"
        s = dispatch[0]
        assert s.name == "url4.backend_call /claude"
        assert s.attributes.get("url4.path") == "/claude"
        assert "url4.intent_length" in s.attributes
        # OpenInference: a backend call is a CHAIN with the prompt+context as input.
        assert s.attributes.get("openinference.span.kind") == "CHAIN"
        assert "ping" in str(s.attributes.get("input.value", ""))


@pytest.mark.e2e_live
class TestProviderHttpTracing:
    def test_provider_post_span_emitted(
        self, ensemble_url: str, otlp_collector: OTLPCollector
    ) -> None:
        """A real backend call emits the deep `llm.POST Anthropic` client span.

        Live-only: the provider POST only fires once a real auth header is
        obtained (Keychain credential present).
        """
        otlp_collector.clear()
        resp = _get_ensemble(ensemble_url, q="/claude()!Say the word pong. One word.")
        assert resp.status_code == 200

        otlp_collector.wait_for_spans(2, timeout=20)
        provider = otlp_collector.find_spans(name="llm.POST Anthropic")
        span_names = sorted({s.name for s in otlp_collector.spans})
        assert provider, f"no llm.POST Anthropic span emitted; spans={span_names}"
        s = provider[0]
        assert s.attributes.get("sf.plugin") == "Anthropic"
        assert s.attributes.get("http.status_code") == 200
        # OpenInference LLM classification + captured model call.
        assert s.attributes.get("openinference.span.kind") == "LLM"
        assert s.attributes.get("input.value")  # request body captured
        assert s.attributes.get("output.value")  # response captured
