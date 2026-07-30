# OME-620 — Local catalogue discovery vertical slice

## Scope

The isolated DRACO-Lite demo exposes the intended Client discovery interface against the real
OME-587 local Engine:

```python
sf.models.list()
sf.benchmarks.list()

client.models.list()
client.benchmarks.list()
```

`AsyncClient` exposes the same names as awaitable operations. Module-level operations delegate to
the existing lazy default Client.

## Contract used by this demo

- `GET /v1/models` returns the Engine-proxied OpenAI-style model catalogue.
- `GET /v1/benchmarks` returns immutable Benchmark summaries.
- Model rows decode to frozen `sf.ModelInfo(id, provider)` values.
- Benchmark rows decode to frozen `sf.BenchmarkInfo` values.
- The public DRACO-Lite identifier is `draco-lite`; manifests remain reproducibly pinned by their
  digest rather than by exposing an `@1` suffix in the user-facing name.
- The Client calls only the configured SF Engine.
- Trusted loopback local mode may use its configured AI Gateway credential when the caller sends
  none. Hosted mode continues to require and forward caller authentication.
- Invalid payloads and transport failures raise typed ScreamingFace errors; raw dictionaries are
  never part of the public interface.

This is conformance evidence for the proposed catalogue interface, not a claim that the production
catalogue schemas or hosted authentication contract have been finalized.
