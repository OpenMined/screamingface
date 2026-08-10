# Enforce Evaluation budgets in the Engine before spend

Public execution remains the single `sf.evaluate()` interface. Once the Engine exposes versioned
pricing and atomic budget enforcement, `max_cost_usd` applies to the complete Evaluation and the
preflight UI shows its conservative Cost Estimate automatically. If that estimate exceeds the
budget, or any required call is unpriced, the Client raises a concise `PlanningError` before spend.
The Engine still enforces the cap before every model dispatch. An unbudgeted Unpriced Evaluation may
run and records unavailable USD cost without a separate warning system. The Client does not add
`sf.plan()`, `sf.estimate()`, `dry_run`, or `max_cost_usd` before the Engine contract can uphold these
semantics.
