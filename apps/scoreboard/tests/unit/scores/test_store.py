from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from tortoise import Tortoise

from scoreboard.scores.models import Benchmark, IdempotencyKey, Score
from scoreboard.scores.schemas import ClientInfo, ScoreSubmission
from scoreboard.scores.store import ScoreStore

pytestmark = pytest.mark.asyncio


def _submission(
    *,
    spec_id: str = "spec-1",
    accuracy: float = 0.75,
    providers: list[str] | None = None,
) -> ScoreSubmission:
    correct_questions = int(accuracy * 100)
    return ScoreSubmission(
        benchmark_id="hle",
        spec_id=spec_id,
        url4_expression=f"url4://benchmark/{spec_id}/{accuracy}",
        submitted_by="tester",
        accuracy=accuracy,
        total_questions=100,
        correct_questions=correct_questions,
        ran_with_providers=providers or ["openai"],
        ran_at_local=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
        client=ClientInfo(name="scoreboard-test", version="0.1.0", platform="test"),
        metadata={"source": "unit"},
    )


async def _store_with_benchmark() -> ScoreStore:
    store = ScoreStore()
    await store.register_benchmark(
        benchmark_id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    return store


async def test_register_benchmark_and_list_benchmarks(tortoise_db: None) -> None:
    store = ScoreStore()

    registered = await store.register_benchmark(
        benchmark_id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    benchmarks = await store.list_benchmarks()

    assert registered.id == "hle"
    assert benchmarks == [registered]


async def test_register_benchmark_updates_existing_row(tortoise_db: None) -> None:
    store = ScoreStore()

    await store.register_benchmark(
        benchmark_id="hle",
        display_name="Humanity's Last Exam",
        description="Fixture benchmark",
        dataset_url="https://example.test/hle.jsonl",
    )
    updated = await store.register_benchmark(
        benchmark_id="hle",
        display_name="News Hallucinations",
        description="OpenMined HLE benchmark",
        dataset_url="https://github.com/openmined/HLE.jsonl",
    )
    benchmarks = await store.list_benchmarks()

    assert await Benchmark.all().count() == 1
    assert updated.id == "hle"
    assert updated.display_name == "News Hallucinations"
    assert updated.description == "OpenMined HLE benchmark"
    assert updated.dataset_url == "https://github.com/openmined/HLE.jsonl"
    assert benchmarks == [updated]


async def test_submit_inserts_and_returns_score(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    score, created = await store.submit(_submission())

    assert created is True
    assert score.benchmark_id == "hle"
    assert score.spec_id == "spec-1"
    assert score.accuracy == 0.75
    assert score.total_questions == 100
    assert score.correct_questions == 75
    assert score.ran_with_providers == ["openai"]
    assert score.client_name == "scoreboard-test"
    assert score.verified_by_openmined is False
    assert await Score.all().count() == 1


async def test_submit_with_live_idempotency_key_returns_existing_score(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()

    first, first_created = await store.submit(
        _submission(accuracy=0.5), idempotency_key="repeat-key"
    )
    second, second_created = await store.submit(
        _submission(accuracy=0.9), idempotency_key="repeat-key"
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.submitted_at == first.submitted_at
    assert second.accuracy == 0.5
    assert await Score.all().count() == 1


async def test_submit_with_expired_idempotency_key_creates_new_score(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    first, _ = await store.submit(_submission(accuracy=0.5), idempotency_key="expired-key")
    await IdempotencyKey.filter(key="expired-key").update(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    second, second_created = await store.submit(
        _submission(accuracy=0.9), idempotency_key="expired-key"
    )

    assert second_created is True
    assert second.id != first.id
    assert second.accuracy == 0.9
    assert await Score.all().count() == 2


async def test_get_by_idempotency_key_respects_expiry_and_cleanup(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    score, _ = await store.submit(_submission(), idempotency_key="lookup-key")

    assert await store.get_by_idempotency_key("lookup-key") == score

    past = datetime.now(UTC) - timedelta(seconds=1)
    await IdempotencyKey.filter(key="lookup-key").update(expires_at=past)

    assert await store.get_by_idempotency_key("lookup-key") is None
    assert await store.cleanup_expired_idempotency_keys(datetime.now(UTC)) == 1
    assert await IdempotencyKey.all().count() == 0


async def test_leaderboard_returns_best_score_per_spec_in_rank_order(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    await store.submit(_submission(spec_id="spec-a", accuracy=0.6, providers=["openai"]))
    await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["anthropic"]))
    await store.submit(_submission(spec_id="spec-b", accuracy=0.95, providers=["openai", "gemini"]))
    await store.submit(_submission(spec_id="spec-c", accuracy=0.7, providers=["gemini"]))

    rows = await store.leaderboard("hle", top_n=2)

    assert [row.spec_id for row in rows] == ["spec-b", "spec-a"]
    assert [row.accuracy for row in rows] == [0.95, 0.9]
    assert rows[0].ran_with_providers == ["openai", "gemini"]
    assert isinstance(rows[0].ran_with_providers, list)


async def test_leaderboard_uses_newer_submission_as_accuracy_tie_breaker(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    older, _ = await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["older"]))
    newer, _ = await store.submit(_submission(spec_id="spec-a", accuracy=0.9, providers=["newer"]))
    await Score.filter(id=older.id).update(
        submitted_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
    )
    await Score.filter(id=newer.id).update(
        submitted_at=datetime(2026, 5, 21, 13, 0, tzinfo=UTC),
    )

    rows = await store.leaderboard("hle")

    assert len(rows) == 1
    assert rows[0].ran_with_providers == ["newer"]


async def test_list_for_spec_returns_history_newest_first(tortoise_db: None) -> None:
    store = await _store_with_benchmark()
    older, _ = await store.submit(_submission(spec_id="spec-history", accuracy=0.5))
    newer, _ = await store.submit(_submission(spec_id="spec-history", accuracy=0.8))
    await Score.filter(id=older.id).update(
        submitted_at=datetime(2026, 5, 21, 12, 0, tzinfo=UTC),
    )
    await Score.filter(id=newer.id).update(
        submitted_at=datetime(2026, 5, 21, 13, 0, tzinfo=UTC),
    )

    rows = await store.list_for_spec("hle", "spec-history")

    assert [row.id for row in rows] == [newer.id, older.id]


async def test_mark_verified_flips_score_flag(tortoise_db: None) -> None:
    store = await _store_with_benchmark()
    score, _ = await store.submit(_submission())

    await store.mark_verified(score.id)

    verified = await Score.get(id=score.id)
    assert verified.verified_by_openmined is True


async def test_submit_identical_recipe_without_header_returns_existing_score(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()

    first, first_created = await store.submit(_submission(spec_id="spec-dup", accuracy=0.42))
    second, second_created = await store.submit(_submission(spec_id="spec-dup", accuracy=0.42))

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.submitted_at == first.submitted_at
    assert await Score.all().count() == 1


async def test_submit_identical_recipe_ignores_submitted_by_and_client_metadata(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()
    first_submission = _submission(spec_id="spec-attrib", accuracy=0.6)
    second_submission = first_submission.model_copy(
        update={
            "submitted_by": "someone-else",
            "client": ClientInfo(name="other-client", version="9.9.9", platform="other"),
            "ran_at_local": datetime(2026, 6, 1, tzinfo=UTC),
        }
    )

    first, _ = await store.submit(first_submission)
    second, second_created = await store.submit(second_submission)

    assert second_created is False
    assert second.id == first.id
    assert second.submitted_by == first.submitted_by
    assert await Score.all().count() == 1


async def test_submit_identical_recipe_ignores_version(tortoise_db: None) -> None:
    # `version` is deliberately excluded from the content hash (see the WHY comment
    # on _content_hash) — model_copy bypasses the Literal[1] validator so this proves
    # the exclusion even though the public schema can't yet submit version=2 for real
    # (OME-391 / C28).
    store = await _store_with_benchmark()
    first_submission = _submission(spec_id="spec-version", accuracy=0.65)
    second_submission = first_submission.model_copy(update={"version": 2})

    first, _ = await store.submit(first_submission)
    second, second_created = await store.submit(second_submission)

    assert second_created is False
    assert second.id == first.id
    assert await Score.all().count() == 1


async def test_submit_identical_counts_dedupe_despite_different_accuracy_precision(
    tortoise_db: None,
) -> None:
    # The route accepts any reported accuracy within 0.01 of correct/total, so the
    # same result (2 of 3 correct) can arrive as 0.6666666667 or 0.67 — both must
    # still dedupe, since the hash is derived from the counts, not the raw float
    # (found in PR review, OME-391 / C28).
    store = await _store_with_benchmark()
    first_submission = _submission(spec_id="spec-precision", accuracy=0.75).model_copy(
        update={"total_questions": 3, "correct_questions": 2, "accuracy": 0.6666666667}
    )
    second_submission = first_submission.model_copy(update={"accuracy": 0.67})

    first, first_created = await store.submit(first_submission)
    second, second_created = await store.submit(second_submission)

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert await Score.all().count() == 1


async def test_submit_identical_recipe_dedupes_across_different_idempotency_keys(
    tortoise_db: None,
) -> None:
    # The core C28 scenario: two clients each send their own Idempotency-Key for the
    # same underlying recipe — the header alone would never catch this, only the
    # content-hash backstop does (OME-391 / C28).
    store = await _store_with_benchmark()

    first, first_created = await store.submit(
        _submission(spec_id="spec-multi-key", accuracy=0.55),
        idempotency_key="client-a-key",
    )
    second, second_created = await store.submit(
        _submission(spec_id="spec-multi-key", accuracy=0.55),
        idempotency_key="client-b-key",
    )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.submitted_at == first.submitted_at
    assert await Score.all().count() == 1


async def test_submit_reused_key_after_content_hash_hit_stays_bound_to_original_score(
    tortoise_db: None,
) -> None:
    # Regression for the bug found in PR review: a content-hash hit with an
    # idempotency_key attached must bind that key permanently. Before the fix,
    # "client-b-key" stayed unbound after hitting recipe A via content_hash, so a
    # later, unrelated recipe B reusing "client-b-key" would silently create a new
    # row AND rebind the key to it — meaning a third replay of the *original*
    # client-b-key request would then wrongly return recipe B instead of recipe A
    # (OME-391 / C28).
    store = await _store_with_benchmark()
    recipe_a = _submission(spec_id="spec-bind-a", accuracy=0.55)
    recipe_b = _submission(spec_id="spec-bind-b", accuracy=0.9)

    first, _ = await store.submit(recipe_a, idempotency_key="client-a-key")
    second, second_created = await store.submit(recipe_a, idempotency_key="client-b-key")
    assert second_created is False
    assert second.id == first.id

    third, third_created = await store.submit(recipe_b, idempotency_key="client-b-key")

    assert third_created is False
    assert third.id == first.id
    assert await Score.all().count() == 1


async def test_submit_same_recipe_different_provider_order_is_not_deduped(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()

    first, _ = await store.submit(
        _submission(spec_id="spec-order", accuracy=0.77, providers=["openai", "gemini"])
    )
    second, second_created = await store.submit(
        _submission(spec_id="spec-order", accuracy=0.77, providers=["gemini", "openai"])
    )

    assert second_created is True
    assert second.id != first.id
    assert await Score.all().count() == 2


async def test_submit_different_accuracy_is_not_deduped(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    first, _ = await store.submit(_submission(spec_id="spec-diff", accuracy=0.3))
    second, second_created = await store.submit(_submission(spec_id="spec-diff", accuracy=0.31))

    assert second_created is True
    assert second.id != first.id
    assert await Score.all().count() == 2


async def test_postgres_concurrent_idempotency_submissions_share_winner(
    tortoise_db: None,
) -> None:
    # AIDEV-NOTE: this test currently only ever skips — see OME-430 for why
    # (postgres_schema_database_url calls asyncio.run() inside an already-running
    # event loop, and CI never sets SCOREBOARD_TEST_DATABASE_URL). Fix there, not here.
    if Tortoise.get_connection("default").capabilities.dialect != "postgres":
        pytest.skip("requires Postgres")

    store = await _store_with_benchmark()
    results = await asyncio.gather(
        *(
            store.submit(
                _submission(accuracy=0.5 + (index / 100)),
                idempotency_key="race-key",
            )
            for index in range(10)
        ),
    )

    assert len({outcome.score.id for outcome in results}) == 1
    assert await Score.all().count() == 1


async def test_postgres_concurrent_identical_recipe_submissions_share_winner(
    tortoise_db: None,
) -> None:
    # AIDEV-NOTE: see OME-430 — same dead-fixture issue as the test above.
    if Tortoise.get_connection("default").capabilities.dialect != "postgres":
        pytest.skip("requires Postgres")

    store = await _store_with_benchmark()
    results = await asyncio.gather(
        *(store.submit(_submission(spec_id="spec-race", accuracy=0.66)) for _ in range(10)),
    )

    assert len({outcome.score.id for outcome in results}) == 1
    assert await Score.all().count() == 1


# --- OME-775: benchmark revision resolution ------------------------------------------------
# INVARIANT: the resolved revision is the same value whether the Client sent it as a typed
# top-level field or nested in the free-form metadata dict. Wire position must not change
# identity — the store has one resolution rule and everything downstream reads its output.


def _revision_submission(
    *,
    spec_id: str = "spec-rev",
    benchmark_revision: str | None = None,
    metadata: dict[str, object] | None = None,
) -> ScoreSubmission:
    return ScoreSubmission(
        benchmark_id="hle",
        spec_id=spec_id,
        url4_expression=f"url4://benchmark/{spec_id}",
        submitted_by="tester",
        accuracy=0.75,
        total_questions=100,
        correct_questions=75,
        ran_with_providers=["openai"],
        benchmark_revision=benchmark_revision,
        metadata=metadata,
    )


async def _stored_revision(score_id: object) -> str | None:
    # WHY assert on the persisted row rather than the returned schema: this step's contract is
    # resolution + storage. Exposure on the read schemas is a separate contract with its own
    # tests, so the two can fail independently.
    row = await Score.get(id=score_id)
    return row.benchmark_revision


async def test_submit_stores_a_typed_top_level_benchmark_revision(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    score, _ = await store.submit(_revision_submission(benchmark_revision="rev-typed"))

    assert await _stored_revision(score.id) == "rev-typed"


async def test_submit_promotes_the_revision_from_metadata(tortoise_db: None) -> None:
    # WHY: this is the shape every deployed Client sends today
    # (packages/screamingface/.../leaderboards.py) — it must keep working.
    store = await _store_with_benchmark()

    score, _ = await store.submit(
        _revision_submission(metadata={"benchmark_revision": "rev-meta", "run_id": "r1"})
    )

    assert await _stored_revision(score.id) == "rev-meta"


async def test_submit_prefers_the_typed_revision_over_the_metadata_copy(
    tortoise_db: None,
) -> None:
    store = await _store_with_benchmark()

    score, _ = await store.submit(
        _revision_submission(
            benchmark_revision="rev-typed",
            metadata={"benchmark_revision": "rev-meta"},
        )
    )

    assert await _stored_revision(score.id) == "rev-typed"


async def test_submit_leaves_the_metadata_copy_intact(tortoise_db: None) -> None:
    # INVARIANT: promotion reads metadata, it never mutates or strips it. The client's
    # payload is stored as sent.
    store = await _store_with_benchmark()

    score, _ = await store.submit(
        _revision_submission(metadata={"benchmark_revision": "rev-meta", "run_id": "r1"})
    )

    assert score.metadata == {"benchmark_revision": "rev-meta", "run_id": "r1"}


async def test_submit_accepts_a_submission_with_no_revision_anywhere(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    score, created = await store.submit(_revision_submission(metadata={"source": "unit"}))

    assert created is True
    assert await _stored_revision(score.id) is None


@pytest.mark.parametrize(
    "metadata",
    [
        {"benchmark_revision": ""},
        {"benchmark_revision": 42},
        {"benchmark_revision": None},
        {"benchmark_revision": ["rev"]},
    ],
)
async def test_submit_treats_an_unusable_metadata_revision_as_absent(
    tortoise_db: None, metadata: dict[str, object]
) -> None:
    # WHY: metadata is free-form and client-supplied, so a non-string or empty value is
    # untrustworthy input, not a crash — it resolves to None rather than raising.
    store = await _store_with_benchmark()

    score, created = await store.submit(_revision_submission(metadata=metadata))

    assert created is True
    assert await _stored_revision(score.id) is None


# --- OME-775: revision participates in dedup identity (D3) ----------------------------------


async def test_same_recipe_at_two_revisions_does_not_dedup(tortoise_db: None) -> None:
    # INVARIANT: a different benchmark revision is a different thing measured, so it is part
    # of the recipe's identity. Before OME-775 these two collided and the second was silently
    # discarded — which would have made the ranking partition unreachable, since the second
    # revision's row never existed.
    store = await _store_with_benchmark()

    first, first_created = await store.submit(_revision_submission(benchmark_revision="rev-a"))
    second, second_created = await store.submit(_revision_submission(benchmark_revision="rev-b"))

    assert first_created is True
    assert second_created is True
    assert first.id != second.id
    assert await Score.all().count() == 2


async def test_identical_submissions_still_dedup_with_a_revision(tortoise_db: None) -> None:
    # The OME-391 guarantee must survive the identity change.
    store = await _store_with_benchmark()

    first, first_created = await store.submit(_revision_submission(benchmark_revision="rev-a"))
    second, second_created = await store.submit(_revision_submission(benchmark_revision="rev-a"))

    assert first_created is True
    assert second_created is False
    assert first.id == second.id
    assert await Score.all().count() == 1


async def test_identity_follows_the_resolved_revision_not_its_wire_position(
    tortoise_db: None,
) -> None:
    # INVARIANT: a revision sent typed and the same revision sent in metadata are the same
    # submission. If identity read the wire shape instead of the resolved value, a client
    # upgrading from the metadata form to the typed form would duplicate its whole history.
    store = await _store_with_benchmark()

    first, first_created = await store.submit(
        _revision_submission(metadata={"benchmark_revision": "rev-a"})
    )
    second, second_created = await store.submit(_revision_submission(benchmark_revision="rev-a"))

    assert first_created is True
    assert second_created is False
    assert first.id == second.id


# --- OME-775: ranking partitions on (spec_id, benchmark_revision) ---------------------------


async def test_leaderboard_ranks_each_revision_of_a_spec_separately(tortoise_db: None) -> None:
    # INVARIANT: results measured against different benchmark revisions are not comparable, so
    # the board must not let one beat the other. Before OME-775 this returned a single row —
    # the higher accuracy winning across an incomparable boundary.
    store = await _store_with_benchmark()
    await store.submit(
        _revision_submission(spec_id="spec-x", benchmark_revision="rev-old"),
    )
    await store.submit(
        _revision_submission(spec_id="spec-x", benchmark_revision="rev-new"),
    )

    rows = await store.leaderboard("hle")

    assert len(rows) == 2
    assert {row.benchmark_revision for row in rows} == {"rev-old", "rev-new"}
    assert {row.spec_id for row in rows} == {"spec-x"}


async def test_leaderboard_still_collapses_within_one_revision(tortoise_db: None) -> None:
    # Best-per-spec is preserved inside a revision — the partition adds a dimension, it does
    # not stop collapsing.
    store = await _store_with_benchmark()
    await store.submit(
        ScoreSubmission(
            benchmark_id="hle",
            spec_id="spec-y",
            url4_expression="url4://benchmark/spec-y/low",
            accuracy=0.60,
            total_questions=100,
            correct_questions=60,
            ran_with_providers=["openai"],
            benchmark_revision="rev-same",
        )
    )
    await store.submit(
        ScoreSubmission(
            benchmark_id="hle",
            spec_id="spec-y",
            url4_expression="url4://benchmark/spec-y/high",
            accuracy=0.90,
            total_questions=100,
            correct_questions=90,
            ran_with_providers=["openai"],
            benchmark_revision="rev-same",
        )
    )

    rows = await store.leaderboard("hle")

    assert len(rows) == 1
    assert rows[0].accuracy == 0.90


async def test_leaderboard_groups_null_revision_rows_exactly_as_before(
    tortoise_db: None,
) -> None:
    # INVARIANT: backward compatibility. Every row predating OME-775 has a NULL revision, so
    # they must keep collapsing to best-per-spec rather than splintering into one row each.
    store = await _store_with_benchmark()
    await store.submit(_submission(spec_id="spec-legacy", accuracy=0.60))
    await store.submit(_submission(spec_id="spec-legacy", accuracy=0.85))

    rows = await store.leaderboard("hle")

    assert len(rows) == 1
    assert rows[0].accuracy == 0.85
    assert rows[0].benchmark_revision is None


# --- OME-775: the revision reaches the score read DTO ---------------------------------------


async def test_score_read_schema_carries_the_resolved_revision(tortoise_db: None) -> None:
    store = await _store_with_benchmark()

    score, _ = await store.submit(_revision_submission(metadata={"benchmark_revision": "rev-read"}))

    assert score.benchmark_revision == "rev-read"


async def test_score_read_schema_serialises_an_absent_revision_as_null(
    tortoise_db: None,
) -> None:
    # INVARIANT: absent means null, never omitted — a client must be able to distinguish
    # "no revision recorded" from "field missing from this deployment".
    store = await _store_with_benchmark()

    score, _ = await store.submit(_revision_submission(metadata={"source": "unit"}))

    assert "benchmark_revision" in score.model_dump()
    assert score.benchmark_revision is None


# --- OME-775 follow-up: the board shows only the registered revision ------------------------
# The partition alone was not enough. It stopped one revision displacing another in the
# best-per-spec collapse, but the outer query still ordered every surviving row into ONE
# accuracy ranking — so a stale-revision score could hold rank 1 on a board registered at a
# different revision, presenting two incomparable numbers as a ranking. Verified against a
# running server before this was written.


async def _benchmark_at(revision: str | None) -> ScoreStore:
    store = ScoreStore()
    await store.register_benchmark(benchmark_id="hle", display_name="Fixture", revision=revision)
    return store


async def test_leaderboard_excludes_scores_from_a_non_registered_revision(
    tortoise_db: None,
) -> None:
    # INVARIANT: every entry the board ranks was measured against the revision the board is
    # registered at. A higher score from an obsolete revision must not outrank a current one.
    store = await _benchmark_at("REV-CURRENT")
    await store.submit(
        _revision_submission(spec_id="old-winner", benchmark_revision="REV-OBSOLETE")
    )
    await store.submit(_revision_submission(spec_id="new-entry", benchmark_revision="REV-CURRENT"))

    rows = await store.leaderboard("hle")

    assert [row.spec_id for row in rows] == ["new-entry"]
    assert all(row.benchmark_revision == "REV-CURRENT" for row in rows)


async def test_leaderboard_without_a_registered_revision_filters_nothing(
    tortoise_db: None,
) -> None:
    # WHY: the retained legacy demo benchmarks have no Engine revision (D2). Filtering on a
    # null registered revision would empty their boards entirely.
    store = await _benchmark_at(None)
    await store.submit(_revision_submission(spec_id="legacy-a", benchmark_revision=None))
    await store.submit(_revision_submission(spec_id="legacy-b", benchmark_revision="whatever"))

    rows = await store.leaderboard("hle")

    assert {row.spec_id for row in rows} == {"legacy-a", "legacy-b"}


async def test_leaderboard_at_a_registered_revision_excludes_pre_revision_rows(
    tortoise_db: None,
) -> None:
    # Rows predating OME-775 carry a NULL revision. Once a benchmark declares a revision, such
    # a row cannot be asserted comparable to it, so it does not rank.
    store = await _benchmark_at("REV-CURRENT")
    await store.submit(_revision_submission(spec_id="pre-revision", benchmark_revision=None))
    await store.submit(_revision_submission(spec_id="current", benchmark_revision="REV-CURRENT"))

    rows = await store.leaderboard("hle")

    assert [row.spec_id for row in rows] == ["current"]
