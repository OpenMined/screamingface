"""
Spend guard — hard USD budget + call limits so a runaway run can't burn
the whole API account balance.

Two enforcement seams cover 100% of paid LLM calls:

  * `BaseProvider.generate` / `generate_multi_turn`
    (benchmarking/arena/providers/base.py) — answer / panel / synth calls.
  * The generate functions in `runners/llm_client.py` — judge + generator
    calls.

Both call `check_spend(model)` BEFORE every attempt (so retry spend counts
against the budget too). `runners.telemetry.record_call` reports every
completed call back via `record_spend()`, which appends to a file-locked
JSONL ledger (`<output_root>/metrics/spend_ledger.jsonl`) so the running
total survives the per-phase subprocess boundary — run_pipeline.py runs
each phase as its own process and stamps one run id into the environment,
and every subprocess seeds its in-memory counter from the ledger lines
carrying that run id. Within one subprocess asyncio is single-threaded,
so the in-memory counter is race-safe; a threading.Lock covers the odd
sync caller running outside the event loop.

Every knob resolves environment variable first, then the global `llm:`
block in config.yaml. The guard is a complete no-op in mock mode
(SCREAMINGFACE_MOCK_LLM / `llm.mock`) — mock calls are free. Real calls with
neither a budget nor a call cap configured refuse to fire
(MissingBudgetError): an uncapped run is the runaway-bill scenario this
module exists to prevent. Spend is recorded to the ledger for every real
call regardless of caps, so a cap added later sees the true total.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Knobs — env var names (underscores: hyphens are invalid in env var names)
# and their config.yaml `llm:` counterparts.
# ---------------------------------------------------------------------------

# Hard USD cap for one run. Config: `llm.budget_usd`.
ENV_BUDGET_USD = "SCREAMINGFACE_BENCHMARKS_USD"
# Max total LLM calls for one run (secondary fuse). Config: `llm.max_calls`.
ENV_MAX_CALLS = "SCREAMINGFACE_BENCHMARKS_MAX_CALLS"
# Per-request timeout in seconds. Config: `llm.request_timeout_s`.
ENV_TIMEOUT_S = "SCREAMINGFACE_BENCHMARKS_TIMEOUT_S"
# "1" → launch even when the pre-flight estimate exceeds the budget.
ENV_CONFIRM = "SCREAMINGFACE_BENCHMARKS_CONFIRM"
# "1" → downgrade the unpriced-model block to a once-per-model warning.
ENV_ALLOW_UNPRICED = "SCREAMINGFACE_BENCHMARKS_ALLOW_UNPRICED"
# Override the ledger file location (default: <output_root>/metrics/…).
ENV_LEDGER = "SCREAMINGFACE_BENCHMARKS_LEDGER"
# One id per pipeline invocation — set by run_pipeline.py so every phase
# subprocess shares a single budget window. Standalone runners fall back
# to SCREAMINGFACE_RUN_ID (the documented resume/pinning var) so a resumed
# run keeps drawing from the same budget window, then to a per-process id.
ENV_RUN_ID = "SCREAMINGFACE_BENCHMARKS_RUN_ID"

SPEND_LEDGER_FILENAME = "spend_ledger.jsonl"
# A hung request otherwise holds one of the (default 10) semaphore slots
# forever. Long DRACO research answers can run several minutes — 10 min
# is generous headroom without letting a stuck call outlive the run.
DEFAULT_REQUEST_TIMEOUT_S = 600.0

_TRUTHY = ("1", "true", "True")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SpendGuardError(RuntimeError):
    """Base for every guard refusal — catch this to abort a run cleanly."""


class BudgetExceededError(SpendGuardError):
    """Cumulative USD spend hit the configured cap."""


class CallLimitExceededError(SpendGuardError):
    """Total LLM call count hit the configured cap."""


class UnpricedModelError(SpendGuardError):
    """A budget is set but the model has no pricing — its spend would
    silently count as $0 against the cap."""


class MissingBudgetError(SpendGuardError):
    """Real (non-mock) calls in CI with no budget configured."""


# ---------------------------------------------------------------------------
# State — seeded once per process from the ledger, then kept in memory.
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()
_LLM_CFG: dict | None = None
_seeded = False
_spent_usd = 0.0
_call_count = 0
_warned_unpriced: set[str] = set()


def reset_for_tests() -> None:
    """Drop cached config + counters so tests get a clean process state."""
    global _LLM_CFG, _seeded, _spent_usd, _call_count
    with _LOCK:
        _LLM_CFG = None
        _seeded = False
        _spent_usd = 0.0
        _call_count = 0
        _warned_unpriced.clear()


# ---------------------------------------------------------------------------
# Knob resolution
# ---------------------------------------------------------------------------


def _llm_cfg() -> dict:
    """Global `llm:` config block, loaded lazily and memoized.

    Falls back to {} if config can't be loaded — the env vars then remain
    the only way to configure the guard.
    """
    global _LLM_CFG
    if _LLM_CFG is None:
        try:
            from config import load_config

            _LLM_CFG = dict(load_config().get("llm") or {})
        except Exception as exc:
            logger.warning("spend_guard: config unavailable (%s)", exc)
            _LLM_CFG = {}
    return _LLM_CFG


def is_mock_mode() -> bool:
    """True when LLM calls are mocked (free). Reads the env var on every
    call — unlike the old import-time freeze in llm_client, a late-set
    SCREAMINGFACE_MOCK_LLM applies immediately."""
    if os.environ.get("SCREAMINGFACE_MOCK_LLM") in _TRUTHY:
        return True
    return bool(_llm_cfg().get("mock", False))


def _env_float(name: str) -> float | None:
    raw = os.environ.get(name)
    if raw in (None, ""):
        return None
    try:
        return float(raw)
    except ValueError:
        # Fail loud: a typo'd cap must not silently mean "no cap".
        raise SpendGuardError(f"invalid {name}={raw!r} — expected a number")


def get_budget_usd(cfg: dict | None = None) -> float | None:
    """Hard USD cap, or None when unconfigured. Env wins over config."""
    env_val = _env_float(ENV_BUDGET_USD)
    if env_val is not None:
        return env_val
    llm = (cfg or {}).get("llm") or _llm_cfg()
    val = llm.get("budget_usd")
    return float(val) if val is not None else None


def get_max_calls() -> int | None:
    """Max total LLM calls per run, or None when unconfigured."""
    env_val = _env_float(ENV_MAX_CALLS)
    if env_val is not None:
        return int(env_val)
    val = _llm_cfg().get("max_calls")
    return int(val) if val is not None else None


def get_request_timeout_s() -> float:
    """Per-request timeout in seconds (never None — see DEFAULT above)."""
    env_val = _env_float(ENV_TIMEOUT_S)
    if env_val is not None:
        return env_val
    val = _llm_cfg().get("request_timeout_s")
    return float(val) if val is not None else DEFAULT_REQUEST_TIMEOUT_S


# ---------------------------------------------------------------------------
# Run id + ledger
# ---------------------------------------------------------------------------


def current_run_id() -> str:
    return (
        os.environ.get(ENV_RUN_ID)
        or os.environ.get("SCREAMINGFACE_RUN_ID")
        or f"local-{os.getpid()}"
    )


def ledger_path() -> Path:
    env = os.environ.get(ENV_LEDGER)
    if env:
        return Path(env)
    root = os.environ.get("SCREAMINGFACE_OUTPUT_ROOT")
    if not root:
        try:
            from config import load_global_config

            root = (load_global_config().get("paths") or {}).get("output_root")
        except Exception:
            root = None
    p = Path(root or "output_artifacts")
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    # Top-level metrics dir (not per-benchmark) — one budget window must
    # span every benchmark in a multi-benchmark pipeline run.
    return p / "metrics" / SPEND_LEDGER_FILENAME


def _ensure_seeded() -> None:
    """Sum this run's ledger lines into the in-memory counters (once)."""
    global _seeded, _spent_usd, _call_count
    if _seeded:
        return
    with _LOCK:
        if _seeded:
            return
        rid = current_run_id()
        spent, calls = 0.0, 0
        path = ledger_path()
        if path.exists():
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if d.get("run_id") != rid:
                            continue
                        spent += float(d.get("cost_usd", 0.0) or 0.0)
                        calls += 1
            except OSError as exc:
                logger.warning("spend_guard: could not read ledger %s (%s)", path, exc)
        _spent_usd, _call_count = spent, calls
        _seeded = True


