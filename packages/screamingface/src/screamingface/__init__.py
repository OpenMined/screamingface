"""screamingface — compose model fusions, run evals, study the lift.

FEATURE: the connect → compose → run → compare loop (App Iteration 1's SDK mirror):

    import screamingface as sf

    sf.setup()                                    # 1. connect providers
    ids = sf.models.list(max_price=20)            # 2. discover models
    fusion = sf.Fusion("fusion", models=ids[:3],  # 3. compose (url4 recipe)
                       reduce="majority_vote", judge=ids[0])
    run = fusion.evaluate("gpqa", first=20, seed=0)   # 4. run, reproducibly
    run.score, run.baseline, run.gain             # 5. the payoff

Benchmark *questions* are real; model *answers* are deterministically simulated
behind the `EngineBackend` port (`engine.py`) — the fusion's score emerges from
really applying the reduce strategy to the models' answers, so independent
errors produce genuine, explainable lift. Real inference plugs in as a second
`EngineBackend` adapter (`OME-296`) without changing this surface.
"""

from .catalog import BENCHMARKS, MODEL_META, PROVIDERS, BenchmarkSpec
from .datasets import Benchmark, Question, load_benchmark
from .engine import Answer, EngineBackend, SimulatedBackend, hash01
from .fusion_core import LOOP_MODES, REDUCE_STRATEGIES, FusionCore, Slot
from .models import Model, Pool, catalog, get_model
from .results import ModelResult, QuestionResult, RunResult
from .session import Session, connect, in_colab, session, setup
from .share import to_url4
from .studio import (
    DEFAULT_JUDGE_PROMPT,
    Fusion,
    ModelsService,
    Run,
    models,
    source_id,
    whoami,
)
from .widgets import MockHandle, mock_widgets

__version__ = "0.1.0"

__all__ = [
    # session
    "setup",
    "connect",
    "session",
    "Session",
    "in_colab",
    # discovery
    "models",
    "ModelsService",
    "Model",
    "Pool",
    "catalog",
    "get_model",
    "source_id",
    "whoami",
    # composition
    "Fusion",
    "FusionCore",
    "Slot",
    "REDUCE_STRATEGIES",
    "LOOP_MODES",
    "DEFAULT_JUDGE_PROMPT",
    # data
    "load_benchmark",
    "Benchmark",
    "Question",
    "BENCHMARKS",
    "BenchmarkSpec",
    "MODEL_META",
    "PROVIDERS",
    # running
    "Run",
    "RunResult",
    "ModelResult",
    "QuestionResult",
    # engine port
    "EngineBackend",
    "SimulatedBackend",
    "Answer",
    "hash01",
    # sharing
    "to_url4",
    # widgets
    "mock_widgets",
    "MockHandle",
    "__version__",
]
