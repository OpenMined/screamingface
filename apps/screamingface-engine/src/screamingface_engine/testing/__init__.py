"""In-memory test doubles standing in for the real infrastructure adapters:
`build_run`/ `publish_mock_run` substitute a real Runner (no url4 execution, no
model calls) with a deterministic fixture.

`InMemoryEventStream` is re-exported here for the suite's convenience, but it is NOT
a test double any more — it is the local-mode event-stream adapter and lives in
`screamingface_engine.adapters.memory`. Production code must import it from there;
nothing shipped should depend on this package.
"""

from screamingface_engine.adapters.memory import InMemoryEventStream
from screamingface_engine.testing.mock_runner import build_run, publish_mock_run

__all__ = ["InMemoryEventStream", "build_run", "publish_mock_run"]