def _append_ledger(entry: dict) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry) + "\n"
    with open(path, "a") as f:
        try:
            import fcntl

            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        except ImportError:  # non-POSIX — append without a lock
            f.write(line)


def spent_usd() -> float:
    _ensure_seeded()
    return _spent_usd


def call_count() -> int:
    _ensure_seeded()
    return _call_count


# ---------------------------------------------------------------------------
# Recording — called by telemetry.record_call after every LLM call
# ---------------------------------------------------------------------------


def record_spend(
    model: str,
    stage: str,
    cost_usd: float,
    tokens_in: int = 0,
    tokens_out: int = 0,
    ok: bool = True,
) -> None:
    """Bump the in-memory counters and append one ledger line.

    Never raises — a broken ledger must not kill a run mid-flight. The
    in-memory counter is bumped before the file write, so in-process
    enforcement keeps working even if the append fails (with a warning).
    No-op in mock mode only (mock calls are free). Real spend is recorded
    even when no cap is configured — recording and enforcement are
    separate concerns, so a cap added mid-run or on resume seeds the true
    cumulative spend instead of $0.
    """
    try:
        if is_mock_mode():
            return
        _ensure_seeded()
        global _spent_usd, _call_count
        entry = {
            "run_id": current_run_id(),
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": model,
            "stage": stage,
            "cost_usd": round(float(cost_usd or 0.0), 6),
            "tokens_in": int(tokens_in or 0),
            "tokens_out": int(tokens_out or 0),
            "ok": bool(ok),
        }
        with _LOCK:
            _spent_usd += float(cost_usd or 0.0)
            _call_count += 1
            _append_ledger(entry)
    except Exception as exc:
        logger.warning("spend_guard.record_spend failed: %s", exc)


