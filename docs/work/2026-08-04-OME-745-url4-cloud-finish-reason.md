---
ticket: OME-745
stack: url4-cloud
status: done
started: 2026-08-04
finished: 2026-08-05
---

# OME-745 — capture finish_reason / refusal and classify a refused turn

## Intent

Sub-issue of `OME-679`, and the hop where the signal is actually lost today.

`_parse_choice` (`apps/url4-cloud/src/url4_cloud/runner/connector.py:262-281`) pulls only
`content` and `tool_calls` out of `data["choices"][0]["message"]`. `finish_reason` is never read —
aigateway produces it and this hop discards it, so **the finish reason dies at the url4
boundary**. The provider `refusal` field is read nowhere in the repo at all.

A hard refusal (`content_filter`, or empty content carrying a `refusal` string) currently
collapses into the generic `aigateway_bad_response` `ResolutionError`, indistinguishable from a
malformed payload — which is exactly the conflation `OME-679` exists to remove.

`OME-744` (merged as `b787cf5d`) added the seam this unit consumes: `ModelResponse`,
`current_response_sink()`, and `ExecutionContext.report_response`.

## Planned changes

- `packages/url4/src/url4/streaming/protocol/signals.py` — `SpanData` gains
  `finish_reasons: list[str] | None` aliased to `gen_ai.response.finish_reasons` (the OTel
  semantic-convention name; every other `gen_ai.*` attribute already uses validation/serialization
  aliases with `populate_by_name`) and `refusal: str | None`.

  Lives in this unit, not `OME-744`, because `packages/url4/pyproject.toml` omits
  `src/url4/streaming/*` from that package's coverage by design — streaming's tests "live with its
  only consumers, in `apps/url4-cloud/tests` — that suite gates it via `--cov=url4.streaming`".
  Change and test stay together.
- `apps/url4-cloud/src/url4_cloud/runner/connector.py` — `_parse_choice` also reads
  `choices[0].finish_reason` and `choices[0].message.refusal`; a `_report_response` beside
  `_report_usage`; reported on **every** round trip of `_chat_completion_loop`; a refused turn
  raises `ResolutionError(code="provider_refusal", permanent=True)`.
- `apps/url4-cloud/src/url4_cloud/runner/executor.py` — `_SpanState` carries it, `_Bridge` handles
  `ModelResponse` as it handles `Usage`, `_finish` passes it to `SpanData`.
