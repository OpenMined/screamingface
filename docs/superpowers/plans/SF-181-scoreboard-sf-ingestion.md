# D-SCORE-006 — SF → scoreboard ingestion (scoreboard side)

**Owner:** Dmitry (scoreboard side). SF/Electron side = Sergey (out of scope here).
**Phase:** 3 / Week 3 · **Estimate:** ~0.5d (scoreboard side) · **Branch:** `SF-XXX-scoreboard-sf-ingestion` (SF "next available" — assign at ticket time).
**Depends on:** D-SCORE-002 (persistence), D-SCORE-003 (POST /v1/scores), DEMO-017 (local eval persistence, SF side).
**Confidence:** ~96%.

> **Scope decision (confirmed with user):** the submission wire shape uses a **nested
> `client: {name, version, platform}`** object, exactly as the task description documents.
> This is the scoreboard-side plan for the paired (A+B) task; the SF/Electron deliverables
> (`PublishDialog`, redaction, toasts) are Sergey's and appear here only as the interface contract.

---

## Goal

Make the public scoreboard accept the SF desktop "Publish to Leaderboard" submission, confirm CORS
allows the Electron renderer, and add a fixture-based round-trip test that simulates the real SF
payload. The receiving endpoint (`POST /v1/scores`), idempotency, and models already exist
(D-SCORE-002/003); this ticket reconciles the **submission schema** with the documented SF wire
shape and proves the round-trip.

## In scope (scoreboard / this PR)

- `scores/schemas.py` — `ScoreSubmission` accepts a **nested `client`** (wiring the already-present
  but currently-unused `ClientInfo` model).
- `scores/store.py` — map the nested `client` onto the existing flat model columns.
- CORS — verify (and, only if needed, finalize) that the Electron renderer origin is allowed.
- `tests/unit/test_sf_payload.py` — **new**, fixture-based end-to-end round-trip of the SF payload.
- Update existing tests that build the submission shape (`test_scores_routes.py`, `scores/test_store.py`).

## Out of scope (SF side — Sergey; documented as the contract only)

- `apps/desktop/.../PublishDialog.tsx`, `use-publish-score.ts`, `url4-redaction.ts`, `EvalRunDetail.tsx`.
- Private-spec detection / redaction (SF-side logic).
- `spec_name` → `benchmark_id:spec_id` convention (DEMO-014, SF side).
- `SF_SCOREBOARD_URL` default coordination (D-SCORE-007).
- No DB schema / migration change (the `Score` table stays flat).

---

## Current state (validated against the code)

- `POST /v1/scores` + `GET /v1/scores/{id}` exist (`routes/scores.py`, D-SCORE-003). Idempotency via
  the `Idempotency-Key` header + `IdempotencyKey` model with a 24h TTL (D-SCORE-002). Repeat key →
  `200` with the original score; expired key → new row.
- Validation already enforced by the route/schema: `version` is `Literal[1]`; `url4_expression`
  non-empty, ≤ 32 000 chars; `accuracy ∈ [0,1]`; `accuracy ≈ correct/total` within `Decimal("0.01")`
  (else `400`); `total_questions > 0`; `correct ≤ total`; unknown `benchmark_id` → `404`;
  `extra="forbid"` on all DTOs.
- **CORS is already permissive:** `Settings.cors_origins` defaults to `["*"]`; `main.py` adds
  `CORSMiddleware(allow_origins=cors_origins, allow_credentials=False, allow_methods=["*"],
  allow_headers=["*"])`. This matches the task's "permissive `*` acceptable for v1" — **no config
  change is required**, only verification + a test.
- **The mismatch this ticket fixes:** the endpoint currently accepts **flat** `client_name` /
  `client_version` / `client_platform`, but the documented SF payload sends **nested** `client:{…}`.
  With `extra="forbid"`, the documented payload is rejected `422` today. A `ClientInfo` model
  (name/version/platform) is already defined in `schemas.py` but **unused** — this ticket wires it in.

---

## Design

### 1. Nested `client` on the input DTO (`scores/schemas.py`)

