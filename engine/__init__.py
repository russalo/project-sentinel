"""Project Sentinel Inference Engine.

Pure-Python core for the DM → Fact-Extractor → world_update pipeline.
Does not import Django. Does not touch disk. Does not call MCP servers.
Callers are responsible for side effects.

See engine/README.md for the full boundary contract.
"""

from .dispatch import DispatchResult, apply_world_update
from .schema import ValidationResult, validate
from .types import Config, DMTurnInput, DMTurnResult, IntroInput, WorldContext

__all__ = [
    "Config",
    "DMTurnInput",
    "DMTurnResult",
    "IntroInput",
    "WorldContext",
    "ValidationResult",
    "validate",
    "DispatchResult",
    "apply_world_update",
]
