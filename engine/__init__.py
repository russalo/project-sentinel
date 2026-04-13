"""Project Sentinel Inference Engine.

Pure-Python core for the DM → Fact-Extractor → world_update pipeline.
Does not import Django. Does not touch disk. Does not call MCP servers.
Callers are responsible for side effects.

See engine/README.md for the full boundary contract.
"""

from .schema import ValidationResult, validate
from .types import Config, DMTurnInput, DMTurnResult, WorldContext

__all__ = [
    "Config",
    "DMTurnInput",
    "DMTurnResult",
    "WorldContext",
    "ValidationResult",
    "validate",
]
