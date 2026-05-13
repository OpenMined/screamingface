"""python-runner plugin — runs Python scripts referenced by URL4 expressions.

This package is a scaffold (DEMO-009 / SF-156). Execution arrives in:

- DEMO-010 — subprocess runner + JSON I/O contract
- DEMO-012 — sandbox-exec on darwin
- DEMO-013 — real ``/python`` route + ``/data/code/<name>.py`` serve route
- DEMO-016 — vendored HLE scripts under ``_vendored/``
- DEMO-030 — Monaco RJSF widget reading the ``x-code-editor`` annotation
"""

from screamingface.plugins.python_runner.plugin import PythonRunnerPlugin

__all__ = ["PythonRunnerPlugin"]
