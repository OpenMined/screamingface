# screamingface — the ScreamingFace Python SDK

Compose AI-model **fusions**, evaluate them on benchmarks, and read the **gain**
over the best single model.

```python
import screamingface as sf

sf.setup()                                    # connect providers
ids = sf.models.list(max_price=20)            # discover models under $20 / M tokens
fusion = sf.Fusion("fusion", models=ids[:3],
                   reduce="majority_vote", judge=ids[0])
fusion.url                                    # shareable url4:// recipe
run = fusion.evaluate("gpqa", first=20, seed=0)
run.score, run.baseline, run.gain             # the payoff
```

Start with the executed tutorial: [`examples/00_quickstart.ipynb`](examples/00_quickstart.ipynb).

## Status — v0.1, simulated backend

Benchmark **questions are real** (bundled GPQA sample; HF-Hub loader included). Model
**answers are deterministically simulated** behind the `EngineBackend` port
(`screamingface.engine`): same seed → identical run, and the fusion's lift emerges from
real voting math over per-model answers, not a hard-coded bonus. Real inference plugs in
as a second `EngineBackend` adapter (tracked as `OME-296`) without changing this API.
The `url4://` recipe string is an interim flat format; the real url4 expression grammar
integration is tracked as `OME-408`.

## Development

```sh
cd packages/screamingface
uv sync
uv run pytest
uv run ruff check && uv run ruff format --check
uv run pyright
```

Architecture: hexagonal — the studio surface (`Fusion`, `Run`, `sf.models`) sits over a
small engine core, with all answer generation behind the `EngineBackend` Protocol.
Core imports no transport, no IPython/widget machinery at import time.

## Releases

Not yet released to PyPI. The `screamingface` distribution name is reserved for this
package; the release lane (release-please) is registered at name lock.