# ---------------------------------------------------------------------------
# Enforcement — called BEFORE every paid call attempt
# ---------------------------------------------------------------------------


def _model_has_pricing(model: str) -> bool:
    # Lazy import: telemetry imports this module at its top level, so the
    # reverse import must stay deferred to call time.
    from runners.telemetry import _load_pricing

    return model in _load_pricing()


def lineup_models(cfg: dict) -> list[str]:
    """Every model slug the configured run can fire a paid eval call at:
    solo models (legacy `models:` + the transport-split `openrouter_models:`
    / `huggingface_models:` lists), fusion panel members + synthesizers,
    and judges. Deduplicated, config order preserved.

    The two-list transport split (`openrouter_models` / `huggingface_models`)
    MUST be included, or the pre-flight unpriced-model gate can't see an
    HF-routed model and a run could launch with it silently unpriced —
    exactly the fail-closed hole this guard exists to close."""
    e = (cfg or {}).get("eval") or {}
    out: list[str] = [
        m
        for key in ("models", "openrouter_models", "huggingface_models")
        for m in (e.get(key) or [])
        if m
    ]
    for f in e.get("fusions") or []:
        out += [m for m in (f.get("panel") or []) if m]
        if f.get("synthesizer"):
            out.append(f["synthesizer"])
    out += [m for m in (e.get("judge_models") or []) if m]
    seen: set[str] = set()
    return [m for m in out if not (m in seen or seen.add(m))]


def _fail_no_budget() -> None:
    raise MissingBudgetError(
        "real (non-mock) LLM calls require a spend cap — set "
        f"{ENV_BUDGET_USD} / llm.budget_usd (or {ENV_MAX_CALLS} / "
        "llm.max_calls). An uncapped run can spend the whole API account "
        "balance. Mock runs (SCREAMINGFACE_MOCK_LLM=1) are exempt."
    )


def check_spend(model: str) -> None:
    """Pre-call gate. Raises a SpendGuardError subclass when the next call
    must not fire:

      BudgetExceededError    — cumulative spend ≥ budget
      CallLimitExceededError — cumulative call count ≥ max_calls
      UnpricedModelError     — budget set but `model` has no pricing
      MissingBudgetError     — no cap configured at all

    No-op in mock mode (mock calls are free). Real calls with neither a
    budget nor a call cap always refuse — an uncapped run is exactly the
    runaway-bill scenario this module exists to prevent.
    """
    if is_mock_mode():
        return
    budget = get_budget_usd()
    max_calls = get_max_calls()
    if budget is None and max_calls is None:
        _fail_no_budget()
    _ensure_seeded()
    if max_calls is not None and _call_count >= max_calls:
        raise CallLimitExceededError(
            f"call limit reached: {_call_count} calls ≥ max {max_calls}. "
            f"Raise {ENV_MAX_CALLS} / llm.max_calls, then relaunch with "
            f"SCREAMINGFACE_RUN_ID={current_run_id()} exported to resume — a "
            "plain re-run mints a NEW run id and re-pays every completed "
            "row."
        )
    if budget is not None:
        if _spent_usd >= budget:
            raise BudgetExceededError(
                f"budget exceeded: ${_spent_usd:.2f} spent of ${budget:.2f} "
                f"cap after {_call_count} calls (run {current_run_id()}). "
                f"To resume THIS run (completed rows cached): raise "
                f"{ENV_BUDGET_USD} / llm.budget_usd, then relaunch with "
                f"SCREAMINGFACE_RUN_ID={current_run_id()} exported — a plain "
                "re-run mints a NEW run id and re-pays every completed "
                "row. The relaunch pre-flight estimates the FULL run on "
                f"top of the spend so far — pass --confirm-spend "
                f"({ENV_CONFIRM}=1) if it refuses a legitimate resume."
            )
        if not _model_has_pricing(model):
            if os.environ.get(ENV_ALLOW_UNPRICED) in _TRUTHY:
                if model not in _warned_unpriced:
                    logger.warning(
                        "spend_guard: model %r has no pricing — its spend "
                        "counts as $0 against the budget.",
                        model,
                    )
                    _warned_unpriced.add(model)
            else:
                raise UnpricedModelError(
                    f"model {model!r} has no entry in the pricing table — "
                    "its spend would count as $0 against the budget. Add a "
                    "`pricing:` entry in config.yaml, or set "
                    f"{ENV_ALLOW_UNPRICED}=1 to proceed at your own risk."
                )