- Tests: a new module rather than an append — the append-only gate compares file status
  (`OME-369` / #383 is the line-level fix, still open), so growing an existing test file reads as
  a modified prior test.

No schema/model change, so S1 (migrations) does not apply.

## Test plan

Failing tests first:

- **The lost signal** — a `stop` response reaches `SpanData.finish_reasons`; today nothing does.
- **Refusal → typed failure** — a `content_filter` response raises
  `ResolutionError(code="provider_refusal", permanent=True)`, not `aigateway_bad_response`.
  `permanent=True` matters: a refusal is deterministic, so retrying it burns budget for the same
  answer.
- **Refusal via the provider field** — empty content plus a `refusal` string classifies the same
  way, since not every provider signals refusal through `finish_reason`.
- **Boundary — absent `finish_reason`** (providers that omit it) does not crash and does not
  fabricate a value.
- **Invariant — one entry per round trip.** A web-tool turn is several calls against one span, so
  the intermediate `tool_calls` and the final `stop` must both survive; the span must not collapse
  them.
- **Regression** — a malformed payload still raises `aigateway_bad_response`, so the new code path
  has not swallowed the old error class.
- **Wire shape** — `SpanData` round-trips `gen_ai.response.finish_reasons` by alias AND by field
  name, and serializes under the alias.

## Acceptance

- A refused turn is distinguishable from a malformed one, by error code.
- A normal turn's finish reason reaches the wire frame.
- No prior test modified.
- Gates green: `uv run .claude/scripts/run_gates.py url4-cloud` — ruff · ruff format --check ·
  pyright · `check_layering.py` · `pytest --cov=url4_cloud --cov=url4.streaming
  --cov-fail-under=80`.

## Outcome

- **Merged:** `3a6e4ad3` + `27b274db` + `e015be7f` squash-merged as `b594d6fc` (#506), remote CI
  **23/23 pass**. This completes OME-679's main-landable half: `finish_reason` and the provider
  `refusal` field now survive from aigateway through the url4 boundary onto the wire frame, and a
  refused turn is a typed `provider_refusal` failure rather than a generic malformed-response
  error. The remaining hop — turning that into a refusal-kind failure excluded from the scored
  denominator, plus the refusal-rate headline — is `OME-680`, blocked on the
  `packages/screamingface` SDK drafts landing.
- **Actual files:**

  | File | Planned? | What |
  |---|---|---|
  | `packages/url4/src/url4/streaming/protocol/signals.py` | yes | `SpanData.finish_reasons` (aliased `gen_ai.response.finish_reasons`) + `refusal` |
  | `apps/url4-cloud/src/url4_cloud/runner/connector.py` | yes | `_Choice`, `_parse_choice` extended, `_raise_if_unusable`, `_report_response` |
  | `apps/url4-cloud/src/url4_cloud/runner/executor.py` | yes | `_SpanState.finish_reasons`/`refusal`, `_fold_response`, `map` dispatch, `_finish` pass-through |
  | `apps/url4-cloud/tests/unit/test_finish_reason_capture.py` | yes | 14 new tests across the three seams |
  | `docs/tasks/…-ome-744-…md`, `docs/work/…-OME-744-…md` | **no** | OME-744's status flipped to done here — see Deviations |

- **Gates:** BOTH touched stacks green.
  - `run_gates.py url4-cloud` — **ALL GATES GREEN**: append-only ✓ · ruff ✓ · ruff format ✓ ·
    pyright ✓ · `check_layering.py` ✓ · `pytest --cov=url4_cloud --cov=url4.streaming
    --cov-fail-under=80` ✓. Suite **492 passed, 5 skipped** (was 478 — 14 new). Coverage **97%**;
    `signals.py` **100%**, `connector.py` 96%, `runner/executor.py` 97% (all misses pre-existing).
  - `run_gates.py url4` — **ALL GATES GREEN** (the `signals.py` edit lives in that package):
    1100 passed, coverage 97%.

- **Design notes worth keeping:**
  - `_parse_choice` was split into extraction + `_raise_if_unusable` so the caller can report the
    finish reason **between** them. Reporting after classification would drop the event for a
    refused turn — the exact case OME-679 exists to capture.
  - The refusal check precedes the emptiness check: a `content_filter` turn normally carries null
    content, so testing emptiness first would classify every refusal as malformed.
  - `permanent=True` on `provider_refusal`: a refusal is deterministic, so a retry spends budget
    to be refused again.
  - `SpanData.refusal` is deliberately **not** given a `gen_ai.*` alias — OTel has no semantic
    convention for it, and inventing one would misrepresent a local extension as a standard
    attribute. `finish_reasons` does get the real semconv name.
  - Empty `finish_reasons` renders as `None`, not `[]`, so the attribute is simply **absent** —
    matching how OTel treats `gen_ai.*` attributes. This collapses "made no model call" and "made
    a call that reported no reason" into one wire shape. **Deliberate limit, not an oversight**
    (see Deviations 5).

- **Deviations:**
  1. **Tests in a new module, not appended.** Same append-only-gate limitation hit in `OME-746`:
     the gate compares file status, so growing `test_aigateway_connector.py` reads as a modified
     prior test. `OME-369` / #383 is the line-level fix and is still open. The module docstring
     records why.
  2. **OME-744's mirror and ledger frontmatter are flipped to `done` in this branch.** They still
     read `in_progress` after #488 merged, and a PR that changes only two status lines is not
     worth its own review cycle. Noted in OME-744's close comment.
  3. **`connector.py` is 648 lines, over the skill's 450 guidance** (it was already 589 before
     this change; this unit added ~59). Not split here on purpose: the obvious extraction is the
     ~180-line Tavily tool-loop cluster (`_WEB_TOOLS`, `_execute_tool`, `_dispatch_tool`,
     `_tool_args`, `_truncate_tool_result`, `_tavily_*`) into a `web_tools.py` sibling, which
     would bring the file to ~470 — but that is a pure-move refactor of code unrelated to
     finish-reason capture, and folding it into a behavior-change PR makes review harder. Same
     reasoning that kept the duplicated provider mapper out of `OME-746`. Worth its own item.
  4. **Card gap, still open:** `.claude/sdlc.local.md` has no body section for `url4-cloud` (nor
     `url4`), so the skill's "read the card BODY for the active stack" step had nothing to bind.
     Gate coverage itself is complete. Raised in OME-744's close comment too.
  5. **Review finding — a documented distinction the code never implemented.** Three comments
     (`_SpanState`, `_finish`, `SpanData.finish_reasons`) claimed `None` meant "no model call"
     while `[]` meant "called a model that reported nothing". Untrue: `_fold_response` skips a
     `None` reason, so a call whose provider omitted `finish_reason` leaves the list empty and
     `_finish` renders it `None` — byte-identical to a span that never called a model. The
     `_finish` comment was self-contradictory ("must not look like"), and the only test covering
     absence asserted on the **event stream**, not on `SpanData`, so the claim was unpinned at
     the layer it was made about.

     **Resolved by deleting the claim, not by building state to satisfy it.** A YAGNI grep found
     **zero consumers** of `finish_reasons` anywhere — only this unit's own code and tests; the
     SDK that would read it (`packages/screamingface`) is not on `main`. Adding a `model_calls`
     counter to preserve a distinction nobody reads is speculative generality, and `[]` conveys
     nothing to an OTel consumer that absence does not (the semconv treats `gen_ai.*` as
     absent-or-populated). `_SpanState` is internal, so if a consumer ever needs the difference,
     counting folded events then is additive. All three comments now state the collapse plainly
     and carry an `AIDEV-NOTE:` on how to add the distinction if it is ever wanted, and a new
     `SpanData`-level test pins the collapse as intended rather than accidental.
