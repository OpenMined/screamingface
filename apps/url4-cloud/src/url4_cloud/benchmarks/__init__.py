"""Benchmark assets baked into the Runner image.

Neither the control plane nor the run mode imports this package: its modules are executed as
SUBPROCESSES by declared `[commands]` routes (see `runner/config.CommandSpec`). It therefore
imports nothing from either half and nothing from the url4 engine — it is a shared leaf by
construction, and the layering gate treats it as one.
"""