```python
class ScoreSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    benchmark_id: str
    spec_id: str
    url4_expression: Annotated[str, Field(max_length=32_000)]
    submitted_by: str | None = None
    accuracy: float
    total_questions: int
    correct_questions: int
    ran_with_providers: list[str]
    ran_at_local: datetime | None = None
    client: ClientInfo | None = None          # <- was client_name/version/platform (flat)
    metadata: dict[str, Any] | None = None
    # ... existing validators unchanged ...
```

`ClientInfo` (already present, `extra="forbid"`, all fields optional) becomes live.

**`ScoreSchema` (the read/response DTO) stays flat** (`client_name/version/platform`). Rationale: the
read contract is consumed by the public leaderboard portal (D-SCORE-005); the task only specifies the
*submission* shape. Keeping the response flat avoids rippling into the portal for no task benefit. The
input/output asymmetry is a deliberate, scoped trade-off (revisit only if a separate ticket asks to
nest the read DTO too).

### 2. Map nested → flat columns (`scores/store.py`)

The `Score` model/table stay flat (no migration). `_submission_to_kwargs` unpacks the nested client:

```python
def _submission_to_kwargs(submission: ScoreSubmission) -> dict[str, object]:
    client = submission.client
    return {
        "benchmark_id": submission.benchmark_id,
        "version": submission.version,
        "spec_id": submission.spec_id,
        "url4_expression": submission.url4_expression,
        "submitted_by": submission.submitted_by,
        "accuracy": submission.accuracy,
        "total_questions": submission.total_questions,
        "correct_questions": submission.correct_questions,
        "ran_with_providers": submission.ran_with_providers,
        "ran_at_local": submission.ran_at_local,
        "client_name": client.name if client else None,
        "client_version": client.version if client else None,
        "client_platform": client.platform if client else None,
        "metadata": submission.metadata,
    }
```

`_score_to_schema` is unchanged (model flat → `ScoreSchema` flat).

### 3. CORS (`config.py` / `main.py`)

No change needed — already `allow_origins=["*"]`, `allow_credentials=False`. This works for the
Electron renderer, whose `fetch` carries `Origin: file://`/`null`; with credentials disabled,
Starlette echoes `Access-Control-Allow-Origin: *`. We only **assert** this in a test. (If credentials
were ever needed, `*` + credentials is disallowed by the spec and we'd switch to explicit origins —
not needed for the open-write v1 API.)

### 4. Tests

- **Update existing submission-builders to nested** (one-line-ish each, fixes all dependents):
  - `tests/unit/test_scores_routes.py::_valid_payload` → `"client": {"name": …, "version": …, "platform": …}`.
  - `tests/unit/scores/test_store.py` → the `ScoreSubmission(...)` builder uses `client=ClientInfo(...)`.
  - `tests/unit/test_leaderboard_routes.py` is **untouched** (it creates `Score` rows directly = flat columns).
- **New `tests/unit/test_sf_payload.py`** (reuse the `tortoise_db` + ASGI `AsyncClient` pattern from
  `test_scores_routes.py`; register a benchmark in the fixture):
  1. POST the **exact documented SF payload** (nested `client`) with `Idempotency-Key: <eval_run_id>`
     → `201`; assert the response round-trips (incl. `client_name/version/platform` derived from the
     nested input, `verified_by_openmined is False`).
  2. **Idempotent:** POST again with the same `Idempotency-Key` → `200` and the **same `id`**
     (one row); confirm via `GET /v1/scores/{id}`.
  3. **Unknown benchmark** (not pre-registered) → `404` field error on `benchmark_id`.
  4. **CORS:** a request carrying an `Origin` header (app built with `cors_origins=["*"]`) returns
     `Access-Control-Allow-Origin: *`. (The shared in-memory fixture uses `cors_origins=[]` to keep
     other tests deterministic, so this case constructs its own app with `cors_origins=["*"]`.)
  5. **Strictness:** a payload with an unknown top-level field, or the **legacy flat** `client_name`,
     is rejected `422` (documents that the contract is now nested-only).

