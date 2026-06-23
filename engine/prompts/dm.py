"""DM agent system prompt.

As of RFC-0005 (subsystem modularity, ADR-0005), the DM system prompt is
no longer a hand-authored constant here. It is **assembled** from the
active world's module set via ``engine.modules.build_dm_prompt``. The
former prompt content moved verbatim into the ``core/base-v1`` module's
fragment at ``engine/modules/base/base-v1/prompt.md``.

``DM_SYSTEM_PROMPT`` is preserved as a back-compat constant — the
assembled prompt for the default (base-only) module set, which is
byte-identical to the pre-RFC-0005 string. Callers that don't thread a
per-world module set (and the engine test suite) keep referencing it
unchanged. Callers that have a world's module map should call
``engine.modules.build_dm_prompt(modules)`` directly (the DM agent's
``_build_messages`` / ``_build_intro_messages`` now do).

History: originally ported verbatim from the retired
``backend/api/dm_ai.py`` during the ADR 0001 Phase 1 migration.
"""

from ..modules import build_dm_prompt

# Back-compat constant: the assembled prompt for the default module set
# (base only). Byte-identical to the former hand-authored string;
# guarded by an equivalence test in the module test suite.
DM_SYSTEM_PROMPT = build_dm_prompt()
