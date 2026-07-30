# OME-620 — Local catalogue discovery plan

1. Add failing Client tests for typed synchronous, asynchronous, and lazy-default catalogue
   listing, malformed payloads, and Engine failures.
2. Add frozen discovery values and narrow catalogue adapters behind `Client.models` and
   `Client.benchmarks`.
3. Export module-level `sf.models.list()` and `sf.benchmarks.list()` through the lazy Client.
4. Permit anonymous model discovery only in the isolated loopback Engine demo by using the
   Engine process's configured AI Gateway credential.
5. Align discovery fixtures and the generated demo notebook on the canonical unversioned
   `draco-lite` identifier.
6. Validate Client tests, Ruff, Pyright, notebook structure, and a no-spend live catalogue call.
