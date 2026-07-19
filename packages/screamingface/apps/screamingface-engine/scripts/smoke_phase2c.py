"""No-mock SDK-to-engine smoke for a running Phase 2C Docker stack."""

from __future__ import annotations

import os

import screamingface as sf


def main() -> None:
    engine_url = os.environ.get("SCREAMINGFACE_ENGINE_URL", "http://127.0.0.1:4404").rstrip("/")
    sf.config(engine=engine_url)

    benchmark = sf.Benchmark(
        "phase2c-smoke@1",
        cases=[sf.Case("arithmetic", "What is 2 + 2?", reference="4")],
        grader=sf.graders.ExactChoice(),
    )
    fusion = sf.Fusion(
        "phase2c-smoke",
        models=["codex/gpt-5.5", "gemini/2.5", "claude/sonnet-4.6"],
        prompt="Answer with only the final number.",
        reducer=sf.reducers.MajorityVote(),
    )

    run = fusion.run(benchmark)
    assert run.benchmark_id == "phase2c-smoke@1"
    assert run.case_ids == ("arithmetic",)
    assert run.fusion_url4 == fusion.url4

    if run.complete:
        result = run.results[0]
        assert result.answer is not None
        assert tuple(result.members) == ("member_1", "member_2", "member_3")
        outcome = "provider-backed Fusion result received"
    else:
        failure = run.failures[0]
        assert failure.kind == "url4", failure
        assert failure.status == 502, failure
        assert not run.results[0].members
        assert run.results[0].answer is None
        outcome = "engine surfaced the credential-free AI Gateway failure atomically"

    print("Phase 2C Docker smoke passed:")
    print("- the SDK compiled and sent one complete Fusion expression to GET /v1")
    print("- the persistent URL4 node dispatched its registered model routes")
    print(f"- {outcome}")


if __name__ == "__main__":
    main()
