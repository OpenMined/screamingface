---
title: Deepen the ScreamingFace SDK modules
ticket: OME-605
status: approved
date: 2026-08-01
approved: 2026-08-01
---

# Deepen the ScreamingFace SDK modules

## Outcome

Restructure `packages/screamingface` without changing its public behavior. The package keeps its
small public interface while concentrating Engine integration, Evaluation orchestration, and
notebook presentation behind three cohesive internal modules.

## Required seams

- `Client` and `AsyncClient` remain the Evaluation and lifetime interface.
- Engine I/O depends on core-owned ports; concrete HTTP, WebSocket, and Cloudflare adapters are
  selected only by the registry/composition root.
- Evaluation owns validation, compilation, Candidate scheduling, and Report decoding behind sync
  and async entry points.
- `ConnectionPanel` remains the public notebook interface while controller state is independent of
  static HTML and ipywidgets rendering adapters.
- Engine wire decoding has one strict, fail-closed implementation shared by catalogues, manifests,
  connections, and results.

## Constraints

- No authoring, Engine-contract, deployment, or release feature work.
- No breaking public-interface changes. Optional constructor injection may expose the existing
  HTTP and Run transport seams for composition and behavioral tests.
- Sync and async code share pure logic but are not unified through metaprogramming.
- Tests observe behavior through Client, ConnectionPanel, and transport interfaces; direct private
  mutation is removed where a real seam exists.
- User notebook working files are preserved.

## Acceptance

- Core modules do not import concrete adapters.
- `client.py` owns Client lifetime and delegates the Evaluation workflow.
- Panel control and rendering can change independently.
- Repeated wire-decoding primitives are removed.
- Ruff, format, Pyright, coverage, deterministic distribution, and relevant end-to-end suites pass.
