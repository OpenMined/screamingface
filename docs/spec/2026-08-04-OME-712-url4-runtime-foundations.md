---
title: OME-712 — URL4 runtime foundations for Engine-owned benchmarks
status: accepted
created: 2026-08-04
ticket: OME-712
related:
  - https://linear.app/openmined/issue/OME-712/run-draco-end-to-end-as-a-url4-expression-on-the-runner-path
  - docs/plan/2026-08-04-OME-712-url4-runtime-foundations.md
  - docs/spec/2026-07-11-url4-package-v1-spec.md
---

# URL4 runtime foundations for Engine-owned benchmarks

## Purpose

Engine-owned benchmark URL4 must be able to carry outer protocol bindings into a collection
iteration, move a large reducer payload without the operating system's per-argument limit,
and report which model actually served a request. These are general URL4 runtime contracts;
DRACO is their first consumer, but no benchmark-specific behavior belongs in `packages/url4`.

## Scope

### Iteration scope parity

An iteration body and its per-row intent may reference names bound by the enclosing expression.
The compiler must create dependency edges for those free references before each row executes.
The row-owned `$item` and `$current` names continue to shadow outer names.

The two supported compilation interfaces are semantically equivalent:

```python
resolve(text) == resolve(build(text))
```

That equivalence covers references appearing in an iteration body or per-row intent, including
nested iteration bodies. An unresolved legal outer binding must not silently reach a route as
the literal characters `$name`.

### Command stdin selection

`make_command_handler` accepts a keyword-only `stdin` selector:

- `"context"` is the compatibility-preserving default.
- `"intent"` pipes the resolved intent to the child process.
- any other value fails when the handler is constructed.

The selector changes only the bytes written to stdin. Existing single-pass `{context}` and
`{intent}` argv substitution remains unchanged. `stdin="intent"` is the supported path for
cross-row reducer payloads that can exceed the kernel's single-argument limit.

### Served-model attribution

Usage and span observations carry an optional `response_model`. When a provider reports the
model that served the call, URL4 preserves it. When the provider omits it, URL4 preserves that
absence rather than fabricating the requested model as a response fact.

## Interfaces and ownership

- `url4.dag.compiler` owns reference-edge discovery and text/AST lowering parity.
- URL4 iteration nodes receive already-wired outer bindings and own row-local shadowing.
- `url4.cli._serve.make_command_handler` owns subprocess stdin selection.
- `url4.observe.Usage` and the execution context own provider-reported served-model
  attribution.
- Benchmark definitions, provider adapters, routing policy, and scoring remain outside this
  package.

## Failure behavior

- Unknown command stdin selectors fail loudly before a command runs.
- Oversized argv remains an operating-system error; callers avoid it by selecting intent stdin.
- Unknown URL4 references retain the language's existing behavior. This change only ensures
  legal enclosing references are actually wired.
- Missing provider response-model metadata remains `None`; it is not guessed.

## Non-goals

- DRACO or IFEval routes, manifests, validation, grading, or aggregation.
- AI Gateway provider request/response normalization.
- URL4 Cloud process configuration.
- A new public URL4 grammar form.

## Acceptance

- Text and AST compilation produce the same observable iteration results.
- Outer bindings reach body and per-row intent while `$item` and `$current` remain row-local.
- A payload larger than 128 KiB can reach a command through `stdin="intent"`.
- The default command behavior stays context-on-stdin.
- Observations distinguish requested model from provider-reported response model.
- The complete deployment-target Linux `url4` gate lane passes without modifying or weakening
  inherited tests. On a host whose argv limit is larger than Linux's `MAX_ARG_STRLEN`, the
  platform-specific ceiling assertion is recorded separately; the stdin behavior tests must
  still pass.
