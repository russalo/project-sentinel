// LevelUpCard — the level-up enactment affordance (ADR-0005 progression
// module / RFC-0009). Renders above the command bar (a sibling of
// CheckRequestRail) when the DM has PROPOSED a level-up — it emits
// `level_up: {to_level}` in the world_update hint at an earned beat, then
// STOPS. The DM never picks the stat or writes the level itself: that
// choice is the player's (the PC-ownership wall). This card is where the
// player exercises it.
//
// Two beats:
//   1. Propose — "⬆ You've reached level N — raise one attribute" + four
//      stat buttons (Body / Mind / Heart / Will).
//   2. Enact   — the player picks a stat and confirms; a line drops into
//      the scroll and the turn resends carrying the choice, so the DM
//      applies exactly the chosen package (level → N, that stat +1, max HP
//      grows by the class factor, the Will pool recomputes).
//
// The current per-stat scores are read from the player character's
// module_data.character_sheet.stats so the player sees what each pick
// would become; a stat already at the cap (10) is disabled.

import { useEffect, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useWorldStore } from '../../stores/worldStore';
import { usePlayerStore } from '../../stores/playerStore';
import { useDMStream } from '../../hooks/useDMStream';

const STATS = [
  { key: 'body', label: 'Body' },
  { key: 'mind', label: 'Mind' },
  { key: 'heart', label: 'Heart' },
  { key: 'will', label: 'Will' },
];
const STAT_CAP = 10;

// Resolve the player character's sheet stats ({} when unknown), mirroring
// CheckRequestRail's playerStatValue selection so the same PC is read.
function playerStats(characters, playerName) {
  let player = null;
  if (playerName) {
    player = characters.find((c) => c?.role === 'player' && c?.name === playerName)
      || characters.find((c) => c?.name === playerName);
  }
  if (!player) player = characters.find((c) => c?.role === 'player');
  const stats = player?.module_data?.character_sheet?.stats;
  return stats && typeof stats === 'object' ? stats : {};
}

export function LevelUpCard() {
  const levelUp = useChatStore((s) => s.levelUp);
  const addMessage = useChatStore((s) => s.addMessage);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const setIsStreaming = useChatStore((s) => s.setIsStreaming);
  const characters = useWorldStore((s) => s.characters);
  const playerName = usePlayerStore((s) => s.characterName);
  const sessionId = usePlayerStore((s) => s.sessionId);
  const { sendLevelUp } = useDMStream();
  const [chosen, setChosen] = useState(null);

  // Reset the local selection whenever the proposal changes/clears so a
  // stale pick can't bleed into the next level-up.
  useEffect(() => {
    setChosen(null);
  }, [levelUp]);

  if (!levelUp) return null;

  const { toLevel } = levelUp;
  const stats = playerStats(characters, playerName);

  const handleConfirm = () => {
    if (!chosen || isStreaming) return;
    const cur = stats[chosen];
    if (Number.isInteger(cur) && cur >= STAT_CAP) return;
    // Lock the turn immediately so the command input (gated on isStreaming)
    // can't race a competing action before sendLevelUp fires. runTurn
    // re-asserts this and clears it in its finally. (Mirrors CheckRequestRail.)
    setIsStreaming(true);
    const label = STATS.find((s) => s.key === chosen)?.label || chosen;
    addMessage({
      type: 'system',
      content: `⬆ Level ${toLevel} — raised ${label}`,
      timestamp: new Date(),
    });
    sendLevelUp(chosen, toLevel, sessionId);
  };

  return (
    <div className="px-3 lg:px-6 pt-2 pb-1">
      <div className="rounded border border-amber/60 bg-amber/5 px-3 py-2">
        <div className="text-xs font-cinzel text-amber uppercase tracking-wide">
          ⬆ You've reached level {toLevel} — raise one attribute
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {STATS.map(({ key, label }) => {
            const cur = stats[key];
            const hasCur = Number.isInteger(cur);
            const atCap = hasCur && cur >= STAT_CAP;
            const selected = chosen === key;
            return (
              <button
                key={key}
                type="button"
                data-testid={`level-up-stat-${key}`}
                onClick={() => setChosen(key)}
                disabled={atCap || isStreaming}
                aria-pressed={selected}
                className={`rounded border px-2 py-1.5 text-sm transition-colors disabled:opacity-40 ${
                  selected
                    ? 'border-amber bg-amber text-void font-medium'
                    : 'border-border bg-void text-ink hover:border-amber/60'
                }`}
              >
                {label}
                {hasCur && (
                  <span className="block text-xs opacity-70">
                    {cur}{atCap ? ' (max)' : ` → ${cur + 1}`}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        <div className="mt-2 flex justify-end">
          <button
            type="button"
            data-testid="level-up-confirm"
            onClick={handleConfirm}
            disabled={!chosen || isStreaming}
            className="px-4 py-1.5 bg-amber text-void rounded font-medium hover:bg-amber/90 transition-colors disabled:opacity-50"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
