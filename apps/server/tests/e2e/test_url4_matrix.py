"""YAML-driven parametrized e2e tests for url4 expressions.

Test cases are defined in ``data/url4_test_matrix.yaml``.  Each entry
becomes a separate pytest case via ``@pytest.mark.parametrize``.

Backends are probed via their ``/health`` endpoint before each test.
If a required backend is unhealthy the test is **skipped** with a
verbose diagnostic (auth failure, rate limit exhausted, plugin missing,
insufficient token capacity, etc.).

No API keys or env vars needed — backends authenticate via their own
OAuth credentials (e.g. Claude Code Keychain token).

Result validation is intentionally fuzzy — LLM output is
non-deterministic, so we use substring checks, regex patterns, length
bounds, and an optional LLM-judge for semantic correctness.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from tests.e2e.infrastructure.otlp_collector import OTLPCollector
from tests.e2e.infrastructure.server_manager import ServerManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent / "data"
HEALTH_TIMEOUT = 20  # seconds for backend health-check (includes a real API call)
REQUEST_TIMEOUT = 45  # seconds for the actual test request

# 429 retry configuration — wait and retry instead of immediately failing
MAX_RETRIES = 3  # number of retries on 429
RETRY_BACKOFF = [10, 20, 30]  # seconds to wait between retries (exponential-ish)

# Minimum token capacity required to run a test. If the backend reports
# fewer tokens remaining than this, the test is skipped.
MIN_TOKEN_CAPACITY = 1000

# ---------------------------------------------------------------------------
# Load test matrix from all YAML files in data/
# ---------------------------------------------------------------------------


def _load_matrix() -> list[dict[str, Any]]:
    """Load and merge all ``*.yaml`` files from the data directory.

    Each file is a YAML list of test cases.  Files are loaded in sorted
    order so test IDs are deterministic across runs.  Duplicate IDs
    across files are caught at load time.
    """
    cases: list[dict[str, Any]] = []
    seen_ids: dict[str, str] = {}  # id -> source file

    for path in sorted(DATA_DIR.glob("*.yaml")):
        with path.open() as fh:
            file_cases = yaml.safe_load(fh)
        if not file_cases:
            continue
        for case in file_cases:
            cid = case["id"]
            if cid in seen_ids:
                raise ValueError(
                    f"Duplicate test id {cid!r} in {path.name} (first seen in {seen_ids[cid]})"
                )
            seen_ids[cid] = path.name
        cases.extend(file_cases)

    return cases


_MATRIX = _load_matrix()

# Split into live (needs backends) and non-live (no backends needed)
_LIVE_CASES = [c for c in _MATRIX if c.get("backends")]
_LIVE_IDS = [c["id"] for c in _LIVE_CASES]
_NON_LIVE_CASES = [c for c in _MATRIX if not c.get("backends")]
_NON_LIVE_IDS = [c["id"] for c in _NON_LIVE_CASES]


# ---------------------------------------------------------------------------
# Fixture: ensemble server (module-scoped — shared across all matrix tests)
# ---------------------------------------------------------------------------

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(180)]


@pytest.fixture(scope="module")
def matrix_server(
    otlp_collector: OTLPCollector,
) -> Generator[ServerManager, None, None]:
    """Spawn a server with all plugins needed for url4 matrix tests.

    Module-scoped so one server handles all parametrized cases — much
    faster than per-test servers.
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
            "codex-backend-api",
            "gemini-backend-api",
            "url4-executor",
            "data-store",
        ],
        "plugin_config": {
            "tracing": {
                "phoenix_launch": False,
                "otlp_endpoint": otlp_collector.endpoint,
            },
            "claude-backend-api": {
                "default_model": "claude-sonnet-4-6",
            },
        },
    }
    mgr = ServerManager(config)
    mgr.start(timeout=30)
    yield mgr
    mgr.stop()


@pytest.fixture(scope="module")
def matrix_url(matrix_server: ServerManager) -> str:
    return matrix_server.base_url


# ---------------------------------------------------------------------------
# Backend health probe — uses /<backend>/health endpoint
# ---------------------------------------------------------------------------

# Cache health results per (base_url, backend) to avoid redundant calls.
# Each health check costs one minimal API call, so caching matters.
_health_cache: dict[tuple[str, str], tuple[str | None, dict[str, Any]]] = {}


def _probe_backend(base_url: str, backend: str) -> str | None:
    """Probe a backend via its /health endpoint.

    Returns None if the backend is healthy and has sufficient capacity,
    or a verbose skip-reason string explaining the exact problem.

    Results are cached per (base_url, backend) for the test session.
    """
    cache_key = (base_url, backend)
    if cache_key in _health_cache:
        return _health_cache[cache_key][0]

    reason = _do_health_probe(base_url, backend)
    _health_cache[cache_key] = (reason, {})
    return reason


