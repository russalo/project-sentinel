"""POST /api/stream — SSE streaming DM turn.

This is the endpoint the frontend's ``useDMStream`` hook hits on every
player action. It:

1. Reads the active session from disk (via state/sessions.py)
2. Builds a WorldContext from data/state/*.json (via state/world_context.py)
3. Opens an SSE response
4. Streams DM tokens live via engine.agents.dm.stream_turn
5. After the stream closes, parses the accumulated response with
   the Fact-Extractor and dispatches the result to fs-manager
6. Emits a world_update SSE event (in the DM hint shape the frontend
   expects) and a [DONE] sentinel

SSE event shapes (preserved from the Django backend so the frontend
works without changes):

  data: {"type": "token", "content": "<chunk>"}
  data: {"type": "world_update", "data": {world, characters, ...}}
  data: {"type": "error", "content": "<message>"}
  data: [DONE]

The handler does not expose ``system`` events (the frontend handles
them defensively but the old backend never emitted them either).
"""

import json
import logging
import re
from typing import Iterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

import engine
from engine import death_stakes
from engine.agents import dm as dm_agent
from engine.agents import fact_extractor

from .. import mock_dm

from ..auth.access import enforce_world_token
from ..concurrency import StreamSlotLimiter
from ..config import Settings
from ..engine_bridge import build_engine_config
from ..ratelimit import enforce, enforce_llm_ceiling
from ..schemas import StreamRequest
from ..state import sessions as session_state
from ..state.lorekeeper import retrieve_canon
from ..state.world_context import load_world_context
from ..state.world_root import find_session_data_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_BLOCK_RE = re.compile(r"<world_update>([\s\S]*?)</world_update>")


