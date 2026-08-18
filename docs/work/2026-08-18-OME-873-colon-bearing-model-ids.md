---
ticket: OME-873
stack: url4-cloud
status: done
started: 2026-08-18
finished: 2026-08-18
---

# OME-873 — Route aigateway's colon-bearing model ids via a `~` encoding

## Intent

`ModelRegistry` (OME-859) partitions aigateway's 117 compiled model ids into `routable` (88)
and `aigateway_only` (29) — the 29 carry a literal `:` (e.g.
`huggingface/openai/gpt-oss-120b:cerebras`), which no URL4 path segment may contain, so they
are declared for the OME-819 drift guard but never enter the runnable world. This unit makes
them routable by remapping `:` → `~` (already `ROUTE_ID_RE`-legal) at the route boundary, and
reverting at the single point the real request reaches aigateway, so `ModelSpec.id` is
uniformly route-legal everywhere and the real gateway id is recovered by one unconditional,
pure decode call exactly where it's needed. Discovery (`GET /v1/models` /
`GET /v1/model-parameters`) is extended to advertise these ids in their encoded form, so what
a caller sees is exactly what they should type into a url4 expression.

## Planned changes

- `src/url4_cloud/models/registry.py` — add `encode_route_id`/`decode_route_id`; reserve `~`
  at seed-validation time (reject a literal `~` in any slug/id).
- `src/url4_cloud/world_config.py` — `_merge()` keys the merged dict by the encoded id for
  every source (registry-routable, registry-aigateway_only, TOML-declared); `declared_model_ids()`
  returns decoded (real) ids so it still matches aigateway's own catalog response;
  `_reject_unroutable_default` repurposed to detect a literal `:` in `default_route` and point
  at the `~` form.
- `src/url4_cloud/runner/connector.py::_chat_completion_loop` — decode once at the top into a
  `real_id` local; use it for the wire `body["model"]` and `_report_usage`.
- `src/url4_cloud/catalog/executable.py::ExecutableCatalog.fetch` — rewrite each retained
  item's `id` through `encode_route_id` before returning.
  `ExecutableModelParameterSource.fetch_model_parameters` — decode the caller-supplied `model`
  before the membership check and before forwarding to the real source.

## Test plan

- `models/registry.py`: `encode_route_id`/`decode_route_id` round-trip (including identity on
  ids with no colon); registry construction rejects a slug containing a literal `~`.
- `world_config.py`: an `aigateway_only` id now appears in `section.models` under its encoded
  form; a TOML entry can override one of these (matched by its encoded id); `declared_model_ids`
  returns the real (decoded) id; a literal `:` in `default_route` gets the specific "use `~`"
  error, not the generic "not declared" dump.
- `connector.py`: calling the encoded route sends the real (colon) id as `"model"` on the wire
  and reports usage under the real id.
- `catalog/executable.py`: a retained catalog item whose real id contains `:` is rewritten to
  its encoded form; `fetch_model_parameters` accepts the encoded id from the caller and forwards
  the decoded real id upstream.
- Existing pinned tests updated (owner-approved, see ticket): `test_an_aigateway_only_id_never_enters_the_world`,
  `test_control_plane_and_runner_read_the_same_declared_ids`,
  `test_a_default_route_naming_an_aigateway_only_id_is_refused`.

## Acceptance

- All 117 declared ids (not just 88) are addressable from a url4 expression, each under a
  `ROUTE_ID_RE`-legal path.
- A call through one of the 29 sends aigateway the real, colon-bearing id — verified by an
  end-to-end connector test asserting the wire body.
- `GET /v1/models` / `GET /v1/model-parameters` advertise the 29 in encoded form and accept
  the encoded form back.
- `run_gates.py url4-cloud` green.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** matched the plan exactly.
  - `src/url4_cloud/models/registry.py` — `encode_route_id`/`decode_route_id`, the `~`-reservation
    guard in `_validate`, updated `aigateway_only` docstring.
  - `src/url4_cloud/world_config.py` — `_merge()` keyed by encoded id (registry-routable +
    registry-aigateway_only + TOML-declared, all in one namespace); `declared_model_ids()` decodes;
    `_reject_unroutable_default(default_model)` (dropped the now-unused `registry` param, detects a
    literal `:` directly).
  - `src/url4_cloud/runner/connector.py::_chat_completion_loop` — one `real_model_id =
    decode_route_id(spec.id)` local, used for the wire body and `_report_usage`.
  - `src/url4_cloud/catalog/executable.py` — `ExecutableCatalog.fetch` rewrites retained ids via
    `encode_route_id`; `ExecutableModelParameterSource.fetch_model_parameters` decodes the
    caller-supplied `model` before the membership check and the forwarded call.
  - New tests: `test_model_route_encoding.py`, `test_aigateway_connector_route_encoding.py`,
    `test_executable_catalog_route_encoding.py`.
  - Edited tests (pre-approved in the ticket/design, not a new decision):
    `test_world_config_registry_merge.py` (`test_an_aigateway_only_id_never_enters_the_world` →
    renamed/flipped to `test_an_aigateway_only_id_enters_the_world_under_its_encoded_id`; the
    shared `_REGISTRY` fixture's expected id set in
    `test_registry_ids_reach_the_declared_world_without_any_toml_entry` gained the encoded
    huggingface id — a collateral fixture effect, not a targeted rewrite),
    `test_executable_model_routes.py::test_control_plane_and_runner_read_the_same_declared_ids`
    (decode added to one side of the equality), `test_executable_model_catalog.py::
    test_production_builder_wraps_the_gateway_source_with_the_declared_routes` (now expects the
    real `url4.toml`'s aigateway_only seed to be retained under its encoded id — discovered during
    implementation, not anticipated in the original file list, but the exact same category as the
    other two).
  - `test_a_default_route_naming_an_aigateway_only_id_is_refused` needed NO edit — the new
    `_reject_unroutable_default` message still contains "cannot be a route".
- **Commits:** see `git log` on this branch (`Refs: OME-873`).
- **Gates:** `run_gates.py url4-cloud --skip-append-only` — ruff check, ruff format --check,
  pyright, check_layering.py, `pytest --cov=url4_cloud --cov=url4.streaming --cov-fail-under=80`
  all green. Full suite: 1718 passed, 5 skipped (pre-existing skips, unrelated).
- **Deviations:**
  - `--skip-append-only` used, per the owner-approved deviation named in the ticket, for the 3
    pre-existing test edits above (all factually contradicted the new, intended behavior — not
    weakened, just corrected to the new truth).
  - One test edit (`test_executable_model_catalog.py`) was not in the original plan — found only
    once the real `url4.toml` + `BUILTIN_MODEL_WORLD` were exercised end-to-end through
    `build_executable_catalog_service`. Same category and same justification as the two planned
    edits; recorded here for completeness.
  - `connector.py` stayed at 711 lines (over the 450-line guideline) — pre-existing size, and this
    unit's change to it is a 4-line, single-purpose addition; a file-level refactor is out of scope
    for this ticket (no drive-by refactor).
