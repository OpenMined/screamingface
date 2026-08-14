# Plan — OME-836: flat benchmark identities

Spec: `docs/spec/2026-08-14-OME-836-flat-benchmark-identities.md`.

## OME-837 — URL4 Cloud

1. Make `Benchmark.id` the only catalogue identity and remove `variant` from definition and
   resource serialization.
2. Reduce DRACO to its canonical constants, builder, installer, runtime, and registry entry.
   Delete variant-only tests rather than rewriting them into compatibility tests.
3. Rename HealthBench's ID and all revision-pinned routes to `healthbench-worst30`.
4. Update foundation/benchmark tests and accepted specs to assert the new wire contract.

## OME-838 — ScreamingFace Client

1. Remove `variant` from catalogue decoding and the discoverable `Benchmark` value.
2. Replace smoke/lite examples with canonical `draco` and explicit `limit=1`; delete the DRACO
   Lite generated notebook and its builder.
3. Rename every Client-facing HealthBench identity to `healthbench-worst30`.
4. Make local Scoreboard seeding an exact declaration of all three identities; remove stale empty
   registrations while refusing to delete stored results. Update fixtures, README, URL4 examples,
   and regenerate notebooks from the builder.
5. Remove obsolete curated demos and align the public documentation site with the same three
   identities and Recipe/Benchmark separation.
6. Reject partial Benchmark results at the Client publication seam and keep the quickstart's
   complete publication flow explicit and opt-in.

## Verification

- Search production, tests, docs, and generated notebooks for all three retired IDs and for
  benchmark `variant` decoding.
- Run `python3 .claude/scripts/run_gates.py url4-cloud --skip-append-only`.
- Run `python3 .claude/scripts/run_gates.py screamingface --skip-append-only`.
- Run the public-docs formatter, linter, type check, and production build.
- Inspect the final diff for aliases, fallbacks, dormant installers, and unrelated changes.
