from __future__ import annotations

import json

import pytest

from url4_cloud.benchmarks import BENCHMARKS, DEFAULT_BENCHMARK_ID
from url4_cloud.benchmarks.registry import benchmark


def _loaded_case() -> dict:
    rows = json.loads(BENCHMARKS["draco-lite"].execute("load", "", ""))
    assert len(rows) == 1
    return rows[0]


def test_registry_explicitly_selects_smoke_as_the_safe_default() -> None:
    assert tuple(BENCHMARKS) == ("draco-smoke", "draco-lite")
    assert DEFAULT_BENCHMARK_ID == "draco-smoke"

    benchmark = BENCHMARKS["draco-smoke"]
    assert benchmark.title == "DRACO Smoke"
    assert b"criteria_per_case: 1" in benchmark.manifest
    assert b"max_output_tokens: 512" in benchmark.manifest
    assert b"tools: []" in benchmark.manifest


def test_registry_exposes_the_real_draco_lite_descriptor() -> None:
    benchmark = BENCHMARKS["draco-lite"]

    assert benchmark.title == "DRACO Lite"
    assert b"route: /benchmark" in benchmark.manifest
    assert b"criteria_per_case: 10" in benchmark.manifest
    assert benchmark.manifest.count(b"model: anthropic/claude-haiku-4-5") == 2


def test_draco_judge_model_params_are_accepted_by_aigateway() -> None:
    manifest = BENCHMARKS["draco-lite"].manifest.decode()
    synthesis = manifest.split("synthesis:", 1)[1].split("grader:", 1)[0]
    grader = manifest.split("grader:", 1)[1].split("aggregator:", 1)[0]

    for model_call in (synthesis, grader):
        assert "reasoning: low" in model_call
        assert "temperature:" not in model_call


def test_draco_lite_prepares_one_explicit_judge_job_per_criterion() -> None:
    jobs = json.loads(
        BENCHMARKS["draco-lite"].execute(
            "grading_inputs",
            json.dumps({"case": _loaded_case(), "answer": "Candidate answer"}),
            "",
        )
    )

    assert len(jobs) == 10
    assert len({job["criterion_id"] for job in jobs}) == 10
    assert all(job["run"] == 0 for job in jobs)
    assert all("<response>\nCandidate answer\n</response>" in job["context"] for job in jobs)


def test_draco_smoke_runs_one_real_rubric_judge_job() -> None:
    benchmark = BENCHMARKS["draco-smoke"]
    cases = json.loads(benchmark.execute("load", "", ""))
    jobs = json.loads(
        benchmark.execute(
            "grading_inputs",
            json.dumps({"case": cases[0], "answer": "Candidate answer"}),
            "",
        )
    )

    assert len(cases) == 1
    assert len(jobs) == 1
    assert jobs[0]["criterion_id"] == "twfe-variance-weighted-decomposition"
    assert jobs[0]["run"] == 0
    assert "<response>\nCandidate answer\n</response>" in jobs[0]["context"]

    grade = json.loads(
        benchmark.execute(
            "grade",
            json.dumps(
                {
                    "case": cases[0],
                    "judgments": [
                        {
                            "criterion_id": jobs[0]["criterion_id"],
                            "run": 0,
                            "response": json.dumps(
                                {
                                    "explanation": "deterministic fixture",
                                    "criterion_status": "MET",
                                }
                            ),
                        }
                    ],
                }
            ),
            "",
        )
    )
    report = json.loads(benchmark.execute("aggregate", "", json.dumps([grade])))

    assert grade["score"] == 1.0
    assert len(grade["criteria"]) == 1
    # INVARIANT: the result names the exact EXAM SAT (versioned id) — this is the
    # leaderboard column key, not the addressable name.
    assert report["benchmark_id"] == "draco-smoke-v1"
    assert report["score"] == 1.0


