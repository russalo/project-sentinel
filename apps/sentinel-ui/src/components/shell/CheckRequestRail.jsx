// CheckRequestRail — the d100 check affordance + roll reveal (ADR-0005
// resolution module / RFC-0006 Slice 2). Renders above the command bar
// (a sibling of ActionPillRail) when the DM has requested a check.
//
// Three beats:
//   1. Request — "🎲 BODY check — Hard (80)  [Roll]" + the DM's prompt.
//   2. Reveal  — click-to-roll; a static count-up of d100 + bonus → total
//      vs target, with the margin band. (Animated dice are a later polish.)
//   3. Resolve — the roll lands as a line in the scroll, and the turn
//      resends carrying the result so the DM resolves from the margin.
//
// The d100 is rolled CLIENT-SIDE (real randomness, not LLM bias) — see
// utils/roll.js. The player's governing-stat value is read from the
// player character's module_data.character_sheet.stats; missing stats
// default to 5 (ordinary), so a roll never strands even mid-migration.

import { useEffect, useRef, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useWorldStore } from '../../stores/worldStore';
import { usePlayerStore } from '../../stores/playerStore';
import { useDMStream } from '../../hooks/useDMStream';
import { computeRoll, toWirePayload, marginBand } from '../../utils/roll';

const STAT_LABEL = { body: 'Body', mind: 'Mind', heart: 'Heart', will: 'Will' };
const TARGET_LABEL = { 40: 'Easy', 60: 'Moderate', 80: 'Hard', 100: 'Very Hard' };

const TONE_TEXT = {
  blood: 'text-blood',
  amber: 'text-amber',
  leyline: 'text-leyline',
};

// Find the player character's score for a stat (1-10), defaulting to 5.
function playerStatValue(characters, playerName, stat) {
  let player = null;
  if (playerName) {
    player = characters.find((c) => c?.role === 'player' && c?.name === playerName)
      || characters.find((c) => c?.name === playerName);
  }
  if (!player) player = characters.find((c) => c?.role === 'player');
  const v = player?.module_data?.character_sheet?.stats?.[stat];
  return Number.isInteger(v) && v >= 1 && v <= 10 ? v : 5;
}

export function CheckRequestRail() {
  const checkRequest = useChatStore((s) => s.checkRequest);
  const addMessage = useChatStore((s) => s.addMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const setIsStreaming = useChatStore((s) => s.setIsStreaming);
  const characters = useWorldStore((s) => s.characters);
  const playerName = usePlayerStore((s) => s.characterName);
  const sessionId = usePlayerStore((s) => s.sessionId);
  const { sendRoll } = useDMStream();
  const [revealed, setRevealed] = useState(null);
  const timerRef = useRef(null);

  // Reset the local reveal whenever the check request changes/clears, so a
  // stale reveal can't bleed into the next request.
  useEffect(() => {
    setRevealed(null);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [checkRequest]);

  if (!checkRequest) return null;

  const { stat, target, label, prompt, effectDie } = checkRequest;
  const statLabel = STAT_LABEL[stat] || stat;
  const targetLabel = TARGET_LABEL[target] || `Target ${target}`;

  const handleRoll = () => {
    if (revealed || isStreaming) return;
    // Lock the turn immediately so the command input (which gates on
    // isStreaming) can't race a competing action during the reveal pause
    // before sendRoll fires. runTurn re-asserts this and clears it in its
    // finally. (codex P2 on PR #146.)
    setIsStreaming(true);
    const statValue = playerStatValue(characters, playerName, stat);
    // effectDie present → a magnitude check (attack weapon die / spell die):
    // roll it alongside the d100. (RFC-0007 combat, RFC-0008 magic.)
    const result = computeRoll({ stat, statValue, target, effectDie });
    setRevealed(result);
    // Beat 3: drop a concise roll line into the scroll for the history,
    // then resend the turn so the DM resolves from the margin. The brief
    // pause lets the reveal register before the resolution stream starts
    // (which clears the check request + unmounts this rail).
    const band = marginBand(result.margin, result.openEnded);
    addMessage({
      type: 'system',
      content: `🎲 ${statLabel} vs ${targetLabel} ${target} — ${result.total} (margin ${result.margin >= 0 ? '+' : ''}${result.margin}): ${band.label}`,
      timestamp: new Date(),
    });
    timerRef.current = setTimeout(() => {
      sendRoll(toWirePayload(result), label || `${statLabel} check`, sessionId);
    }, 900);
  };

  const band = revealed ? marginBand(revealed.margin, revealed.openEnded) : null;

  return (
    <div className="px-3 lg:px-6 pt-2 pb-1">
      <div className="rounded border border-amber/60 bg-amber/5 px-3 py-2">
        {!revealed ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs font-cinzel text-amber uppercase tracking-wide">
                🎲 {statLabel} check — {targetLabel} ({target})
              </div>
              {prompt && (
                <div className="text-sm text-dust mt-0.5 truncate">{prompt}</div>
              )}
            </div>
            <button
              type="button"
              data-testid="check-roll-button"
              onClick={handleRoll}
              disabled={isStreaming}
              className="shrink-0 px-4 py-1.5 bg-amber text-void rounded font-medium hover:bg-amber/90 transition-colors disabled:opacity-50"
            >
              Roll
            </button>
          </div>
        ) : (
          <div data-testid="check-reveal" className="font-mono text-sm text-ink">
            <div className="flex justify-between"><span className="text-dust">d100</span><span>{revealed.rolled}{revealed.openEnded ? ` (${revealed.openEnded === 'high' ? '+' : ''}${revealed.openEndedRoll} open-ended)` : ''}</span></div>
            <div className="flex justify-between"><span className="text-dust">+ {statLabel} ×5</span><span>+{revealed.bonus}</span></div>
            <div className="flex justify-between border-t border-border mt-1 pt-1"><span className="text-dust">total vs {target}</span><span>{revealed.total}</span></div>
            <div className={`flex justify-between font-cinzel ${TONE_TEXT[band.tone] || 'text-ink'}`}>
              <span>margin {revealed.margin >= 0 ? '+' : ''}{revealed.margin}</span>
              <span>{band.label}</span>
            </div>
            {revealed.effectRoll !== null && revealed.effectRoll !== undefined && (
              <div data-testid="check-effect-roll" className="flex justify-between border-t border-border mt-1 pt-1">
                <span className="text-dust">effect {revealed.effectDie}</span>
                <span>{revealed.effectRoll}{revealed.margin >= 0 ? ` + ${Math.floor(revealed.margin / 10)} (margin)` : ''}</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