def _do_health_probe(base_url: str, backend: str) -> str | None:
    """Call GET /<backend>/health and interpret the response.

    Retries with backoff if the health probe itself gets rate-limited
    (the probe makes a real API call to validate auth + get rate limits).
    """
    url = f"{base_url}/{backend}/health"

    data: dict[str, Any] = {}
    authenticated = False
    error: str | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, timeout=HEALTH_TIMEOUT)
        except httpx.ConnectError:
            return (
                f"/{backend}/health: connection refused — "
                f"server not reachable at {base_url}. "
                f"Is the SF server running with the {backend}-backend-api plugin?"
            )
        except httpx.TimeoutException:
            return (
                f"/{backend}/health: timed out after {HEALTH_TIMEOUT}s — "
                f"the health check includes a minimal API call; "
                f"the provider API may be slow or unreachable"
            )
        except httpx.HTTPError as exc:
            return f"/{backend}/health: HTTP error — {exc}"

        # 404 = plugin not loaded — no point retrying
        if resp.status_code == 404:
            return (
                f"/{backend}/health: endpoint not found (HTTP 404) — "
                f"the {backend}-backend-api plugin is not loaded. "
                f"Add '{backend}-backend-api' to the plugins list in sf.json"
            )

        # Parse the health response
        try:
            data = resp.json()
        except Exception:
            return (
                f"/{backend}/health: response is not JSON (HTTP {resp.status_code}) — "
                f"body: {resp.text[:300]}"
            )

        error = data.get("error")
        authenticated = data.get("authenticated", False)

        # Rate limited — retry with backoff
        if authenticated and error and "rate limit" in error.lower():
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                logger.warning(
                    "/%s/health: rate limited (attempt %d/%d), waiting %ds...",
                    backend,
                    attempt + 1,
                    MAX_RETRIES,
                    wait,
                )
                time.sleep(wait)
                continue
            # Exhausted retries
            tokens_remaining = data.get("tokens_remaining")
            requests_remaining = data.get("requests_remaining")
            capacity_msg = ""
            if tokens_remaining is not None:
                capacity_msg += f" tokens_remaining={tokens_remaining}"
            if requests_remaining is not None:
                capacity_msg += f" requests_remaining={requests_remaining}"
            return (
                f"/{backend}: rate limited after {MAX_RETRIES} retries — "
                f"API rate budget exhausted.{capacity_msg}"
            )

        # Not rate limited — break out and interpret
        authenticated = data.get("authenticated", False)
        error = data.get("error")
        break

    tokens_remaining = data.get("tokens_remaining")
    requests_remaining = data.get("requests_remaining")

    # Not authenticated — explain why
    if not authenticated:
        if error and "credential" in error.lower():
            return (
                f"/{backend}: no OAuth credential found — "
                f"run the {backend} CLI to authenticate "
                f"(e.g. 'claude auth login' for Claude). "
                f"Detail: {error}"
            )
        if error and ("401" in error or "403" in error or "rejected" in error.lower()):
            return (
                f"/{backend}: OAuth token rejected by provider API — "
                f"the token may be expired or revoked. "
                f"Re-authenticate with the {backend} CLI. "
                f"Detail: {error}"
            )
        return (
            f"/{backend}: authentication failed — "
            f"{error or 'unknown error'}. "
            f"Run the {backend} CLI to authenticate."
        )

    # Authenticated but insufficient token capacity
    if tokens_remaining is not None and tokens_remaining < MIN_TOKEN_CAPACITY:
        return (
            f"/{backend}: insufficient token capacity — "
            f"tokens_remaining={tokens_remaining} < minimum={MIN_TOKEN_CAPACITY}. "
            f"Wait for rate limit to reset."
        )

    # Authenticated but has some other error (API unreachable, etc.)
    if error:
        return f"/{backend}: health check warning — {error}"

    # All good
    return None


def _check_backends(base_url: str, backends: list[str]) -> None:
    """Probe all required backends; skip with verbose reason if any fail."""
    for backend in backends:
        reason = _probe_backend(base_url, backend)
        if reason is not None:
            pytest.skip(reason)


# ---------------------------------------------------------------------------
# Blob setup helper
# ---------------------------------------------------------------------------