def test_manifest_declares_schema_and_versioned_exam_identity() -> None:
    # INVARIANT: manifest `id` = `<name>@<version>` — same id string ⇒ same exam; `name`
    # stays the unversioned address used by the registry, REST routes, and the SDK.
    for address, entry in BENCHMARKS.items():
        manifest = entry.manifest.decode()
        assert manifest.startswith("schema: screamingface.benchmark-manifest.v1\n")
        assert f"\nname: {address}\n" in f"\n{manifest}"
        assert f"\nid: {address}-v1\n" in manifest
        assert entry.id == address


def test_manifest_pins_case_provenance_revision() -> None:
    # INVARIANT: the pinned cases carry a content revision, so the exam cannot change
    # under a frozen id — different case sets MUST yield different revisions.
    revisions: dict[str, str] = {}
    for address, entry in BENCHMARKS.items():
        manifest = entry.manifest.decode()
        provenance = manifest.split("provenance:", 1)[1].split("answer:", 1)[0]
        assert "dataset: vendored:url4_cloud.benchmarks.draco.cases" in provenance
        marker = "revision: sha256:"
        revision = provenance.split(marker, 1)[1].split()[0]
        assert len(revision) == 64
        assert set(revision) <= set("0123456789abcdef")
        revisions[address] = revision
    assert revisions["draco-smoke"] != revisions["draco-lite"]


def test_case_revision_is_deterministic_across_builds() -> None:
    # WHY: the revision feeds the future leaderboard hash gate — a rebuild of the same
    # pinned cases must reproduce byte-identical manifests.
    from url4_cloud.benchmarks.draco.cases import CASES
    from url4_cloud.benchmarks.draco.family import build_draco_benchmark

    def build() -> bytes:
        return build_draco_benchmark(
            benchmark_id="draco-lite",
            version=1,
            title="DRACO Lite",
            cases=CASES,
            criteria_per_case=10,
            judge_passes=1,
            answer_output_tokens=4096,
            synthesis_output_tokens=4096,
            judge_output_tokens=4096,
            tools=("web_search", "web_fetch"),
        ).manifest

    assert build() == build() == BENCHMARKS["draco-lite"].manifest


def test_registry_resolves_the_versioned_exam_identity() -> None:
    # INVARIANT: the SDK compiles the manifest `id` (`<name>-v<version>`) into the
    # executed plan — the registry resolves it only when the installed version matches,
    # so a stale client can never silently sit a different exam under a frozen id.
    # WHY `-v` and not `@`: `@` is url4's reserved holdings-reference token; an id
    # containing it drops the /benchmark context out of structured ctx-slot lowering.
    assert benchmark("draco-lite") is BENCHMARKS["draco-lite"]
    assert benchmark("draco-lite-v1") is BENCHMARKS["draco-lite"]
    assert benchmark("draco-smoke-v1") is BENCHMARKS["draco-smoke"]
    with pytest.raises(ValueError, match="unknown benchmark 'draco-lite-v2'"):
        benchmark("draco-lite-v2")
    with pytest.raises(ValueError, match="unknown benchmark"):
        benchmark("missing-v1")


def test_draco_lite_grades_and_aggregates_deterministically() -> None:
    benchmark = BENCHMARKS["draco-lite"]
    case = _loaded_case()
    jobs = json.loads(
        benchmark.execute(
            "grading_inputs",
            json.dumps({"case": case, "answer": "Candidate answer"}),
            "",
        )
    )
    judgments = [
        {
            "criterion_id": job["criterion_id"],
            "run": job["run"],
            "response": json.dumps(
                {
                    "explanation": "deterministic fixture",
                    "criterion_status": (
                        "UNMET" if job["criterion_id"] == "pretest-gating" else "MET"
                    ),
                }
            ),
        }
        for job in jobs
    ]

    grade = json.loads(
        benchmark.execute(
            "grade",
            json.dumps({"case": case, "judgments": judgments}),
            "",
        )
    )
    report = json.loads(benchmark.execute("aggregate", "", json.dumps([grade])))

    assert grade["score"] == 1.0
    assert grade["metrics"]["coverage"] == 1.0
    assert len(grade["criteria"]) == 10
    assert report["schema"] == "screamingface.candidate-result.v1"
    assert report["benchmark_id"] == "draco-lite-v1"
    assert report["case_count"] == 1
    assert report["score"] == 1.0