# ---------------------------------------------------------------------------
# Pre-flight — estimate the run before ANY paid call fires
# ---------------------------------------------------------------------------


def preflight_check(cfg: dict, confirmed: bool = False) -> None:
    """Print a cost estimate for the configured run and refuse to launch
    when (already-spent + estimate) exceeds the budget, unless explicitly
    confirmed via `confirmed=True` (--confirm-spend) or the confirm env.

    This is the primary "don't wake up to a bill" defense; the per-call
    ledger check remains the mid-flight backstop. If the estimator itself
    fails we warn and continue — runtime enforcement still applies.
    """
    if is_mock_mode():
        return
    confirmed = confirmed or os.environ.get(ENV_CONFIRM) in _TRUTHY
    budget = get_budget_usd(cfg)

    # Every lineup slug must be priced BEFORE any phase spends. Without
    # this gate, a failed OR /models fetch (DEFAULT_PRICING fallback)
    # still launches: the priced models burn real money first, then the
    # first call to a missing-slug model aborts the run mid-flight via
    # check_spend's UnpricedModelError — money spent on a run that dies.
    missing = [m for m in lineup_models(cfg) if not _model_has_pricing(m)]
    if missing:
        if os.environ.get(ENV_ALLOW_UNPRICED) in _TRUTHY:
            logger.warning(
                "spend_guard: unpriced lineup models %s — their spend "
                "counts as $0 against the budget.",
                missing,
            )
        elif budget is not None:
            raise UnpricedModelError(
                f"lineup models with no pricing entry: {missing}. Their "
                "spend would count as $0 against the budget, and the run "
                "would abort mid-flight on the first call to them — after "
                "the priced models already spent real money. Add "
                "`pricing:` entries in config.yaml, or set "
                f"{ENV_ALLOW_UNPRICED}=1 to proceed at your own risk."
            )

    estimate = None
    total_calls = None
    try:
        from runners.phases.run_costs import estimate_run_cost

        sim = estimate_run_cost(cfg)
        estimate = float(sim.get("total_cost_usd", 0.0))
        total_calls = (sim.get("calls") or {}).get("total")
    except Exception as exc:
        logger.warning(
            "spend_guard: pre-flight estimate failed (%s) — runtime ledger "
            "enforcement still active.",
            exc,
        )

    _ensure_seeded()
    print(f"\n{'─' * 60}")
    print("[spend-guard] pre-flight")
    if estimate is not None:
        calls_str = f"  ({total_calls} calls)" if total_calls is not None else ""
        print(f"  estimated cost : ${estimate:,.2f}{calls_str}")
    else:
        print("  estimated cost : unavailable (estimator failed — see log)")
    print(f"  already spent  : ${_spent_usd:,.2f}  (run {current_run_id()})")
    print(
        f"  budget         : {'$' + format(budget, ',.2f') if budget is not None else '(none)'}"
    )
    print(f"{'─' * 60}\n")

    if budget is None:
        # Same rule as check_spend: a call cap alone is an active guard.
        if get_max_calls() is None:
            _fail_no_budget()
        return
    if estimate is not None and _spent_usd + estimate > budget and not confirmed:
        raise BudgetExceededError(
            f"estimated cost ${estimate:,.2f} + already-spent "
            f"${_spent_usd:,.2f} exceeds the ${budget:,.2f} budget. Raise "
            f"{ENV_BUDGET_USD} / llm.budget_usd, shrink the run (rows / "
            "models / judges), or pass --confirm-spend "
            f"({ENV_CONFIRM}=1) to launch anyway. NOTE: the estimate is "
            "for the FULL run — when resuming a partially completed run "
            "(cached rows are skipped, so the real remaining cost is "
            "lower), --confirm-spend is the intended path."
        )
