"""``InProcessJobRunner`` — the ``JobRunner`` over an in-process ``asyncio.Task`` (local mode,
docs/plans/url4-cloud-integration/prd/local-mode.md §7 tests 2-3).

Engine-independent: the Runner's own :func:`~url4_cloud_runner.publish.run` coroutine is spawned
as a task per topic, keyed by the same deterministic :func:`~url4_cloud.jobs.port.job_name` the k8s
adapter uses — so the stateless single-use guard (spec §5) behaves identically across both
``JobRunner`` adapters. The bus and the per-run ``Executor`` are both injected
(``executor_factory`` builds a fresh one per run) so this module never imports ``url4``.
"""

import asyncio
from collections.abc import Callable

from url4_cloud.jobs.port import JobAlreadyExists, JobStatus, job_name
from url4_cloud_nats import Bus
from url4_cloud_runner import publish
from url4_cloud_runner.executor import Executor


def _terminal_status(task: asyncio.Task[None]) -> JobStatus:
    if task.cancelled():
        return "stopped"
    return "failed" if task.exception() is not None else "succeeded"


def _map_status(task: asyncio.Task[None] | None) -> JobStatus:
    if task is None:
        return "not_found"
    if not task.done():
        return "running"
    return _terminal_status(task)


class InProcessJobRunner:
    """``JobRunner`` backed by a ``dict[str, asyncio.Task]`` registry, one task per run.

    Unlike ``K8sJobRunner`` — whose backing resource (Job) persists until an explicit
    ``stop`` — a completed task here frees its ``job_name`` slot immediately (see
    :meth:`exists`/:meth:`schedule`): there is no lingering substrate object to block a re-run.
    """

    def __init__(
        self, bus: Bus, executor_factory: Callable[[], Executor], *, max_history: int = 1000
    ) -> None:
        self._bus = bus
        self._factory = executor_factory
        self._tasks: dict[str, asyncio.Task[None]] = {}
        # WHY a counter (not a scan of _tasks): _tasks retains completed entries so status()
        # can return terminal state instead of not_found, which means active_count() would
        # otherwise be O(history). This counter increments per schedule() and decrements via a
        # done_callback on every completion path (return, exception, cancel) — admission stays O(1).
        self._active = 0
        # WHY bounded: unlike K8sJobRunner, whose finished Job is
        # reclaimed by a substrate TTL, this dict has no external reaper — a long-lived local-mode
        # process would otherwise retain one Task (plus any stored exception/traceback) per
        # distinct topic for the process lifetime. `_prune_history` caps it the same way a Job's
        # `ttlSecondsAfterFinished` does: oldest FINISHED entries age out once over the cap, never
        # a still-running one.
        self._max_history = max_history

    def _on_done(self, task: asyncio.Task[None]) -> None:
        # INVARIANT: every schedule() registers this callback exactly once, so each run decrements
        # exactly once regardless of how it ends (succeeded/failed/cancelled).
        self._active -= 1
        self._prune_history()

    def _prune_history(self) -> None:
        if len(self._tasks) <= self._max_history:
            return
        # Oldest-first (dict preserves insertion order) — evict only DONE entries; an in-flight
        # task's slot is never reclaimed early (that would reopen the "already running" guard).
        for name, task in list(self._tasks.items()):
            if len(self._tasks) <= self._max_history:
                return
            if task.done():
                del self._tasks[name]

    def schedule(
        self,
        topic: str,
        url4: str,
        deadline_s: int,
        *,
        traceparent: str | None = None,
        credential: str | None = None,
        profile: str | None = None,
    ) -> str:
        # NOTE: deadline_s is accepted per the JobRunner Protocol but not enforced in v1 — a hard
        # per-run timeout (surfacing as "timed_out") is a substrate concept the local runner does
        # not yet model; see local-mode PRD open questions.
        # credential/profile are accepted per the Protocol but INTENTIONALLY dropped in local mode:
        # local uses a single process-level aigateway credential baked into a shared world (built at
        # app startup), not the per-run forwarded one — see make_local_app's local-credential model.
        # Per-request credential forwarding is a prod-only (k8s) feature.
        name = job_name(topic)
        existing = self._tasks.get(name)
        if existing is not None and not existing.done():
            raise JobAlreadyExists(name)
        task = asyncio.get_running_loop().create_task(
            publish.run(self._bus, self._factory(), topic, url4, traceparent=traceparent)
        )
        task.add_done_callback(self._on_done)
        self._tasks[name] = task
        self._active += 1
        return name

    def stop(self, topic: str) -> None:
        # INVARIANT: idempotent — an absent or already-finished task is a no-op stop.
        # WHY no purge here: the REST DELETE route calls `job_runner.stop()` then separately
        # `await bus.purge()` itself; the WS bridge's Stop handling calls `job_runner.stop()` with
        # no purge at all. Purging here would be redundant with the route and wrong for the bridge
        # path — mirrors K8sJobRunner, which does not purge either.
        task = self._tasks.get(job_name(topic))
        if task is not None and not task.done():
            task.cancel()

    def exists(self, topic: str) -> bool:
        task = self._tasks.get(job_name(topic))
        return task is not None and not task.done()

    def status(self, topic: str) -> JobStatus:
        return _map_status(self._tasks.get(job_name(topic)))

    def active_count(self) -> int:
        """Count of tasks still running — the local-mode max-runs admission gate (PRD §3.3.7)."""
        return self._active

    async def aclose(self) -> None:
        """Cancel every in-flight task and await them — graceful shutdown (PRD §3.3.4)."""
        pending = [task for task in self._tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