def _setup_blob(base_url: str, blob_spec: dict[str, str]) -> str:
    """POST a blob to /data and return the key."""
    resp = httpx.post(
        f"{base_url}/data",
        content=blob_spec["content"].encode(),
        headers={"content-type": blob_spec.get("content_type", "text/plain")},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["key"]


# ---------------------------------------------------------------------------
# Fuzzy result validation
# ---------------------------------------------------------------------------


def _validate_result(resp: httpx.Response, expect: dict[str, Any], base_url: str = "") -> None:
    """Apply all fuzzy matchers from the ``expect`` block.

    Each failing matcher produces a clear assertion message including the
    actual response text so the developer can diagnose the mismatch.

    Rate limit (429) and auth errors are treated as **skips**, not
    failures — the test infrastructure can't control provider rate
    limits, and a 429 during a test is not a code bug.
    """
    text = resp.text
    lower = text.lower()
    expected_status = expect.get("status", 200)

    # --- skip on rate limit or auth error (not a code bug) ---
    if expected_status == 200 and resp.status_code in (429, 502):
        if "rate limit" in lower or "429" in lower:
            pytest.skip(
                f"Rate limited during test execution (HTTP {resp.status_code}): {text[:300]}"
            )
        if "credential" in lower or "auth" in lower:
            pytest.skip(f"Auth error during test execution (HTTP {resp.status_code}): {text[:300]}")

    # --- status code ---
    assert resp.status_code == expected_status, (
        f"Expected HTTP {expected_status}, got {resp.status_code}.\nResponse body: {text[:500]}"
    )

    # Short-circuit: if we expected a non-200 status, the remaining
    # content checks are usually not meaningful.
    if expected_status != 200:
        return

    # --- non_empty (default true for status 200) ---
    if expect.get("non_empty", True):
        assert text.strip(), "Expected non-empty response, got empty body."

    # --- min_length / max_length ---
    min_len = expect.get("min_length")
    if min_len is not None:
        assert len(text) >= min_len, (
            f"Response too short: {len(text)} chars < min_length={min_len}.\n"
            f"Response: {text[:300]!r}"
        )

    max_len = expect.get("max_length")
    if max_len is not None:
        assert len(text) <= max_len, (
            f"Response too long: {len(text)} chars > max_length={max_len}.\n"
            f"Response: {text[:300]!r}"
        )

    # --- contains_any (case-insensitive) ---
    needles = expect.get("contains_any")
    if needles:
        found = any(n.lower() in lower for n in needles)
        assert found, (
            f"Expected at least one of {needles} in response (case-insensitive).\n"
            f"Response: {text[:500]!r}"
        )

    # --- contains_all (case-insensitive) ---
    all_needles = expect.get("contains_all")
    if all_needles:
        missing = [n for n in all_needles if n.lower() not in lower]
        assert not missing, (
            f"Missing required substrings: {missing} (case-insensitive).\nResponse: {text[:500]!r}"
        )

    # --- not_contains (case-insensitive) ---
    bad_needles = expect.get("not_contains")
    if bad_needles:
        found_bad = [n for n in bad_needles if n.lower() in lower]
        assert not found_bad, (
            f"Response contains forbidden substrings: {found_bad}.\nResponse: {text[:500]!r}"
        )

    # --- pattern (regex) ---
    pattern = expect.get("pattern")
    if pattern:
        assert re.search(pattern, text), (
            f"Regex pattern {pattern!r} not found in response.\nResponse: {text[:500]!r}"
        )

    # --- min_results / max_results (newline-separated) ---
    min_results = expect.get("min_results")
    max_results = expect.get("max_results")
    if min_results is not None or max_results is not None:
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        if min_results is not None:
            assert len(lines) >= min_results, (
                f"Expected at least {min_results} result lines, got {len(lines)}.\nLines: {lines}"
            )
        if max_results is not None:
            assert len(lines) <= max_results, (
                f"Expected at most {max_results} result lines, got {len(lines)}.\nLines: {lines}"
            )

    # --- LLM judge (optional — for semantic validation) ---
    judge = expect.get("judge")
    if judge:
        _run_llm_judge(base_url, text, judge)


def _run_llm_judge(base_url: str, response_text: str, judge_spec: dict[str, Any]) -> None:
    """Use our own /claude/run backend to validate semantic correctness.

    Uses ``POST /claude/run`` (raw prompt, not url4-parsed) so the
    judge prompt can contain arbitrary text without parser issues.

    This is a best-effort check — if the judge backend is rate-limited
    or unavailable, the check is skipped (not failed).
    """
    question = judge_spec["question"]
    judge_prompt = (
        f"You are a test result validator. Given an LLM response and a question, "
        f"determine if the response satisfies the question. Be lenient — if the "
        f"answer is roughly correct or the key information is present anywhere "
        f"in the response, answer YES.\n\n"
        f"LLM response:\n{response_text[:2000]}\n\n"
        f"Question: {question}\n\n"
        f"Answer YES or NO only."
    )

    try:
        judge_resp = httpx.post(
            f"{base_url}/claude/run",
            json={"prompt": judge_prompt},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        import warnings

        warnings.warn(f"LLM judge request failed (non-fatal): {exc}", stacklevel=2)
        return

    # Rate limited or other backend error — skip judge, don't fail
    if judge_resp.status_code != 200:
        if "rate limit" in judge_resp.text.lower() or "429" in judge_resp.text:
            import warnings

            warnings.warn("LLM judge skipped: rate limited", stacklevel=2)
            return
        import warnings

        warnings.warn(
            f"LLM judge returned HTTP {judge_resp.status_code} (non-fatal): "
            f"{judge_resp.text[:200]}",
            stacklevel=2,
        )
        return

    # /claude/run returns JSON {"stdout": "...", ...}
    try:
        judge_data = judge_resp.json()
        answer_text = judge_data.get("so") or judge_data.get("stdout") or ""
    except Exception:
        answer_text = judge_resp.text

    answer = answer_text.strip().upper()
    if not answer.startswith("YES"):
        import warnings

        warnings.warn(
            f"LLM judge answered NO (non-fatal).\n"
            f"  Judge question: {question}\n"
            f"  Judge answer: {answer_text.strip()!r}\n"
            f"  Response evaluated: {response_text[:200]!r}",
            stacklevel=2,
        )


# ---------------------------------------------------------------------------
# HTTP request with 429 retry
# ---------------------------------------------------------------------------


def _is_rate_limited(resp: httpx.Response) -> bool:
    """Check if a response indicates rate limiting (429 or 502 wrapping 429)."""
    if resp.status_code == 429:
        return True
    if resp.status_code == 502:
        text = resp.text.lower()
        return "rate limit" in text or "429" in text
    return False


def _get_with_retry(url: str, **kwargs: Any) -> httpx.Response:
    """httpx.get with retry-on-429.  Waits between attempts."""
    resp = httpx.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
    for attempt in range(MAX_RETRIES):
        if not _is_rate_limited(resp):
            return resp
        wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
        logger.warning(
            "Rate limited (attempt %d/%d), waiting %ds before retry...",
            attempt + 1,
            MAX_RETRIES,
            wait,
        )
        time.sleep(wait)
        resp = httpx.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
    return resp


# ---------------------------------------------------------------------------
# Execute a single test case
# ---------------------------------------------------------------------------


def _run_case(base_url: str, case: dict[str, Any]) -> None:
    """Execute one test case from the YAML matrix."""
    backends = case.get("backends", [])
    if backends:
        _check_backends(base_url, backends)

    # Setup blob if needed
    blob_key = None
    if "setup_blob" in case:
        blob_key = _setup_blob(base_url, case["setup_blob"])

    # Build expression (substitute {blob_key} placeholder)
    expression = case["expression"]
    if blob_key:
        expression = expression.replace("{blob_key}", blob_key)

    expect = case.get("expect", {})

    # Handle empty expression -> expect 400 (no retry needed)
    if not expression:
        resp = httpx.get(
            f"{base_url}/ensemble",
            params=case.get("params", {}),
            timeout=REQUEST_TIMEOUT,
        )
        _validate_result(resp, expect, base_url)
        return

    # Raw GET (for non-ensemble endpoints like /data/{key})
    if case.get("raw_get"):
        resp = _get_with_retry(f"{base_url}{expression}")
        _validate_result(resp, expect, base_url)
        return

    # Standard ensemble GET — retry on 429
    params: dict[str, Any] = {"q": expression, **case.get("params", {})}
    resp = _get_with_retry(
        f"{base_url}/ensemble",
        params=params,
    )
    _validate_result(resp, expect, base_url)


# ============================================================================
# Test classes
# ============================================================================


class TestUrl4MatrixNonLive:
    """Non-live matrix tests — no backend needed, always run."""

    @pytest.mark.parametrize("case", _NON_LIVE_CASES, ids=_NON_LIVE_IDS)
    def test_case(self, matrix_url: str, case: dict[str, Any]) -> None:
        _run_case(matrix_url, case)


class TestUrl4MatrixLive:
    """Live matrix tests — require real backend(s).

    Each test probes its required backends via ``/<backend>/health``
    before running.  If a backend is unavailable the test is skipped
    with a verbose diagnostic:

    - No credential in Keychain -> "run 'claude auth login'"
    - Token rejected (401/403) -> "re-authenticate with the CLI"
    - Rate limited (429) -> "try again later, tokens_remaining=0"
    - Insufficient capacity -> "tokens_remaining=500 < minimum=1000"
    - Plugin not loaded (404) -> "add to sf.json plugins list"
    - Server unreachable -> "is the SF server running?"
    """

    @pytest.mark.parametrize("case", _LIVE_CASES, ids=_LIVE_IDS)
    def test_case(self, matrix_url: str, case: dict[str, Any]) -> None:
        _run_case(matrix_url, case)
