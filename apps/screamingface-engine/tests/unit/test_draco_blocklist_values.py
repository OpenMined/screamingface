"""The blocklist VALUES — bare hosts only, because that is all a provider accepts.

FEATURE: the DRACO retrieval policy keeps a candidate from reading the answer key.
STORY: as a benchmark author, "the paper is blocked" must also mean the run still WORKS — a
blocklist the provider rejects protects nothing, it just stops the benchmark.

MEASURED 2026-08-02, straight to OpenRouter AND through the deployed gateway on a kind cluster:

    exclude_domains: ["arxiv.org"]                 -> 200
    exclude_domains: ["arxiv.org/abs/2602.11685"]  -> 400  "Invalid domain 'arxiv.org/abs/...'"
    exclude_domains: ["*.substack.com"]            -> 400
    exclude_domains: <the whole shipped list>      -> 400

The path-shaped list this benchmark shipped therefore made EVERY native answering call a hard
400: a run that finished in five seconds, reported `terminated: succeeded`, and scored nothing.
It was invisible to every earlier test because those used a bare host in a PROBE policy — only
the real expression carries the real list, and only a real Job run puts the two together.

# AIDEV-NOTE: an earlier revision of this module asserted the OPPOSITE — one entry per URL form
# (`/abs/`, `/pdf/`, `/html/`) and "never block a bare research host". That came from Tavily,
# which does accept paths and match them partially. The provider side does not, and it is the
# binding constraint. Both assertions were replaced the same day they were written.

DECISION (owner, 2026-08-02): block whole SITES. The cost is real and belongs beside any published
score — `arxiv.org` and `huggingface.co` are legitimate research sources, and removing them makes
a candidate look worse at deep research than it is. The alternative under-blocks, which INFLATES
scores, and an inflated score is the one nobody audits.
"""

from __future__ import annotations

import json

from screamingface_engine.benchmarks.draco import prepare


def test_every_entry_is_a_bare_host() -> None:
    """INVARIANT: no path, no wildcard, no scheme. THE regression guard — one path-shaped entry
    takes the whole benchmark down with a 400, and the failure presents as a successful run that
    scored zero."""
    for entry in prepare.EXCLUDED_DOMAINS:
        assert "/" not in entry, f"{entry!r} has a path — the provider rejects the whole request"
        assert "*" not in entry, f"{entry!r} is a wildcard — measured as a 400"
        assert ":" not in entry, f"{entry!r} carries a scheme or port"
        assert entry == entry.strip().lower(), f"{entry!r} is not normalised"


def test_the_leak_sources_are_covered_at_host_level() -> None:
    """Every host that actually served DRACO material in a live search."""
    for host in ("arxiv.org", "huggingface.co", "openrouter.ai", "paperswithcode.com"):
        assert host in prepare.EXCLUDED_DOMAINS


def test_the_list_has_no_duplicates() -> None:
    """Collapsing pages to hosts turns several old entries into the same host; a duplicate would
    be sent to the provider twice and reads as sloppiness in a published artifact."""
    entries = list(prepare.EXCLUDED_DOMAINS)

    assert len(entries) == len(set(entries))


def test_the_policy_artifact_carries_the_same_bare_hosts(tmp_path) -> None:
    """What `prepare` WRITES is what a run sends. Asserting the constant alone would miss a
    transform introduced between the constant and the file."""
    prepare.write_policy(tmp_path)
    policy = json.loads((tmp_path / "policy" / "retrieval.json").read_text(encoding="utf-8"))

    assert policy["excluded_domains"]
    for entry in policy["excluded_domains"]:
        assert "/" not in entry and "*" not in entry
