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

// Body geometry per race (Fantasy flagship; other genres' equivalents — Sci-Fi
// species, Cyberpunk frame, etc. — slot in here too once authored). Each entry
// is an SVG path that fills the silhouette body (used both as the clip-path
// region for the damage wash AND as the stroked visible outline). Single
// source of truth per race means the wash never escapes the outline.
//
// **Stub status (2026-06-12):** every race in this map currently points at
// HUMAN_BODY_PATH. The dispatch is real (PlayerVitals reads player.race and
// looks up the matching geometry), but the per-race art hasn't been drawn
// yet — so an elf, a dwarf, and a human all render the same shape today.
// Authoring real geometry per race is filed in docs/BACKLOG.md "Author
// race-specific silhouette geometries"; the dispatch here lets that work
// land race-by-race without re-architecting the component.
//
// The shared default is the humanoid Russell sees on the live alpha: covers
// shoulders → arms hanging at the sides → tapered torso → split legs.
const HUMAN_BODY_PATH = `
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

// Race → body path. Keys are lowercased so the lookup is case-insensitive
// against whatever spelling the DM emits ("Elf" vs "elf" vs "ELF"). Add a new
// race by authoring a path constant above and registering it here; everything
// else flows through automatically. Unknown races (any string not in this map)
// fall back to the human silhouette, so a fresh genre that emits "android"
// or "rigger" doesn't crash — it just renders the default until art lands.
const RACE_BODIES = {
  human: HUMAN_BODY_PATH,
  // Fantasy stubs — all human-shaped for now; per-race geometry is BACKLOG.
  elf: HUMAN_BODY_PATH,
  'half-elf': HUMAN_BODY_PATH,
  dwarf: HUMAN_BODY_PATH,
  halfling: HUMAN_BODY_PATH,
  gnome: HUMAN_BODY_PATH,
  orc: HUMAN_BODY_PATH,
  'half-orc': HUMAN_BODY_PATH,
  tiefling: HUMAN_BODY_PATH,
  dragonborn: HUMAN_BODY_PATH,
};

function bodyPathFor(race) {
  if (typeof race !== 'string') return HUMAN_BODY_PATH;
  return RACE_BODIES[race.trim().toLowerCase()] || HUMAN_BODY_PATH;
}

function bandFor(hp, isDead) {
  if (isDead) return { label: 'Fallen', text: 'text-blood' };
  if (hp <= 9) return { label: 'Near death', text: 'text-blood' };
  if (hp <= 39) return { label: 'Bleeding', text: 'text-blood' };
  if (hp <= 69) return { label: 'Wounded', text: 'text-amber' };
  if (hp <= 99) return { label: 'Bruised', text: 'text-amber' };
  return { label: 'Whole', text: 'text-leyline' };
}

// Wash opacity is stepped per band, not a smooth function of HP. The dark
// codex background eats subtle opacity — a smooth (100-hp)/100 curve
// produced ~10% wash at HP=90 (Bruised) which was effectively invisible
// against the parchment palette. Each band now has a floor that makes
// damage unambiguously legible at every level. (Reported by Russell
// 2026-06-12 looking at HP=90 Johnny.) Fallen is intentionally dimmer
// than "Near death" — the silhouette opacity also drops, the two together
// read as "spent" not "bleeding out."
//
// Module-scoped (closes over nothing) so it's not re-allocated per render
// — gemini-medium on PR #128 suggested an inline ternary, but a hoisted
// named function reads more clearly than a 6-deep `? :` chain.
function washOpacityFor(hp, isDead, placeholder) {
  if (placeholder) return 0;
  if (isDead) return 0.40;
  if (hp >= 100) return 0;       // Whole
  if (hp >= 70) return 0.30;     // Bruised
  if (hp >= 40) return 0.55;     // Wounded
  if (hp >= 10) return 0.75;     // Bleeding
  return 0.90;                    // Near death
}

export function PlayerVitals() {
  const characters = useWorldStore((s) => s.characters);
  const playerName = usePlayerStore((s) => s.characterName);

  // Find the player. Priority order, top to bottom:
  //   1. role=player AND name=playerName — the unambiguous match. This wins
  //      even when other role=player records exist, which is the codex-P2
  //      case from PR #127: the shared/legacy state path can leak multiple
  //      historical role=player entities into worldStore (the repo's
  //      data/state/core/entities/ already has several), and a plain
  //      `find(role=player)` would surface whichever happens to be first,
  //      potentially the wrong character for the active session.
  //   2. name match alone — covers the case where the DM emitted a player
  //      record without setting role.
  //   3. any role=player — last-resort fallback when playerName isn't set
  //      yet (early hydration race, or the placeholder path).
  // Order matters: only descend to (3) when nothing earlier matches.
  let player;
  if (playerName) {
    player = characters.find(
      (c) => c?.role === 'player' && c?.name === playerName,
    );
    if (!player) {
      player = characters.find((c) => c?.name === playerName);
    }
  }
  if (!player) {
    player = characters.find((c) => c?.role === 'player');
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

  const washOpacity = washOpacityFor(hp, isDead, placeholder);
  // Race-keyed body geometry — stubbed today (every known race resolves to
  // the human silhouette). When real per-race art lands, only the path
  // string in RACE_BODIES needs to change. Reads from player.race when set;
  // falls back to the human default otherwise.
  const bodyPath = bodyPathFor(player?.race);
  const silhouetteOpacity = isDead ? 0.3 : 1;

  const ariaValueText = placeholder
    ? 'Unknown'
    : `${band.label} — ${hp}/100`;

  return (
    <div className="border-b border-border pb-4 mb-4">
      <h3 className="text-amber font-cinzel text-sm mb-2">VITALS</h3>
      {/* Stack vertically on narrow screens — iPhone screenshot 2026-06-12
          showed the right column (band / HP / name) clipping off the screen
          edge because the world-state drawer is too tight for a side-by-side
          layout on mobile. `flex-col sm:flex-row` keeps the desktop look
          but centers the silhouette over the readout on phones. The text
          column also gets `text-center sm:text-left` so the labels track
          alignment with the stacking axis. */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <svg
          viewBox="0 0 100 180"
          className="h-24 w-auto shrink-0 text-ink"
          style={{ opacity: silhouetteOpacity, transition: 'opacity 300ms' }}
          role="meter"
          aria-label="Player vitals"
          // Per WAI-ARIA: when the current value is unknown, aria-valuenow
          // should be OMITTED, not set to 0 — a screen reader interprets
          // 0 here as "Fallen / 0 HP," which is exactly the opposite of
          // what "Unknown" means (gemini-medium on PR #127). Passing
          // undefined lets React drop the attribute entirely.
          aria-valuenow={placeholder ? undefined : hp}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={ariaValueText}
        >
          <defs>
            <clipPath id="vitals-body-clip">
              <ellipse cx="50" cy="22" rx="11" ry="12" />
              <path d={bodyPath} />
            </clipPath>
            {/* Damage gradient — solid blood at the core, fading to a
                still-saturated amber at the body edges (NOT to transparent
                — the wash should color the whole silhouette body so the
                damage is visible against the dark codex background). The
                rect-level `opacity` prop controls overall intensity per
                band; this gradient just gives the wash a hot-center,
                inked-bleed shape inside the silhouette. (Russell visual
                feedback 2026-06-12.) */}
            <radialGradient id="vitals-damage" cx="50%" cy="50%" r="65%">
              <stop offset="0%" stopColor="#8c3a3a" stopOpacity="1" />
              <stop offset="60%" stopColor="#8c3a3a" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#c9973a" stopOpacity="0.75" />
            </radialGradient>
          </defs>

          {/* Damage wash — clipped to the body so it never spills outside
              the silhouette. Opacity is the runtime mapping of HP loss. */}
          <rect
            data-testid="vitals-damage-wash"
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
            <path d={bodyPath} />
          </g>
        </svg>

        <div className="flex-1 min-w-0 text-center sm:text-left">
          <div className={band.text + ' font-medium text-sm font-cinzel'}>
            {band.label}
          </div>
          <div className="text-dust text-xs mt-0.5">
            {placeholder ? '—' : `${hp}/100`}
          </div>
          {player?.name && !placeholder && (
            <div className="text-ink text-xs mt-1 truncate max-w-full">
              {player.name}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
