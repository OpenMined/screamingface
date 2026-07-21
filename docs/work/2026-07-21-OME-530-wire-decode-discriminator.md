---
ticket: OME-530
stack: url4
status: done
started: 2026-07-21
finished: 2026-07-21
---

# OME-530 — dual-convention wire decode mis-parses fully-encoded non-group heads and raw iteration payloads

## Intent

Spec §3.4 obliges a node to accept BOTH wire conventions — url4's raw convention
(structural chars raw, content wire-escaped) and standard full percent-encoding
(curl `--data-urlencode`, browsers, httpx). The decode layer's convention
discriminator only recognizes a `%28` head, and the raw-branch reassembly in
`decode_expression_http` assumes the `(context)!intent` envelope shape. Three
grammar-legal payload shapes therefore mis-parse silently (verified by
execution): fully-encoded non-`(` heads (`%2F…`, `url4%3A…`) → `()!<text>`;
raw paren-collection iterations `(a,b)*(body)!'i'` → tail dropped → `(a,b)`;
raw non-`(` heads → `()!<text>`. Same failure family as OME-501. This makes
`url4 serve` reject over HTTP what the same node accepts in-process.

## Planned changes

- `packages/url4/src/url4/core/subrequest.py` — replace the `_fully_encoded`
  head-sniff with the paren discriminator (raw `(` present → raw convention;
  else `%` present → fully-encoded; else inert), shared by
  `decode_subrequest_http` and `decode_expression_http`; give
  `decode_expression_http` a raw branch that keeps envelope part-unquoting ONLY
  for the exact `(context)[!intent]` shape and whole-text `unquote` otherwise.
  `decode_subrequest` itself untouched.
- `packages/url4/tests/spec/test_wire_spec.py` — append decoder-level RED tests.
- `packages/url4/tests/unit/test_server.py` — append eval-surface HTTP tests
  (fully-encoded call expression end-to-end).

## Test plan

- fully-encoded relative-call sugar (`%2F` head) round-trips through
  `decode_expression_http` verbatim (happy).
- fully-encoded canonical `/path?q=(…)!'…'` and remote `url4://…` heads
  round-trip (boundaries).
- raw iteration with paren-collection head keeps its `*(body)!'intent'` tail.
- raw `(a%26b)!go` envelope still part-unquotes to context `a&b`
  (INVARIANT guard: raw-convention envelope behavior unchanged).
- fully-encoded bare intent with `+`-encoded space decodes the space
  (`decode_subrequest_http`).
- server: `GET /v1?q=<fully-encoded legal call>` evaluates instead of
  `endpoint_not_found` (error path fixed end-to-end).
- INVARIANT protected: a node accepts over HTTP exactly the expression set it
  accepts in-process; no silent truncation of grammar-legal payloads.

## Acceptance

- All new tests green; all 908+ prior tests green and unmodified.
- `run_gates.py url4` fully green (ruff, format, pyright, pytest cov ≥95%).
- OME-530 closed with commit sha; OME-500 informed of the non-defect findings.

## Outcome (fill at the end — required before COMMIT)

- **Actual files:** as planned — `src/url4/core/subrequest.py` (new paren
  discriminator + `_decode_raw_expression`), `tests/spec/test_wire_spec.py`
  (+8 tests), `tests/unit/test_server.py` (+2 tests). Also lint-cleaned
  `demo/backends/mock.py` (complexity/dispatch refactor) so the stack's ruff
  gate is green — committed separately as demo work, not part of this unit.
- **Commits:** (sha recorded post-commit) `fix(url4): classify every wire
  head in the dual-convention decode + stop truncating raw non-envelope
  payloads` — Refs: OME-530.
- **Gates:** ALL GREEN — ruff check, ruff format --check, pyright,
  pytest --cov=url4 --cov-fail-under=95 (1056 passed). Append-only check run
  with `--skip-append-only` after verifying by `git diff HEAD -- tests/`:
  98 insertions, 0 deletions — no prior test modified (the gate's
  name-status heuristic cannot distinguish appends; rule 5 satisfied).
- **Deviations:** e2e verification exposed a SEPARATE pre-existing engine
  defect (canonical `/p?q=(x)!'go'` rejected at fragment root while sugar
  parses) — filed as OME-533 under OME-500 rather than widening this unit.
  Non-defect findings (opaque endpoint context §13.4; Binding exclusion
  §4.3; iteration illegal bare in `?q=`) recorded on the tickets, engine
  conforms to the repo spec on all three.
