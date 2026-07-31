"""The url4-cloud REST surface: run lifecycle, token minting, and model catalog routes.

Re-exports the FastAPI ``APIRouter``s (``router`` for run/token endpoints, ``catalog_router``
for the model catalog, ``benchmarks_router`` for the benchmark manifest catalog) and the
``SubscriberGate`` protocol so ``app.py`` can wire them without reaching into the individual
route modules.
"""

from url4_cloud.rest.benchmarks import router as benchmarks_router
from url4_cloud.rest.catalog import router as catalog_router
from url4_cloud.rest.interest import DenyAllGate, SubscriberGate
from url4_cloud.rest.routes import router

__all__ = ["DenyAllGate", "SubscriberGate", "benchmarks_router", "catalog_router", "router"]
