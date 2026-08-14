---
title: OME-836 — Flat benchmark identities
status: accepted
created: 2026-08-14
ticket: OME-836
related:
  - OME-837
  - OME-838
  - docs/plan/2026-08-14-OME-836-flat-benchmark-identities.md
---

# Flat benchmark identities

## Decision

Benchmark discovery exposes one flat, complete identity per independently meaningful benchmark.
Candidate construction strategies remain Client Recipes; cheap development projections are not
public Benchmarks.

The public catalogue is exactly:

- `draco` — canonical DRACO. Bounded examples use the ordinary exact `limit` parameter.
- `ifeval` — canonical IFEval.
- `healthbench-worst30` — the separately named, non-canonical HealthBench Professional challenge.

`draco/lite`, `draco/smoke`, and `healthbench/worst30` are removed. There are no aliases,
redirects, deprecated registrations, fallback decoding, or compatibility translations.
Hierarchical selections fail Client validation as invalid flat identities; unknown flat ids reach
the ordinary unknown-benchmark path.

## Contract

`id` is the complete benchmark identity. `revision` versions the executable benchmark. The
separate `variant` field is deleted from `screamingface.benchmark.v1`, Engine list resources,
and the Client's discoverable `Benchmark` because it would duplicate or contradict the flat `id`.

`limit=N` changes only the exact case selection of the named Benchmark. It never changes its
rubric, judge passes, checker, aggregation, or identity. Consequently `benchmark="draco",
limit=1` is one canonical DRACO case—not the retired cheap smoke protocol.

## Removal boundary

All DRACO lite/smoke definitions, route constants, revision hashes, runtime installers, public
tests, docs, and notebooks are deleted. Shared canonical DRACO machinery remains only where
canonical DRACO uses it.

The HealthBench challenge keeps its existing 157-case selection, grading, scoring, and revision
inputs. Only its public identity and revision-pinned route prefix change to
`healthbench-worst30`.

## Acceptance

- Engine discovery returns exactly the three flat IDs above and no `variant` field.
- Hierarchical IDs fail flat-ID validation; they are never translated.
- Client discovery has no `Benchmark.variant` attribute.
- Generated examples use canonical DRACO plus explicit limits and the flat HealthBench ID.
- Package docs expose the same three identities and teach corrective behavior as Client Recipes.
- URL4 Cloud and ScreamingFace gates are green.
