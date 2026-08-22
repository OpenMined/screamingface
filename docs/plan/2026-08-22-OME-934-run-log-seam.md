# OME-934 — Implementation plan

Spec: `docs/spec/2026-08-22-OME-934-run-log-seam.md`
Stack: `screamingface-engine`
Ledger: `docs/work/2026-08-22-OME-934-run-log-seam.md`

Production code starts only after explicit owner approval.

## Iteration 1 — port and isolation

### RED

- Optional factory sees the exact rendered URL4 once.
- Its context surrounds exactly one run.
- Concurrent runs receive distinct emitters and state.
- No factory preserves byte-identical result and errors.

### GREEN

- Define the smallest generic run-scope and scalar structured-Log port.
- Add optional injection to the Runner adapter and composition root.
- Keep generic modules free of Benchmark imports.

## Iteration 2 — bridge delivery and failure containment

### RED

- Emitted Logs use existing bridge ordering and protocol mapping.
- Setup, emission, and teardown failures cannot replace the URL4 result or exception.
- Existing bridge pressure policy remains unchanged.

### GREEN

- Adapt the emitter to the existing Log observation/bridge path.
- Contain only observational failures and retain diagnostics without recursive publication.

## Verification

```text
uv run .claude/scripts/run_gates.py screamingface-engine
```

Before PR, compare exact results/errors and inspect the diff to confirm no `benchmarks` consumer,
generated URL4, or `packages/url4` change.
