---
ticket: OME-400
stack: screamingface
status: done
started: 2026-07-20
finished: 2026-07-20
---

# OME-400 — Phase 9B.1 Hugging Face discovery and connections

## Intent

Extend the application-owned ScreamingFace engine profile to expose Hugging Face Inference
models already advertised by AI Gateway, without copying a model list or claiming Tavily/tool
support before it exists. Researchers must be able to discover URL4-safe HF routes and configure
the Gateway-owned HF API-key connection through the existing `sf.connect()` boundary; the SDK
continues to contact only the configured ScreamingFace engine.

## Planned changes

- Record the approved Phase 9 HF/Tavily boundary in the OME-400 architecture plan and a normative
  Phase 9 contract.
- Add append-only engine tests for strict HF Gateway-ID normalization, URL4-safe provider pins,
  malformed/duplicate IDs, tool-free registry records, and API-key connection forwarding.
- Update `screamingface_engine.catalog` to derive HF routes from the startup Gateway model snapshot
  and advertise the HF API-key provider.
- Represent providers without OAuth using `callback_path=None`; never invent an unused callback.
- Update the temporary engine README with the discovered HF route and credential boundary.
- Add a dated quickstart compatibility note explaining the observed Gemini 2.5/new-project
  failure, AI Gateway's missing Gemini 3 registrations, and the non-Gemini HF boundary.
- Add an append-only notebook contract test and regenerate the output-free quickstart from its
  canonical builder.
- Do not modify generic `packages/url4`, AI Gateway, notebooks, Tavily execution, or the public
  benchmark/tool API in this unit.

## Test plan

- RED: `huggingface/<org>/<model>:<provider>` maps to the public URL4-safe
  `huggingface/<org>/<model>~<provider>` while preserving the exact private Gateway model ID.
- RED: malformed HF IDs, missing provider pins, reserved `~`, and duplicate public aliases fail
  startup rather than producing ambiguous routes.
- RED: the public registry advertises Hugging Face with API-key auth and advertises no tools on HF
  models.
- RED: the existing engine connection control plane creates and reads the managed Hugging Face
  API-key connection through AI Gateway without exposing the key.
- GREEN: run the new tests, all prior engine/SDK tests, and the authoritative ScreamingFace gate.

## Acceptance

- Adding/removing a valid pinned HF model in AI Gateway changes ScreamingFace discovery after an
  engine restart without a ScreamingFace model-list edit.
- `sf.models.list(query="huggingface/")` can return URL4-safe HF model IDs without adding an
  unreviewed provider-filter API.
- `sf.connect("huggingface", api_key=...)` traverses SDK -> engine -> AI Gateway only.
- HF route execution restores the exact colon-pinned Gateway model ID.
- No HF model claims `web_search`, `web_fetch`, or Tavily support in Phase 9B.1.
- All malformed catalog and unsupported-auth paths fail explicitly; there is no static model or
  credential fallback.

## Outcome

- **Actual files:** recorded the Phase 9 normative contract and architecture status; updated the
  engine catalog, callback-path set, and README; added focused HF catalog/connection tests; updated
  the owner-approved strict provider/catalog fixtures; added SDK discovery coverage; and added a
  dated Gemini/HF compatibility warning to the generated output-free quickstart with an append-only
  contract test.
- **Commits:** `feat(screamingface): discover Hugging Face models` (this commit).
- **Gates:** 49 focused HF/connection tests green; 168 complete engine tests green; 30 focused SDK
  registry tests green; six quickstart warning/regression tests green; `uv run
  .claude/scripts/run_gates.py screamingface --skip-append-only` passed Ruff lint/format, Pyright,
  SDK and engine coverage, fixtures, deterministic notebooks, and wheel build.
- **Deviations:** the append-only precheck was skipped under the owner's explicit approval to
  update prior exact provider/catalog expectations when adding Hugging Face. No prior behavioral
  assertion was weakened. The quickstart warning was added at the owner's request after the first
  green gate; it describes the observed new-project failure as conditional rather than a universal
  Google rule. Interactive notebook outputs and kernel metadata were regenerated away from the
  canonical notebooks before the final gate.
