"""MCP Bridge HTTP clients.

Each submodule here wraps one MCP server's HTTP API. Callers import the
specific client they need — e.g. `from engine.dispatch.fs_manager import
apply_world_update` or `from engine.dispatch.git_sync import commit_snapshot`.
The top-level `engine` package re-exports the most common entry points
for convenience.

Keeping dispatch out of the agents (`engine/agents/*.py`) preserves the
engine's layering: agents produce structured payloads; dispatch sends them
somewhere. Agents do not import dispatch modules directly — that way the
Fact-Extractor and DM agent can be unit-tested with no network at all, and
the dispatcher can be unit-tested with no LLM at all.

See docs/adr/0001-data-canonical-source-of-truth.md for why the MCP Bridge
exists and why engine writes must go through it.
"""

from .fs_manager import DispatchResult, apply_world_update
from .git_sync import commit_snapshot, init_world

__all__ = ["DispatchResult", "apply_world_update", "commit_snapshot", "init_world"]
