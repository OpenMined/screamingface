from __future__ import annotations

import uuid

from tortoise import fields

from .base import BaseScoreboardModel


class BaseScore(BaseScoreboardModel):
    class Meta:
        abstract = True

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    version = fields.IntField(default=1)
    spec_id = fields.CharField(max_length=255, db_index=True)
    url4_expression = fields.TextField()
    submitted_by = fields.CharField(max_length=255, null=True)
    submitted_at = fields.DatetimeField(auto_now_add=True)
    accuracy = fields.FloatField()
    total_questions = fields.IntField()
    correct_questions = fields.IntField()
    ran_with_providers = fields.JSONField()
    ran_at_local = fields.DatetimeField(null=True)
    client_name = fields.CharField(max_length=128, null=True)
    client_version = fields.CharField(max_length=64, null=True)
    client_platform = fields.CharField(max_length=32, null=True)
    # WHY True: a TEMPORARY placeholder, not a verification claim.
    #
    # Nothing re-runs submissions yet (OME-414 is unstarted and unstaffed), so with
    # default=False every row on the board read "unverified" permanently. Nothing
    # attests execution provenance either: the SDK takes independent engine_url and
    # scoreboard_url, and the chart ships authMode: disabled, so a submission is an
    # unattested client payload. This field therefore asserts nothing today.
    #
    # INVARIANT: the public portal must not claim more than this. index.html and
    # benchmark.html state that scores are self-reported and that this column does not
    # yet distinguish rows. They previously said "Verified means OpenMined
    # independently reproduced the run", which this default would have turned into a
    # false claim on every row. Change the default and that copy together, or the
    # board lies.
    #
    # INVARIANT: never client-settable. Absent from ScoreSubmission, so sending it is a
    # 422. The trust signal must not be assertable by the party it exists to constrain.
    #
    # AIDEV-NOTE: OME-821 replaces this with a real distinction (self-reported vs
    # OpenMined-run); OME-414 is what makes "reproduced" possible at all. Until one of
    # them lands, do not build a UI that filters or ranks on this field. Not because
    # the value is uniform — rows predating this change keep false, since D5 forbids a
    # backfill — but because the value certifies nothing either way. A filter would
    # therefore split rows by whether they predate the default change while presenting
    # itself as a verification filter, which is worse than filtering nothing
    # (review of #588).
    verified_by_openmined = fields.BooleanField(default=True)
    # INVARIANT: the Engine benchmark revision this score was produced against. The
    # leaderboard partitions ranking on (spec_id, benchmark_revision) so results measured
    # against different dataset/protocol revisions never rank against each other (OME-775).
    # WHY nullable + indexed: OME-322's imported LMArena baselines never ran at any revision
    # and every row predating this change has none, so no backfill is possible; indexed
    # because it is a ranking partition key.
    # AIDEV-NOTE: the Client sends this inside the free-form `metadata` dict today; the store
    # promotes it via _resolve_benchmark_revision. Read that before changing the wire shape.
    benchmark_revision = fields.CharField(max_length=64, null=True, db_index=True)
    metadata = fields.JSONField(null=True)
    # INVARIANT: sha256 hex over the submission's recipe identity (benchmark, spec,
    # url4 expression, result numbers, provider order) — NOT submitted_by or client
    # metadata. Unique so the DB itself rejects a duplicate recipe, independent of
    # any client-supplied Idempotency-Key (OME-391 / C28). Nullable so this column
    # can be added to a table with pre-existing rows without a backfill migration —
    # multiple NULLs don't violate a unique constraint, and every row created from
    # here on always gets one (the store always computes it on submit).
    content_hash = fields.CharField(max_length=64, unique=True, null=True)
    # FEATURE: OME-323 — manual open/closed correction, operator-only (never set via
    # the public submission API). `null` defers to the classification registry
    # (scoreboard.classification.openness); an explicit "open"/"closed" wins outright
    # over whatever the registry would have said, without a code deploy.
    openness_override = fields.CharField(max_length=8, null=True)


class Score(BaseScore):
    class Meta:
        table = "scores"
        indexes = (
            ("benchmark_id", "accuracy"),
            ("benchmark_id", "spec_id", "submitted_at"),
        )

    benchmark = fields.ForeignKeyField(
        "models.Benchmark",
        related_name="scores",
        on_delete=fields.OnDelete.RESTRICT,
    )
