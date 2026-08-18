"""The local admission ceiling as a CONTRACT with the Client, not as runner behaviour.

`test_inprocess_runner.py` pins how the adapter refuses once it is full. This module pins the
separate question of where "full" is set, because that number is only correct in relation to a
constant living in another distribution.
"""

from screamingface_engine.adapters.inprocess import DEFAULT_MAX_CONCURRENT_RUNS
from screamingface_engine.config import Settings

# INVARIANT: the local admission ceiling stays STRICTLY ABOVE the Client's per-Evaluation
# fan-out. The Client schedules one run per Candidate and keeps up to `_MAX_CANDIDATES_IN_FLIGHT`
# of them in flight at once — 8, at `packages/screamingface/src/screamingface/_evaluation/
# runner.py`. Equal values leave ZERO headroom: one full Evaluation saturates the runner exactly,
# so a second notebook cell, a second Client, or a single abandoned run turns the next schedule
# into `503 the runner is at capacity`. Abandoned runs make that sticky rather than momentary — a
# WebSocket disconnect does NOT stop a run (only a `StopEvent` or `DELETE /?topic=` does), so an
# orphan holds its slot until `job_deadline_s`, which is 16 hours.
#
# WHY a floor rather than a comparison against the real constant:
# `apps/screamingface-engine` does not depend on `packages/screamingface` — the package
# is absent from this app's `pyproject.toml` and imported nowhere under `src/` or
# `tests/`. Reading it here would either invert the layering (a
# server app reaching into the published Client SDK) or force the shared bound up into
# `packages/url4`, which both sides already depend on. That hoist is the correct end state and is
# tracked separately; until it lands, this floor is what stops the collision returning silently.
#
# AIDEV-NOTE: if the Client's fan-out ever rises above 8, raise this number with it. The two are a
# contract that no import currently enforces, so nothing else will fail to warn you.
_CLIENT_CANDIDATE_FAN_OUT = 8


def test_the_local_ceiling_leaves_headroom_above_the_client_fan_out() -> None:
    assert DEFAULT_MAX_CONCURRENT_RUNS > _CLIENT_CANDIDATE_FAN_OUT
    assert Settings().local_max_concurrent_runs > _CLIENT_CANDIDATE_FAN_OUT


def test_the_adapter_default_and_the_setting_agree() -> None:
    # WHY: `local.py` builds the runner from the setting, while any caller that omits the keyword
    # gets the adapter default. If the two drift, local capacity depends on which path built the
    # runner — a split that surfaces only as an unreproducible 503.
    assert Settings().local_max_concurrent_runs == DEFAULT_MAX_CONCURRENT_RUNS
