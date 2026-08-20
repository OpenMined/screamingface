---
ticket: OME-904
stack: python
status: in_progress
started: 2026-08-20
finished:
---

# OME-904 — Show benchmark descriptions on the leaderboard (engine text as the only copy)

## Intent

The leaderboard prints "No description published." for every benchmark because the
deployed seed list carries ids + revisions only, and Helm replaces lists wholesale —
so the descriptions hand-copied into `apps/scoreboard/charts/scoreboard/values.yaml`
never reach the database. Good text already exists in the Engine benchmark definitions.
This unit makes the Engine's benchmark catalogue the ONLY copy: the scoreboard seed job
fetches `GET {engine}/v1/benchmarks` at deploy and writes description / focus /
dataset_url / revision from it, so a deploy override physically cannot blank the text.

Owner decisions (2026-08-20):
- Mechanism: seed job fetches the Engine catalogue at deploy (not build-time codegen,
  not request-time merge).
- The Engine `Benchmark` gains `focus` + `dataset_url` so all four fields have one copy.
- Tracked as one ticket / one PR spanning both apps (owner override of the
  cross-cutting split rule).

## Planned changes

- `apps/screamingface-engine/src/screamingface_engine/benchmarks/definition.py` — optional
  `focus` / `dataset_url` on `Benchmark`, surfaced in `_metadata()`.
- `apps/screamingface-engine/src/screamingface_engine/benchmarks/{draco,ifeval,healthbench}/definition.py`
  — carry the focus / dataset link text.
- `apps/scoreboard/src/scoreboard/seed.py` — fetch + map the Engine catalogue, merge with
  the configured legacy rows.
- `apps/scoreboard/charts/scoreboard/values.yaml` + `templates/job-seed-benchmarks.yaml`
  — `seedBenchmarks.engineUrl`, legacy demo rows only.
- Tests on both sides.

## Test plan

Engine (`tests/unit/test_benchmark_display_metadata.py`): a declared focus line and dataset link
reach both the catalogue entry and the detail resource; a benchmark declaring neither publishes
neither key (absent, never null); blank focus and non-http(s) dataset links are refused; the
three installed benchmarks publish the focus lines and dataset links the board displays, IFEval
deliberately without one; the published revision is the computed revision and display metadata
does not move it.

Scoreboard (`tests/unit/test_seed_engine_catalog.py`): a catalogue entry becomes a seed row with
`title` mapped to `display_name`; an entry without display extras seeds them absent; catalogue
fields the board does not display are ignored; the catalogue path is appended to the configured
origin; transport failure, error status, non-JSON body, and a missing displayed field each
surface as `EngineCatalogUnavailable` rather than an httpx/json exception; an Engine row wins
over a configured row sharing its id and the shadowed id is reported; a configured row the
Engine does not publish is kept; the seeded revision is the catalogue revision, never a
configured literal; an unreachable Engine leaves an already-seeded board untouched and does not
fail; an unreachable Engine does fail when no row carries a revision; no configured Engine URL
seeds only the configured rows.

## Acceptance

- No file outside an Engine benchmark definition states a benchmark's description, focus, or
  dataset link.
- `helm template` renders `SCOREBOARD_SEED_ENGINE_URL` when `seedBenchmarks.engineUrl` is set
  and omits it when empty.
- Both stacks' gates green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned, plus `apps/scoreboard/src/scoreboard/scores/store.py`
  (`has_registered_revision`, so the bootstrap check reads the database through the store rather
  than reaching for the ORM from the seed module) and
  `apps/scoreboard/charts/scoreboard/README.md`. The before/after diagram is NOT committed
  (owner decision 2026-08-20): it lives on the Linear issue as an attachment, keeping binaries
  out of the repository. Source is in the session scratchpad. No migration: `benchmarks` already carries
  `description`, `focus`, `dataset_url`, and `revision` columns, so S1 does not apply.
- **Commits:** see the OME-904 branch.
- **Gates:** `run_gates.py screamingface-engine` ALL GATES GREEN; `run_gates.py scoreboard` ALL
  GATES GREEN. The review round ran with `--skip-append-only` under owner approval (below).

## Review round (PR #657, 2026-08-20)

Eight findings, all verified before any fix — two of them by executing the behaviour rather
than reading it (`follow_redirects` defaults to False; `.json()` raises `UnicodeDecodeError`,
not `JSONDecodeError`, on a non-UTF-8 body).

- **Release-breaking:** `httpx` was declared under `[dependency-groups].dev` while the image is
  built with `uv sync --frozen --no-dev`, so `import httpx` in `scoreboard.seed` would have
  been a `ModuleNotFoundError` on every deploy. No test could see it, because tests install the
  dev group. Moved to `[project.dependencies]`, relocked, and pinned by a test that reads
  `pyproject.toml` — the only kind of test that can defend this.
- **"Engine is the only copy" held on the happy path only.** With the catalogue unreadable
  there is nothing to shadow with, so the deploy's own stale entries would have overwritten
  good rows with null descriptions — OME-904 reproduced by its own fix. Configuration may now
  never write an entry asserting a `revision` the Engine did not publish this pass, nor one
  naming an existing Engine-owned row.
- **The bootstrap guard read the database after writing to it**, so a configured entry carrying
  a revision satisfied the guard with the row it had just written. The prior state is now read
  before anything is seeded.
- **The likeliest misconfiguration was silent** (chart upgraded without `engineUrl`). Those
  entries are now refused and named loudly.
- One unreadable catalogue entry rejected the whole batch; entries are now validated
  independently, and the Engine enforces the board's column widths so over-long text fails
  where it is written instead of at deploy.
- Redirects are followed; `UnicodeDecodeError` is caught; the fetch retries transport failures
  and 5xx (never a 4xx or a mangled body); and `parser.error` no longer wraps the whole run, so
  an unrelated `ValueError` can no longer surface as a command-line usage error.

Owner-approved prior-test edits (sdlc rule 5, 2026-08-20): 18 lines across two committed test
files — five mechanical (the fetch returns a `CatalogRead` so it can report unreadable
entries), eight adding `retry_delay=0` so failure tests do not sleep through the real backoff
(28s -> 0.07s), three widening a fixture helper, and one changed expectation, because finding 5
proved batch-rejection wrong. A new test covers the case that must still raise.
- **Deviations:**
  - The plan's step 1 included pinning each installed benchmark's revision as a literal. That
    test was written, went red, and was replaced rather than satisfied: the three revisions the
    chart pins (`draco 1c58b3085912e304`, `ifeval 0b88a52b5f10a6d9`,
    `healthbench-worst30 6cd57aee171fbdc4`) do NOT match what this checkout computes
    (`66a463248586b277`, `1cba769ece27f7ef`, `39cfd96b068f7230`). Pinning literals in a test
    would have recreated exactly the hand-copied second copy this ticket removes, so the test
    now asserts the published revision is the benchmark's own computed value, and the board's
    protection lives where it belongs — the seeded revision comes from the catalogue response.
  - That mismatch is a PRE-EXISTING drift, surfaced by this work and not caused by it: the
    deployed board's revisions are stale relative to this checkout's Engine. It also means the
    ticket's "quick unblock" (re-seed from `values.yaml`) would seed stale revisions. Reported
    to the owner.
