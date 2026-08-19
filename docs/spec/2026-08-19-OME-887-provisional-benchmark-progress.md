# OME-887 — Benchmark-native provisional Evaluation progress

## Decision

The ScreamingFace Engine owns live Benchmark progress. Each independently executed Candidate
publishes immutable aggregate snapshots after meaningful Case-stage transitions. URL4 remains the
execution and ordered telemetry transport; it does not learn Benchmark concepts and
`packages/url4` is unchanged.

Snapshots travel as a strictly named structured `ai.url4.log` record on the existing sequenced
CloudEvents stream. The Engine maps a best-effort, run-scoped internal progress signal into that
record. The Client recognizes only the exact ScreamingFace semantic convention and decodes it into
a public immutable `BenchmarkProgress` Event; ordinary logs remain ordinary logs. A publication,
decoding, or monotonicity failure drops only that snapshot and can never fail the Evaluation.

## Snapshot contract

One snapshot describes one Candidate Run and carries:

- Benchmark id and immutable revision;
- selected Case total;
- queued, running-Candidate, grading, and complete Case counts;
- numerically scored Case count;
- coverage (`scored / selected`, rounded to four decimals);
- Benchmark-native provisional score (`finite number | null`).

The stage counts always sum to the selected total. Complete and scored counts are monotonic,
`scored <= complete`, and coverage is derived rather than supplied independently. A null score is
required until at least one Case is gradeable.

## Scoring authority

The same Benchmark aggregate adapter used for the final `CandidateResult` computes provisional
scores over completed rows. Pending rows are internal ungradeable placeholders used only to keep
selection positions stable; they never become public Case failures or zeroes. The Client never
averages Case grades or interprets a Benchmark's score range.

The final snapshot accounts for every selected Case and must equal the final Candidate Result's
score and coverage.

## Presentation

- Display one per-Candidate completion bar whose fill is exactly `complete / selected`; Candidate
  and grading occupancy remain explicit text and never make an incomplete bar look complete.
- Use the brand fusion gradient, anchored at the fill's leading edge, for the completion bar.
- Display `score so far` only once a provisional score exists. Before the first grade, display
  `awaiting first grade`; after a fully unscored selection, display `score unavailable`.
- Display explicit scored coverage, including negative Benchmark-native scores.
- Multi-Candidate Evaluations render one independently named row per Candidate; no scores or Case
  counts are combined across Candidates.
- Headless progress and `on_event` receive the same public `BenchmarkProgress` Event.

## Privacy and resilience

Snapshots contain counts and aggregate score only. They never contain Case ids, inputs, outputs,
private rubrics, grader prompts, or provider errors. Intermediate snapshots are self-contained;
replay and skipped intermediate states cannot double-count work. The final Result remains the
authority for the returned Report. Progress metadata or provisional aggregation failures are
fail-open and never alter Candidate Invocation, grading, or the final Result.

An Engine process may terminate successfully while Benchmark grading produced incomplete output.
In that case the Client presents the Evaluation as `incomplete`, not `succeeded`.
