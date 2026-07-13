---
ticket: none (Linear filing explicitly waived by owner this session — "skip the linear task step")
stack: pkg/url4 (not yet registered in .claude/sdlc.local.md — card gap; gates run manually)
status: in_progress
started: 2026-07-13
finished:
---

# url4 SDK facades — renderer, builders, client, node

## Intent

Close the four product-surface gaps identified in the URL4 spec (Parts A+B) digest so the
`packages/url4` engine becomes usable as an SDK, matching the approved UX direction
(client-side `query/broadcast/iterate/reduce` helpers; node-side decorator-registered
endpoints + holdings with in-process/ASGI serving):

- **G1 renderer** — `render(node) -> str`, the missing inverse of `build()`/`parse()`;
  prerequisite for every builder.
- **G2 builders** — Python constructors (`expr`, `src`, `text`, `ref`, `self_`, `identity`,
  `iterate`, `broadcast`, `reduce`, `expand`) that lower to the existing frozen AST with
  grammar-faithful normalization.
- **G3 client** — `Client` + `Url4Result` envelope over `url4.run()`, local + remote
  (RemoteExpr wrapping), owned HttpIOLayer lifecycle.
- **G4 node SDK** — `Url4Node`: endpoint/holdings/identity registries implementing the
  IOLayer + SupportsHoldings ports (a node IS an io layer), `evaluate()`, framework-free
  ASGI shim (GET-only per url4-engine doctrine N1), lazy-uvicorn `serve()`.

## Planned changes

- `packages/url4/src/url4/render.py` (new) + `errors.py` (add `RenderError`) +
  `grammar.py` (public `parse_value()`)
- `packages/url4/src/url4/builders.py` (new)
- `packages/url4/src/url4/client.py` (new)
- `packages/url4/src/url4/node.py` (new; ASGI inline, uvicorn lazy)
- `packages/url4/src/url4/__init__.py` (exports; file already carries uncommitted v0.2 WIP)
- `packages/url4/tests/test_render.py`, `test_builders.py`, `test_client.py`,
  `test_node.py` (new)
- `docs/spec/2026-07-13-url4-sdk-facades.md`, `docs/plan/2026-07-13-url4-sdk-facades.md`

## Test plan

- **G1**: per-node render cases; round-trip property `build(render(x)) == x` over the
  full corpus of expression texts harvested from existing tests + seeded random AST
  generator; unrepresentable-value errors (unbalanced-paren URLs, negative weights,
  dual-key boundary misclassification) raise `RenderError` naming the leaf.
- **G2**: builder → render golden strings; coercions (str/dict/Node); two-axis kwargs;
  validation errors (required+optional, reserved names, bad weight).
- **G3**: Client over StaticIOLayer — query/broadcast/iterate/reduce results, remote
  target via fetch_map/routes, Url4Result.text/.data/.elements, aclose lifecycle.
- **G4**: Url4Node — endpoint dispatch (decorator), holdings/identity resolution incl.
  error codes (unknown_identity, identity_access_denied), evaluate() in-process, ASGI
  GET via httpx.ASGITransport (200 body, 400 parse error, 404 unknown path, 405 non-GET).

## Acceptance

- All four modules land with tests; prior 385 tests stay green and unmodified.
- Gates green: `uv run ruff check` · `uv run ruff format --check` · `uv run pyright` ·
  `uv run pytest -q` (in `packages/url4`).
- Round-trip property holds for every existing-corpus expression.
- Design-reviewer pass with the plan as rubric; STRUCTURAL findings resolved.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:**
- **Commits:**
- **Gates:**
- **Deviations:** Linear ticket + docs/tasks mirror waived by owner; url4 stack missing
  from sdlc card (gates run manually); working tree carried pre-existing uncommitted
  v0.2 WIP — only files this unit touches are committed.
