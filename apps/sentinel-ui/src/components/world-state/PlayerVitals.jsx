import { usePlayerStore } from '../../stores/playerStore';
import { useWorldStore } from '../../stores/worldStore';

// Player condition readout — an inked humanoid silhouette whose body fills
// with an amber→blood wash as HP drops, plus a categorical band label and
// the raw "N/100" number. Mirrors the tension-meter's render-time-derived
// band pattern from PR #124 so the world-state panel reads consistently:
// player condition at the top, world state in the middle, tension at the
// bottom — "you ↔ world" sandwich.
//
// Data source: the DM emits the player as a character with role='player' +
// health on every world_update (verified against live sessions). We find
// them by role rather than name so a renamed character still lands.
//
// Fallbacks:
//  - no player character yet in worldStore (hydration race or a DM that
//    didn't emit on intro) → synthesize a placeholder from playerStore.
//  - missing health → assume 100 (DM-prompt rule: first appearance defaults
//    to 100 when not specified; never invent a zero from absence).
//  - NaN / out-of-range → Number.isFinite gate + clamp to [0, 100], same
//    pattern WorldMetrics uses (gemini-medium fix on PR #124).

// One shared body geometry — used both as the clip-path region (filled, so
// the damage wash gets confined to the silhouette body) AND as the visible
// outline (stroke only, no fill). Single source of truth means the wash
// never escapes the outline. Path covers shoulders → arms hanging at the
// sides → tapered torso → split legs.
const BODY_PATH = `
  M 36 36
  C 30 38, 26 42, 24 50
  L 18 90
  L 24 100
  L 32 78
  L 36 80
  L 36 102
  L 32 174
  L 42 176
  L 48 174
  L 48 112
  L 52 112
  L 52 174
  L 58 176
  L 68 174
  L 64 102
  L 64 80
  L 68 78
  L 76 100
  L 82 90
  L 76 50
  C 74 42, 70 38, 64 36
  L 50 34
  Z
`;

function bandFor(hp, isDead) {
  if (isDead) return { label: 'Fallen', text: 'text-blood' };
  if (hp <= 9) return { label: 'Near death', text: 'text-blood' };
  if (hp <= 39) return { label: 'Bleeding', text: 'text-blood' };
  if (hp <= 69) return { label: 'Wounded', text: 'text-amber' };
  if (hp <= 99) return { label: 'Bruised', text: 'text-amber' };
  return { label: 'Whole', text: 'text-leyline' };
}

export function PlayerVitals() {
  const characters = useWorldStore((s) => s.characters);
  const playerName = usePlayerStore((s) => s.characterName);

  // Find the player by role first (canonical) — fall back to name match for
  // legacy/edge worlds where the DM emitted role=undefined but the name lines
  // up with the session's recorded character.
  let player = characters.find((c) => c?.role === 'player');
  if (!player && playerName) {
    player = characters.find((c) => c?.name === playerName);
  }

  // No player in either source → render a placeholder slot so the panel
  // visual hierarchy is stable across sessions (vs. the entire vitals box
  // appearing/disappearing). Aria-valuetext announces "Unknown" so screen
  // readers know the data isn't available rather than reading a default 100.
  const placeholder = !player;

  const rawHp = player?.health;
  // Missing health on a known player → 100 (DM-prompt rule), not 0. NaN /
  // non-finite → 100. Out-of-range → clamped. Order matters: the placeholder
  // case is handled separately so its render doesn't show "100/100 Whole."
  const hpInput = rawHp === undefined ? 100 : rawHp;
  const hp = Number.isFinite(hpInput)
    ? Math.max(0, Math.min(100, hpInput))
    : 100;

  const isDead = !placeholder && (player?.status === 'dead' || hp === 0);
  const band = placeholder
    ? { label: 'Unknown', text: 'text-dust' }
    : bandFor(hp, isDead);

  // Wash opacity scales smoothly with (100 - hp), capped at 0.85 so the
  // outline stays just visible even at 1 HP. On a "Fallen" player the wash
  // is a fixed dim-red 0.30 and the silhouette itself drops to 30% opacity
  // — together they read as "spent" without resorting to a slashed-X mark
  // (we may iterate this with Russell).
  const washOpacity = placeholder
    ? 0
    : isDead
    ? 0.3
    : Math.min(0.85, (100 - hp) / 100 * 0.95);
  const silhouetteOpacity = isDead ? 0.3 : 1;

  const ariaValueText = placeholder
    ? 'Unknown'
    : `${band.label} — ${hp}/100`;

  return (
    <div className="border-b border-border pb-4 mb-4">
      <h3 className="text-amber font-cinzel text-sm mb-2">VITALS</h3>
      <div className="flex items-center gap-3">
        <svg
          viewBox="0 0 100 180"
          className="h-24 w-auto shrink-0 text-ink"
          style={{ opacity: silhouetteOpacity, transition: 'opacity 300ms' }}
          role="meter"
          aria-label="Player vitals"
          aria-valuenow={placeholder ? 0 : hp}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={ariaValueText}
        >
          <defs>
            <clipPath id="vitals-body-clip">
              <ellipse cx="50" cy="22" rx="11" ry="12" />
              <path d={BODY_PATH} />
            </clipPath>
            <radialGradient id="vitals-damage" cx="50%" cy="55%" r="55%">
              <stop offset="0%" stopColor="#8c3a3a" />
              <stop offset="60%" stopColor="#c9973a" stopOpacity="0.5" />
              <stop offset="100%" stopColor="#c9973a" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Damage wash — clipped to the body so it never spills outside
              the silhouette. Opacity is the runtime mapping of HP loss. */}
          <rect
            x="0"
            y="0"
            width="100"
            height="180"
            fill="url(#vitals-damage)"
            opacity={washOpacity}
            clipPath="url(#vitals-body-clip)"
            style={{ transition: 'opacity 400ms' }}
          />

          {/* Visible outline — stroke only, same geometry as the clip. */}
          <g
            stroke="currentColor"
            strokeWidth="1.2"
            fill="none"
            strokeLinejoin="round"
            strokeLinecap="round"
          >
            <ellipse cx="50" cy="22" rx="11" ry="12" />
            <path d={BODY_PATH} />
          </g>
        </svg>

        <div className="flex-1 min-w-0">
          <div className={band.text + ' font-medium text-sm font-cinzel'}>
            {band.label}
          </div>
          <div className="text-dust text-xs mt-0.5">
            {placeholder ? '—' : `${hp}/100`}
          </div>
          {player?.name && !placeholder && (
            <div className="text-ink text-xs mt-1 truncate">{player.name}</div>
          )}
        </div>
      </div>
    </div>
  );
}