---

## tortoise-dev / SOLID check (requested)

- **No model or migration change** → the `tortoise-dev` model rules are unaffected (the scoreboard
  models already comply: `models/` subpackage, one model per file, abstract `Base*`, `Meta` first —
  per D-SCORE-002). The `Score` table keeps its flat `client_*` columns.
- **SRP / layering preserved:** the change lives entirely in the DTO (`schemas.ScoreSubmission`) and
  the DTO→model mapping (`store._submission_to_kwargs`) — the exact seam meant to absorb wire-shape
  changes. The persistence model and the read DTO are untouched, so the storage and read contracts
  stay stable. No raw SQL is added.
- **DRY:** wiring the existing `ClientInfo` removes dead code rather than adding a parallel definition.

---

## Wire contract (for the paired session with Sergey)

```
POST /v1/scores
Content-Type: application/json
Idempotency-Key: <eval_run_id>

{ "version": 1, "benchmark_id": "hle", "spec_id": "hle-ensemble-three",
  "url4_expression": "...", "accuracy": 0.81, "total_questions": 1000,
  "correct_questions": 810, "ran_with_providers": ["claude","codex","gemini"],
  "submitted_by": null, "ran_at_local": "2026-05-04T11:55:00Z",
  "client": { "name": "screamingface-desktop", "version": "0.4.2", "platform": "darwin" },
  "metadata": null }
```

- SF **must** send `client` **nested** (flat `client_*` is now `422`).
- `accuracy` must equal `correct_questions/total_questions` within `0.01`, else `400`.
- `benchmark_id` must be **pre-registered** on the scoreboard, else `404` — coordinate which
  benchmarks are seeded (e.g. `livetruth`, `hle`); SF publishing to an unregistered benchmark fails.
- Response is **flat** `ScoreSchema`; SF reads `id` for the success-toast deep link
  `<portal>/spec.html?benchmark=<benchmark_id>&spec=<spec_id>`.
- Repeat POST with the same `Idempotency-Key` → `200` + original row (no dupes).

## Acceptance criteria (scoreboard side)

- [ ] `POST /v1/scores` accepts the documented nested-`client` SF payload → `201`.
- [ ] Double POST with the same `Idempotency-Key=<eval_run_id>` → one row (`200` on repeat;
      verifiable via `GET /v1/scores/{id}`).
- [ ] CORS allows the renderer (`Access-Control-Allow-Origin: *` present).
- [ ] `test_sf_payload.py` simulates the SF shape and confirms the round-trip.
- [ ] Existing route/store tests updated to nested `client` and green.

## Build sequence

1. `scores/schemas.py`: `ScoreSubmission.client: ClientInfo | None` (drop the 3 flat fields).
2. `scores/store.py`: nested→flat mapping in `_submission_to_kwargs`.
3. Update `test_scores_routes.py::_valid_payload` and `scores/test_store.py` builders to nested.
4. Add `tests/unit/test_sf_payload.py` (round-trip + idempotency + 404 + CORS + 422 strictness).
5. Gates.

## Validation

```bash
cd apps/scoreboard
uv run pytest tests/unit -q
uv run ruff check . && uv run ruff format --check .
uv run pyright
```

(The Postgres-gated migration smoke is unaffected — no schema change.)

## Risks

- **Input-contract change (flat → nested).** Breaks any flat-sending client; none is deployed (SF is
  the first client and is being built in this paired task). Existing tests are updated in the same PR,
  so CI stays green.
- **Benchmark must exist.** A publish to an unregistered `benchmark_id` returns `404`; ensure the
  target benchmarks are seeded (`seed.py` / `register_benchmark`). Coordination item for the manual e2e.
- **CORS `*` + no credentials** is correct for the open-write v1 API; revisit if auth is ever added.

## Notes

- SF number is "next available" — assign at ticket creation and name the branch accordingly.
- Plan location: `docs/superpowers/plans/` (per repo convention); task brief lives at
  `.agent-team-D-SCORE-006/initial_task_description.md`.
