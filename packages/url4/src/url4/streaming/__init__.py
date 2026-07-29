"""The wire contract between the App and the Runner, and the ports they meet across.

The abstract contracts live in :mod:`url4.streaming.interfaces`; everything else here is
concrete — the codec, the protocol models, the trace helpers, and `lifecycle.run`, which drives
the ports without knowing any implementation of them.

Nothing is re-exported from this module. Every name is imported from the submodule that owns it
(`url4.streaming.interfaces`, `.codec`, `.trace`, `.protocol`), so an import says which layer it
reaches for and there is no second ``__all__`` to keep in sync with the first.
"""
