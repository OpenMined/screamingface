---
title: Attribute and remove websocket_disconnected drops
ticket: none filed — investigation of OME-806
status: approved
date: 2026-08-13
---

# Attribute and remove `websocket_disconnected` drops

## Problem

`ExecutionError: SF Engine WebSocket disconnected before the Run completed` (code
`websocket_disconnected`) is raised from exactly one place, and every way a Run stream can be
lost arrives there as the same sentence. An oversized result frame, a proxy draining a
listener, a rolled Pod and a refused capability are indistinguishable to the researcher who
hits one and to the engineer who reads the report afterwards.

Two of those causes turned out to be defects the Client creates itself. Both were reproduced
before anything was changed.

### A — a capped Report can never be delivered

`Url4Executor.result_cap` is `1_048_576`. The `websockets` client's `max_size` default is
`2**20` — the same number — and the Client never overrode it. The Engine truncates a body to
the cap and then wraps it in a CloudEvent whose `data.body` is a JSON string, so the frame
always exceeds the body it carries. Measured against a real socket: a body at the cap
produces a **1,048,884 byte frame**, 308 bytes over the limit before a single character of
JSON escaping (escaping adds ~7% on a real Report, and can double it in the worst case).

The truncation guard therefore never produced a deliverable frame. Any Evaluation whose
Report approached 1 MiB — roughly 125 Cases on a rubric-heavy Benchmark — failed, every time,
with close 1009.

### E — the Access retry outlives the capability it retries with

On a Cloudflare Access challenge, `run()` calls `reauthenticate()` — an interactive browser
login with a **300 second** timeout — and then retries the handshake with the capability it
already held. That capability's `iat_window_s` is **60 seconds**, in the default and in the
shipped chart values. Any login slower than a minute presents an expired ticket, the Engine
refuses the handshake with 1008, and the Run dies. Because `_MAX_CANDIDATES_IN_FLIGHT`
capabilities are minted together, one slow login fails the whole Evaluation.

### T — the two halves of the transport trust different roots

Found by deploying the observability below and asking the reporting user to try again. The
Client reaches one Engine two ways, and they disagreed about certificate authorities.
`httpx` resolves `SSL_CERT_FILE`, then `SSL_CERT_DIR`, and otherwise falls back to the
`certifi` bundle shipped with this package. `websockets`, given no context, trusts OpenSSL's
own CA paths. They agree while those variables are set and **diverge in the default case**,
which is the common one — a python.org macOS build whose `Install Certificates.command` was
never run has nothing in OpenSSL's paths at all.

The Client therefore minted its capability over HTTPS successfully and then failed to open a
WebSocket to the same host, 0.0 seconds in, with `SSLCertVerificationError`. The engine-side
log confirms the asymmetry exactly: `POST /token 200 OK`, the catalog and benchmark reads all
`200`, and no `ws attach` or `ws rejected` line at all — the socket never arrived.

This is also the real explanation for the "local runs are unaffected" observation that framed
OME-806 from the start. A local Engine is reached over plain `ws://`, which never negotiates
TLS, so the split could only ever appear against a hosted Engine — and read as a property of
being remote rather than a property of the trust store.

### The reason neither was visible

The Client discards the WebSocket close code into a generic message, and the App cannot log
below WARNING at all: `cli.py` calls `uvicorn.run()` with no `log_config`, uvicorn configures
only the `uvicorn*` loggers, and the root logger is left without a handler — so every
`url4_cloud` record falls through to `logging.lastResort`. Production log exports show
`uvicorn.access` health checks and nothing else, which reads as an idle service rather than a
muted one. This has been true of every deployment.

## Outcome

A dropped Run stream names its own cause, from either end, and the two causes above stop
happening.

- The Client's frame limit is above the Engine's result cap plus envelope and escaping, so a
  capped Report is delivered rather than refused.
- An Access challenge is retried with a capability minted after the login, not before it.
- The WebSocket verifies against exactly what the HTTP half verifies against, so a host the
  Client just reached over HTTPS cannot be unreachable over WSS.
- The Client's error carries the close code and the elapsed Run time.
- The App records the close code, duration, and whether the connection was carrying work or
  idling — and its records actually reach a handler.

## Interfaces and seams

**Client (`packages/screamingface`).** `Url4CloudTransport` and its asynchronous twin gain an
explicit `max_size`, track the capabilities they mint as a list rather than one value, and
report the close code. No public API changes; `_RunOutcome`, the event stream and the Report
are untouched.

**Engine (`apps/url4-cloud`).** A new `url4_cloud.logs` module owns log configuration for both
modes of the image, wired from `cli.main` before dispatch. The WS bridge records the shape of
each connection. Stdlib only, so the layering rule keeps the run mode's import graph disjoint
from the serving mode's.

## Behavioral invariants

- A result body at exactly `result_cap` reaches the researcher.
- The retry after an Access challenge presents a capability that did not exist when the
  challenge was issued.
- Every cause of a lost stream is distinguishable from the Client's error text alone.
- The App's INFO records survive the process that hosts them, and configuring twice neither
  stacks handlers nor suppresses one another component already installed.
- Counters describe frames that actually left the socket, so `frames` and `heartbeats` are
  disjoint and neither counts a frame that was queued but never sent.
- No payload is logged. The url4 expression is recorded by length only — it carries prompts.

## Explicitly out of scope

The observability lands so these can be settled with evidence rather than argument:

- **Envoy Gateway listener drain.** The dev cluster's control plane pushes new xDS roughly
  once a minute while idle; whether that drains in-flight WebSockets is unverified.
- **Cloudflare edge idle or duration cuts.** Not reproducible without the real edge.
- **Pod rollout.** `replicaCount` must stay 1 while the 428 subscriber gate is in-process, so
  every rollout drops in-flight Runs by construction.

Also deliberately left alone, each its own unit:

- **Reconnect after a drop.** Still impossible: a 60 second capability cannot outlive the Run
  it authorizes, so resuming from `from_sequence` needs a token-lifetime decision first.
- **The stop fallback on long Runs.** `cancel_active()` presents the original capability, which
  a Run older than 60 seconds has already outlived; 401 is not treated as already-stopped, and
  the synchronous fan-out cannot cancel running threads, so interrupting a long Evaluation
  still leaves paid work running.
- **Advisory frames dropped under backpressure.** `Bridge._offer` discards on a full queue,
  including the `stream_failed` nack that drives recovery — the control signal shares the
  bounded queue it exists to repair.

## Compatibility

Both changes are behaviour-preserving for every Run that already succeeded. The Client's frame
limit only admits frames it previously refused; the capability re-mint only occurs on a path
that previously failed. No wire contract, schema or public signature changes, so no Benchmark
revision moves.
