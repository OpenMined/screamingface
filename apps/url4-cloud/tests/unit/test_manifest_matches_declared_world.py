"""A manifest's claims must match the world the image actually declares.

FEATURE: `GET /v1/benchmarks/{id}` tells a client how to run a benchmark.
STORY: as a client author, the routes and judge a manifest names must be the ones the Runner
serves — or the expression I build from it fails at resolution, or worse, silently runs something
else.

WHY this module exists: `manifests.py` carried an AIDEV-NOTE saying two things were unenforced
and "will drift" — the `routes` block against `prepare.render_data_table`, and the judge against
`url4.toml`. An unenforced claim in a published catalog is the same shape as every other defect
this branch has found: it reads as a guarantee and is not one.

INVARIANT: these assert the manifest against the GENERATOR and the CONFIG, never against a second
copy of the same literal — a test that restates the manifest proves only that the manifest equals
itself.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from url4_cloud import manifests
from url4_cloud.benchmarks.draco import prepare

_RUNNER_CONFIG = Path(__file__).resolve().parents[2] / "url4.toml"


def _declared_data_routes(case_ids: list[int]) -> set[str]:
    """The `[data]` paths `prepare` would actually emit for these cases."""
    cases = [{"id": case_id} for case_id in case_ids]
    table = tomllib.loads(prepare.render_data_table(cases, Path("/opt/benchmarks/draco"), "/draco"))
    return set(table["data"])


def test_the_manifest_cases_route_is_one_prepare_declares() -> None:
    route = manifests.field(manifests.DRACO_LITE, "routes")
    # `routes:` is a nested block, so `field` returns None for it — read the leaf directly.
    assert route is None
    assert "cases: /draco/cases" in manifests.DRACO_LITE
    assert "/draco/cases" in _declared_data_routes([1, 2])


def test_the_manifest_criteria_template_matches_a_declared_route() -> None:
    """The manifest advertises `/draco/criteria/{case_id}`; the generator emits one exact path per
    case, because routing has no wildcard form. The TEMPLATE is only honest if substituting a real
    id yields a route that exists."""
    assert "criteria: /draco/criteria/{case_id}" in manifests.DRACO_LITE

    declared = _declared_data_routes([1, 7])

    assert {"/draco/criteria/1", "/draco/criteria/7"} <= declared


def test_the_manifest_never_advertises_a_rubric_route() -> None:
    """INVARIANT: the weighted rubrics are the answer key. They are deliberately NOT declared as
    routes, so a manifest naming one would advertise a path that both leaks and does not exist."""
    assert "rubric" not in manifests.DRACO_LITE.split("routes:")[1]
    assert not any("/rubrics/" in route for route in _declared_data_routes([1, 2]))


def test_the_manifest_judge_is_a_route_the_runner_declares() -> None:
    """A judge the image cannot address is a `ResolutionError` at run time, and the paper PINS
    this model — so a drift here silently changes what the score means."""
    judge = manifests.field(manifests.DRACO_LITE, "judge")
    assert judge is not None

    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]
    declared = {entry["id"] if isinstance(entry, dict) else entry for entry in entries}

    assert judge in declared


def test_the_judge_declares_no_retrieval() -> None:
    """arXiv:2602.11685 §4.2 — the judge sees one answer and one criterion. Giving it web access
    would let it check claims against the live web, which is a DIFFERENT benchmark."""
    judge = manifests.field(manifests.DRACO_LITE, "judge")

    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]
    entry = next(e for e in entries if isinstance(e, dict) and e.get("id") == judge)

    assert not entry.get("web_tools")
    assert not entry.get("native_web_search")


def test_every_answering_route_in_the_lineup_retrieves_somehow() -> None:
    """The owner's 2026-08-02 decision: native where OpenRouter provides it, Tavily otherwise, so
    that no DRACO candidate answers from weights alone on a DEEP-RESEARCH benchmark.

    INVARIANT: this is what makes the manifest's `tools:` block honest. A route added to the
    lineup without a retrieval mechanism would silently score below the reference chart for
    reasons that have nothing to do with the candidate.
    """
    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]
    judge = manifests.field(manifests.DRACO_LITE, "judge")

    openrouter = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and str(entry.get("id", "")).startswith("openrouter/")
        and entry.get("id") != judge
    ]
    assert openrouter, "no OpenRouter answering routes are declared"

    silent = [
        entry["id"]
        for entry in openrouter
        if not entry.get("web_tools") and not entry.get("native_web_search")
    ]
    assert silent == [], f"these DRACO routes would answer from weights alone: {silent}"


def test_no_google_route_declares_native_web_search() -> None:
    """MEASURED 2026-08-02: a Google native-search call carrying `exclude_domains` is a hard 400 —

        "Domain filters (include_domains/exclude_domains) are not supported with native search on
         Google. Use engine: 'exa' or remove domain filters"

    INVARIANT: on a Google route it is retrieval OR the blocklist, never both. For a benchmark
    whose candidates must not reach the answer key the guard is not optional, so these routes take
    the Tavily loop instead. The trap is that the flag looks correct — the model DOES support
    native search — and the failure only appears once a policy is attached, i.e. on the real
    benchmark expression and not on a smoke test.

    This applies to the DEPLOYMENT's blocklist too, not only an expression policy.
    """
    with _RUNNER_CONFIG.open("rb") as handle:
        entries = tomllib.load(handle)["aigateway"]["models"]

    offenders = [
        entry["id"]
        for entry in entries
        if isinstance(entry, dict)
        and "/google/" in str(entry.get("id", ""))
        and entry.get("native_web_search")
    ]

    assert offenders == [], f"Google native search cannot carry a blocklist: {offenders}"


def test_the_declared_call_timeout_fits_a_retrieving_answer() -> None:
    """MEASURED 2026-08-02 on a real Kubernetes Job: at the 60s default the answering call raised
    `ReadTimeout`, and because `iteration.on_error=collect` substitutes an error object in place,
    the run reported `terminated: succeeded` with `case_count: 0`.

    INVARIANT: a DRACO answer is a deep-research call WITH provider-side retrieval and does not
    fit in the default. This pins the declaration, because the failure it prevents is silent —
    a benchmark emptied by a network setting is indistinguishable in the result from a candidate
    that answered badly.
    """
    with _RUNNER_CONFIG.open("rb") as handle:
        section = tomllib.load(handle)["aigateway"]

    assert section.get("timeout_s", 60.0) >= 180.0, (
        "the declared aigateway timeout is at or near the 60s default — a retrieving answer "
        "times out and the run silently scores nothing"
    )


_CHART_VALUES = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "values.yaml"


def _values() -> dict:
    """Parse the chart's values without Helm — the invariants below are about DECLARED defaults,
    and a test that needed a Helm binary would simply not run in this stack's gate."""
    import yaml

    with _CHART_VALUES.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_runner_jobs_default_to_the_benchmark_image() -> None:
    """A Runner exists to execute a benchmark, and the plain engine image declares no `[data]`
    routes — MEASURED on a real Job, the first expression fails `endpoint_not_found ... at
    '/draco/cases'`. Defaulting to the App image makes a whole deployment unable to run a single
    case until someone remembers an override.

    The default is DERIVED (`<image.repository>-benchmark`) rather than written out, so this
    asserts on the helper that derives it. A literal path here made the override always set,
    which left the derivation unreachable and pinned Runner Jobs to ghcr.io even when the App
    was mirrored to a private registry — see `test_runner_image_tracks_the_app_registry.py`,
    which pins the same invariant against a REAL `helm template` render.
    """
    helpers = (_CHART_VALUES.parent / "templates" / "_helpers.tpl").read_text(encoding="utf-8")

    assert _values()["runner"]["image"]["repository"] == ""
    assert '"%s-benchmark"' in helpers


def test_the_control_plane_never_runs_the_benchmark_image() -> None:
    """INVARIANT: the benchmark image carries the private weighted rubrics — the answer key. The
    control plane is the process that terminates CLIENT connections, so a rubric on that pod is
    one bug away from reaching the client it is being kept from. Two images exist for exactly this
    asymmetry; collapsing them back to one would silently undo it."""
    values = _values()

    assert values["image"]["repository"] != values["runner"]["image"]["repository"]
    assert not values["image"]["repository"].endswith("-benchmark")


def test_the_runner_tag_tracks_the_app_tag() -> None:
    """Empty => the App image's resolved tag. That is what keeps engine and dataset on ONE version,
    so a published score can name the engine that produced it. A pinned tag here is a staged
    rollout, not a default."""
    assert _values()["runner"]["image"]["tag"] == ""
