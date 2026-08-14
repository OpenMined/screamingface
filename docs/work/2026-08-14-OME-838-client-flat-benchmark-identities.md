---
ticket: OME-838
stack: screamingface + public-docs
status: done
started: 2026-08-14
finished: 2026-08-14
---

# OME-838 — Client flat benchmark identities

## Intent

Align Client discovery, examples, and local development data with the flat Engine identities.

## Planned changes

- Remove discoverable `Benchmark.variant` and variant decoding.
- Delete DRACO Lite material; use canonical DRACO limits elsewhere.
- Rename HealthBench references and regenerate notebooks.

## Test plan

- Discovery/result tests, notebook generation checks, and full ScreamingFace gates.

## Acceptance

- No Client code or generated example names a retired benchmark identity.

## Outcome

- **Actual files:** Client discovery/resource adapters, flat-id validation, local Scoreboard seed,
  Leaderboard wire/submission validation, README, deterministic notebook builder/examples/checker,
  tests, and public-docs Client pages. The local seed now declares all three identities exactly,
  removes only empty stale registrations, and refuses to delete stored results.
- **Commits:** this branch's squash-ready OME-836 implementation commit.
- **Gates:** ScreamingFace and Scoreboard stack gates green; public-docs formatter, linter,
  type-check, and build green.
- **Deviations:** deleted both curated `09_demo*` notebooks because they used the retired
  pre-release SDK and a retired hierarchical identity; all remaining examples are deterministic
  builder outputs. The review added complete-run publication enforcement after finding that the
  Scoreboard cannot compare a limited rehearsal fairly with a full canonical run.
