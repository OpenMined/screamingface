"""``url4://`` share strings — encode a fusion into a portable recipe.

AIDEV-NOTE: this flat format is INTERIM (spec §3). The real url4 expression
grammar (`packages/url4`, `(sources)!intent`) replaces it in OME-408 — which is
why encoding lives alone in this module and nothing else knows the format.
Decoding (`from_url4`) is OME-408 scope and intentionally absent.

Grammar::

    url4://<name>?models=<id>+<id>&reduce=<strategy>&loop=<mode>&judge=<id>

`judge` is emitted only when set.
"""

from __future__ import annotations

from .fusion_core import FusionCore


def to_url4(fusion: FusionCore) -> str:
    models = "+".join(s.model.id for s in fusion.slots)
    url = (
        f"url4://{fusion.name}?models={models}"
        f"&reduce={fusion.reduce_strategy}&loop={fusion.loop_mode}"
    )
    if fusion.judge_model_id:
        url += f"&judge={fusion.judge_model_id}"
    return url
