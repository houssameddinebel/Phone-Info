"""phoneinfo — offline phone-number intelligence with optional carrier enrichment."""

from . import mnc
from .core import InvalidNumber, analyze, batch, candidates, redact
from .providers import REGISTRY, ProviderError, enrich

__all__ = [
    "analyze",
    "batch",
    "candidates",
    "redact",
    "InvalidNumber",
    "enrich",
    "ProviderError",
    "REGISTRY",
    "mnc",
]

__version__ = "0.3.0"