class _SlotReleasingIterator:
    """Iterator wrapping the SSE body that releases its concurrency slot once.

    Defends against the GEN_CREATED edge case (gemini high on PR #106):
    a Python generator that has been ``close()`` d **before its first
    ``next()``** does NOT execute its ``try/finally``. Starlette will close
    the body iterator on response teardown OR client disconnect; if that
    happens before iteration begins, a `finally`-based release would leak
    the slot permanently.

    Class-based pattern with belt-and-suspenders coverage:
    - ``__next__`` releases on StopIteration and on exception (mid-stream).
    - ``close()`` releases (Starlette's explicit teardown hook).
    - ``__del__`` releases (GC safety net for any escape we missed).
    - ``_released`` flag makes all paths idempotent — the limiter's own
      double-release defense is the second line; this is the first.
    """

    def __init__(
        self,
        inner_iterable,
        limiter: "StreamSlotLimiter",
        on_release=None,
    ) -> None:
        self._iter = iter(inner_iterable)
        self._limiter = limiter
        # Optional callback for observability (e.g. admin_metrics.stream_released).
        # Invoked exactly once, in the same release-once block. Failures are
        # swallowed — a metrics bug must not affect the slot lifecycle.
        self._on_release = on_release
        self._released = False

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return next(self._iter)
        except BaseException:
            # Includes StopIteration (normal completion) and any other
            # exception inside the inner generator. Release, then propagate
            # so Starlette sees the same flow it would have seen otherwise.
            self._release_once()
            raise

    def close(self) -> None:
        """Called by Starlette on response teardown / client disconnect.

        Forwards to the inner generator's close() if present (so its
        finally fires when it WAS started), then releases the slot.
        """
        close = getattr(self._iter, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                # Inner close failure must not prevent slot release.
                pass
        self._release_once()

    def __del__(self) -> None:
        # Final GC-time safety net. May not run during interpreter shutdown,
        # which is fine — the process exiting releases the OS-level resources.
        self._release_once()

    def _release_once(self) -> None:
        if not self._released:
            self._released = True
            self._limiter.release()
            if self._on_release is not None:
                try:
                    self._on_release()
                except Exception:
                    # Observability bug must not affect slot lifecycle.
                    pass


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _parse_frontend_hint(raw: str) -> dict:
    """Pull the raw <world_update> hint block out of a DM response.

    Returns the DM's hint-shape JSON (what the frontend's worldStore
    expects), not the apply_world_update.schema.json shape.
    """
    match = _BLOCK_RE.search(raw)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _mirror_death_outcome_to_hint(
    hint: dict, player_name: str, outcome_hint: dict
) -> None:
    """Patch the PC's entry in the SSE ``world_update`` hint to the committed
    death-save status + clock (RFC-0014), so the UI never renders the DM's stale
    version. If the DM emitted no PC entry (e.g. no ``<world_update>`` at all —
    the synth-payload case), ADD one so the committed death still reaches the UI
    without a refresh (codex P2 on PR #172). In-place; tolerant of a malformed
    hint."""
    if not isinstance(hint, dict) or not isinstance(player_name, str):
        return
    chars = hint.get("characters")
    if not isinstance(chars, list):
        chars = []
        hint["characters"] = chars
    lowered = player_name.strip().lower()
    pc = None
    for char in chars:
        if isinstance(char, dict) and str(char.get("role", "")).lower() == "player":
            pc = char
            break
    if pc is None:
        for char in chars:
            if (
                isinstance(char, dict)
                and str(char.get("name", "")).strip().lower() == lowered
            ):
                pc = char
                break
    if pc is None:
        # No PC entry to correct — add a minimal one carrying the committed death.
        pc = {"name": player_name, "role": "player", "action": "upsert"}
        chars.append(pc)
    pc["status"] = outcome_hint.get("status", pc.get("status"))
    module_data = pc.setdefault("module_data", {})
    if isinstance(module_data, dict):
        combat = module_data.setdefault("combat", {})
        if isinstance(combat, dict):
            combat["death_saves_failed"] = outcome_hint.get("failed")


@router.post("/stream")
def stream_turn(request: Request, body: StreamRequest) -> StreamingResponse:
    # NOTE: This handler is deliberately `def`, not `async def`.
    # The generator it returns iterates engine.agents.dm.stream_turn
    # (a synchronous generator), and every dispatch inside it is
    # synchronous blocking I/O (fs-manager HTTP, file reads). FastAPI
    # runs sync handlers — and sync generators returned to
    # StreamingResponse — in a thread pool, so they don't stall the
    # event loop. An `async def` handler with an async generator
    # that drives a sync iterator internally would block the loop
    # on every token.
    settings: Settings = request.app.state.settings
    config = build_engine_config(settings)

    # Resolve the world's own data tree (ADR 0002 Slice 3). The *session* is the
    # authoritative routing key: find the world whose tree holds this session,
    # rather than trusting a client-supplied world_id. This keeps reads and
    # writes consistent (writes go to session.world_id) and means the cutover
    # works without any frontend change — the client need not send world_id.
    # With SENTINEL_WORLDS_ROOT unset (today's default) this returns the shared
    # tree. None → the session doesn't exist in any world (or a bad id).
    data_dir = find_session_data_dir(
        settings.worlds_root, body.session_id, default_data_dir=settings.data_dir
    )
    session = (
        session_state.read_session(data_dir, body.session_id)
        if data_dir is not None
        else None
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session not found or inactive",
        )
    if not session.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active",
        )

    # ADR 0003 Slice A — verify the per-world token against the world the
    # *session* belongs to (session.world_id), never a client-asserted id, so a
    # token for world A can't drive a session in world B. No-op when enforcement
    # is off. A legacy session predating world_id (empty) can't be token-gated;
    # that only occurs in shared-tree dev where enforcement is off anyway.
    enforce_world_token(request, settings, session.world_id or "")

    # ADR 0003 access dim #3 — max concurrent /api/stream. Acquire BEFORE the
    # rate-limit + LLM-ceiling checks so a 503-capacity-rejected request never
    # burns budget counters (codex P1 on #106: a burst of over-capacity attempts
    # otherwise consumes the daily LLM ceiling without ever calling an LLM, then
    # blocks real turns with 429s). Released on slot teardown in
    # `_SlotReleasingIterator` (defense-in-depth: explicit `close()`, `__del__`,
    # and idempotent `release_once()` — gemini high on #106 about the
    # GEN_CREATED edge case where a generator's `finally` doesn't run if it's
    # never iterated).
    stream_limiter: StreamSlotLimiter = request.app.state.stream_limiter
    admin_metrics = request.app.state.admin_metrics
    if not stream_limiter.try_acquire():
        admin_metrics.capacity_rejected()
        raise HTTPException(
            status_code=503,
            detail="sentinel is at concurrency capacity; retry shortly",
            headers={"Retry-After": "5"},
        )
    # Counter side of the slot acquire: bumps streams_served + active_streams.
    # Paired with admin_metrics.stream_released() inside _SlotReleasingIterator
    # so it tracks the same lifecycle as the semaphore permit.
    admin_metrics.stream_acquired()

    try:
        # ADR 0003 Slice B — per-world turn rate-limit + the global daily LLM-call
        # ceiling, before the (paid) DM stream starts. Both no-op when unset.
        # Inside the try so a rate-limit or ceiling raise releases the slot.
        limiter = request.app.state.rate_limiter
        enforce(
            limiter,
            f"stream:{session.world_id or body.session_id}",
            settings.rl_stream_per_minute,
            60,
            detail="too many turns; slow down",
        )
        enforce_llm_ceiling(limiter, settings.llm_daily_ceiling)
    except HTTPException as exc:
        # 429 is the only HTTPException these enforce calls raise. Count it
        # before re-raising so the dashboard sees rate-limit pressure.
        if exc.status_code == 429:
            admin_metrics.rate_limited()
        stream_limiter.release()
        admin_metrics.stream_released()
        raise
    except Exception:
        stream_limiter.release()
        admin_metrics.stream_released()
        raise

    # Build the world context the DM will see for this turn.
    recent = [
        {
            "playerAction": t.get("player_action", ""),
            "narrative": t.get("narrative", ""),
        }
        for t in session.turns[-5:]
    ]
    world_context = load_world_context(
        data_dir,
        session_id=body.session_id,
        recent_turns=recent,
    )

    # RFC-0011 Lorekeeper fold: retrieve relevant canon for this turn and inject
    # it into the DM prompt so the DM cites established canon instead of
    # improvising it. Dormant unless SENTINEL_LOREKEEPER_ENABLED; fail-open
    # (a missing/broken poggio degrades to no canon, never breaks the turn).
    retrieved_lore = retrieve_canon(data_dir, world_context, body.action, settings)

    # RFC-0014 death-stakes: a death save is DERIVED FROM SERVER STATE, not the
    # client's `roll.kind`. The trigger is "there is a roll AND the PC's STORED
    # status is `unconscious`" — the only state a death save is valid in. Keying
    # off the client-echoed `kind` would let a crafted/stale client either force
    # a save when the PC is fine, or send `kind:"skill"` to bypass engine
    # authority on a real save and reopen the forged-margin path (codex P1 on PR
    # #172). `kind` stays advisory for the UI only. The engine then computes the
    # outcome from the validated roll + the PC's STORED `will` and clock (a
    # crafted client `margin` can't dodge death; only `rolled` is server-
    # validated), rides it into the prompt as a narrate-not-decide block, and
    # injects it authoritatively into the write payload below (Q1 = 2a).
    death_outcome_obj = None
    death_outcome_hint: dict | None = None
    death_pc_module_data: dict | None = None
    if body.roll is not None:
        _pc = death_stakes.find_player_character(
            world_context.characters, session.player_character_name
        )
        if _pc is not None and str(_pc.get("status", "")).lower() == "unconscious":
            death_pc_module_data = _pc.get("module_data")
            death_outcome_obj = death_stakes.resolve_death_save(
                rolled=body.roll.rolled,
                will=death_stakes.stored_will(_pc),
                current_failed=death_stakes.stored_death_clock(_pc),
            )
            death_outcome_hint = {
                "status": death_outcome_obj.status,
                "failed": death_outcome_obj.failed,
                "stabilized": death_outcome_obj.stabilized,
                "died": death_outcome_obj.died,
            }

    turn_input = engine.DMTurnInput(
        session_id=body.session_id,
        player_action=body.action,
        world_context=world_context,
        retrieved_lore=retrieved_lore,
        # ADR-0005 resolution module (RFC-0006): on a resolve turn the body
        # carries the d100 roll; model_dump() yields the snake-case keys the
        # engine's ROLL RESULT block reads. None on an ordinary turn.
        roll=body.roll.model_dump() if body.roll is not None else None,
        # RFC-0014: the engine-committed death-save outcome, rendered as a
        # narrate-not-decide block. None on any non-death-save turn.
        death_outcome=death_outcome_hint,
        # ADR-0005 progression module (RFC-0009): on a level-up turn the body
        # carries the player's chosen stat; the engine renders it as a
        # LEVEL-UP CHOICE block. None otherwise.
        level_up=body.level_up.model_dump() if body.level_up is not None else None,
    )

    next_turn_number = (session.turns[-1]["turn_number"] + 1) if session.turns else 1

    def generator() -> Iterator[str]:
        buffer: list[str] = []

        try:
            # RFC-0016: in mock-DM mode, inject the fixture client for this turn
            # in place of the live LLM. Built inside the try so a fixture over-run
            # (KeyError) surfaces as the generic "DM agent failed" SSE, not a 500.
            dm_client = (
                mock_dm.client_for_turn(settings, next_turn_number)
                if settings.dm_mode == "mock"
                else None
            )
            for token in dm_agent.stream_turn(config, turn_input, client=dm_client):
                buffer.append(token)
                yield _sse_event({"type": "token", "content": token})
        except Exception:  # pragma: no cover - network/OpenAI failure
            # Log the full traceback server-side (exc_info=True); send the client a
            # generic message — the upstream string can carry org id + quota
            # (red-team #4).
            logger.warning("DM stream failed", exc_info=True)
            yield _sse_event(
                {"type": "error", "content": "DM agent failed; please retry."}
            )
            yield "data: [DONE]\n\n"
            return

        raw_response = "".join(buffer)
        narrative = _BLOCK_RE.sub("", raw_response).strip()
        frontend_hint = _parse_frontend_hint(raw_response)

        # RFC-0014: mirror the engine-committed death outcome into the SSE hint so
        # the UI shows the authoritative status immediately — otherwise the DM's
        # (possibly "alive") version would render until a refresh re-hydrates the
        # committed state.
        if death_outcome_hint is not None:
            _mirror_death_outcome_to_hint(
                frontend_hint, session.player_character_name, death_outcome_hint
            )

        # Emit the world_update event in the shape the frontend
        # expects (DM hint shape, not the fs-manager schema shape).
        yield _sse_event({"type": "world_update", "data": frontend_hint})

        # Dispatch the canonical payload through the engine →
        # fs-manager path. Failure here is logged as an error event
        # so the frontend can surface it; the narrative has already
        # streamed to the player so we never roll back.
        extracted = fact_extractor.extract(
            raw_response,
            session_id=body.session_id,
            turn_number=next_turn_number,
        )

        payload = extracted.payload
        # RFC-0014: a death-save resolve turn MUST write the engine's committed
        # outcome even if the DM emitted no <world_update> — synthesize a minimal
        # payload so the status/clock still land authoritatively.
        if death_outcome_obj is not None and payload is None:
            # log_entry has a schema minLength of 10 — a short DM narrative would
            # make fs-manager reject the whole payload and silently drop the
            # committed death (swarm HIGH on PR #172). Fall back to a fixed
            # >=10-char entry whenever the narrative is too short.
            _narrative = narrative[:200]
            payload = {
                "session_id": body.session_id,
                "log_entry": (
                    _narrative
                    if len(_narrative.strip()) >= 10
                    else f"Turn {next_turn_number} — death save resolved."
                ),
                "updates": [],
            }

        if payload is not None:
            # Engine-authoritative death outcome (Q1 = 2a): override any
            # conflicting DM-emitted status/clock so a hallucinated "you recover"
            # can't beat a rolled death.
            if death_outcome_obj is not None:
                death_stakes.apply_death_outcome(
                    payload,
                    player_name=session.player_character_name,
                    outcome=death_outcome_obj,
                    # Pass the PC's STORED module_data so the write carries the
                    # full sheet — fs-manager's shallow merge would otherwise
                    # erase character_sheet (stats/HP) behind the death clock.
                    stored_module_data=death_pc_module_data,
                )
            # Permadeath gate (Q2): on EVERY turn, refuse to revive a stored-dead
            # PC when the world's permadeath flag is set. Rejections surface to
            # the player and the state stays dead — the DM sees it unchanged next
            # turn.
            _, permadeath_rejections = death_stakes.enforce_permadeath(
                payload,
                stored_characters=world_context.characters,
                player_name=session.player_character_name,
                permadeath=session.permadeath,
            )
            for rejection in permadeath_rejections:
                yield _sse_event({"type": "error", "content": rejection})

            dispatch = engine.apply_world_update(
                config, payload, world_id=session.world_id or None
            )
            if not dispatch.ok:
                yield _sse_event(
                    {
                        "type": "error",
                        "content": f"fs-manager rejected update: {dispatch.error}",
                    }
                )

        # Append the turn to the session file and re-serialize it.
        session.turns.append(
            {
                "id": next_turn_number + 1,
                "session_id": body.session_id,
                "turn_number": next_turn_number,
                "player_action": body.action,
                "narrative": narrative,
                "world_updates": frontend_hint,
                "created_at": "",  # created_at currently unused by the frontend
            }
        )
        session_write = session_state.write_session(
            config,
            session,
            log_entry=narrative[:200] or f"Turn {next_turn_number} completed.",
            turn_number=next_turn_number,
        )

        # Commit the snapshot via git-sync regardless of whether the
        # session-file write succeeded. The apply_world_update
        # dispatch above may have already written real entity /
        # location / item / world state mutations — if we skip the
        # commit on session-write failure we silently drop those
        # mutations out of the audit trail. Committing whatever is
        # on disk captures the partial success honestly: the commit
        # will include whatever fs-manager wrote (world state, etc.)
        # and exclude whatever it didn't (the session file append).
        # Per ADR 0001 Phase 1, every fs-manager write is supposed
        # to produce a git commit, no exceptions.
        commit_result = engine.commit_snapshot(
            config,
            session_id=body.session_id,
            turn_number=next_turn_number,
            summary=narrative[:200] or f"Turn {next_turn_number} completed.",
            world_id=session.world_id or None,
        )

        # Both failure modes surface as structured error SSE events
        # so the frontend can show a system message. We still emit
        # [DONE] below regardless so the stream closes cleanly.
        if not session_write.ok:
            # If the session write fails, the narrative has already
            # been streamed to the player and the game is in a
            # half-persisted state: the world-state dispatch
            # succeeded, but the per-session turn log and counter
            # didn't advance. The next turn will regenerate from
            # whatever `recent_turns` the stale session file has.
            yield _sse_event(
                {
                    "type": "error",
                    "content": f"Failed to save turn to session: {session_write.error}",
                }
            )
        if not commit_result.ok:
            # Narrative and disk state are durable; only the audit
            # trail missed this turn. Emit the dispatcher's error
            # directly — it already includes the "git-sync rejected
            # commit (<status>):" prefix so wrapping it again would
            # produce redundant double prefixes in the UI.
            yield _sse_event({"type": "error", "content": commit_result.error})

        yield "data: [DONE]\n\n"

    # Wrap the inner generator so the slot is guaranteed released exactly once,
    # even in the GEN_CREATED edge case where a generator is gc'd without ever
    # being iterated (gemini high on #106): `finally` blocks don't run on a
    # generator that's been close()d before its first `next()`. Class-based
    # iterator + explicit `close()` + `__del__` safety net + idempotent
    # `release_once()` covers normal completion, mid-stream exception, client
    # disconnect, AND the never-started case.
    return StreamingResponse(
        _SlotReleasingIterator(
            generator(),
            stream_limiter,
            on_release=admin_metrics.stream_released,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
