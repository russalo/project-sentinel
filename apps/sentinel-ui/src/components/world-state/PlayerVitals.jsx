import { usePlayerStore } from '../../stores/playerStore';
import { useWorldStore } from '../../stores/worldStore';

// Player condition readout — an inked humanoid silhouette that **fills with
// blood from the feet up** as HP rises (Diablo health-orb idiom; RFC-0001,
// 2026-06-14). The wash is a single solid blood-red across the visible
// vitality region — no gradient, no per-band opacity stepping — and the
// rect's AREA carries the percentage of HP remaining. Two additional
// statuses are rendered as distinct pictograms: `unconscious` keeps the
// humanoid silhouette (vitality empty) and adds a "Zzz" caption above the
// head; `dead` replaces the body entirely with skull-and-crossbones.
//
// Data source: the DM emits the player as a character with role='player' +
// health + status on every world_update (verified against live sessions).
// We find them by role rather than name so a renamed character still lands.
//
// Fallbacks:
//  - no player character yet in worldStore (hydration race or a DM that
//    didn't emit on intro) → render an Unknown placeholder.
//  - missing health → assume 100 (DM-prompt rule: first appearance defaults
//    to 100; never invent a zero from absence).
//  - NaN / out-of-range → Number.isFinite + clamp to [0, 100], same pattern
//    WorldMetrics uses.

// Body geometry per race (Fantasy flagship; other genres' equivalents slot
// in once authored). Every entry currently points at HUMAN_BODY_PATH; per-
// race art is BACKLOG. The dispatch is real so per-race geometries land
// race-by-race without re-architecting.
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
`.trim();

const RACE_BODIES = {
  human: HUMAN_BODY_PATH,
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
  const key = race.trim().toLowerCase();
  // `hasOwnProperty.call` guard so a race string that matches an
  // Object.prototype member (`'constructor'`, `'toString'`, `'__proto__'`)
  // falls back to human instead of returning the prototype function
  // (which would land as a non-string `d` attribute on <path>).
  return Object.prototype.hasOwnProperty.call(RACE_BODIES, key)
    ? RACE_BODIES[key]
    : HUMAN_BODY_PATH;
}

// Band labels: derived at render time from (hp, statusStr) so the visible
// categorical reads consistently with the rendered pose. `status` overrides
// HP when set — e.g. status='unconscious' wins over HP=20.
function bandFor(hp, statusStr) {
  if (statusStr === 'dead') return { label: 'Dead', text: 'text-blood' };
  if (statusStr === 'unconscious') return { label: 'Unconscious', text: 'text-amber' };
  if (hp <= 0) return { label: 'Fallen', text: 'text-blood' };
  if (hp <= 9) return { label: 'Near death', text: 'text-blood' };
  if (hp <= 39) return { label: 'Bleeding', text: 'text-blood' };
  if (hp <= 69) return { label: 'Wounded', text: 'text-amber' };
  if (hp <= 99) return { label: 'Bruised', text: 'text-amber' };
  return { label: 'Whole', text: 'text-leyline' };
}

// Vitality fill height — Diablo orb idiom (RFC-0001, decision 1). Anchored
// at the bottom of the SVG; grows up as HP rises. At HP=100 the rect fills
// the full body; at HP=0 it's collapsed; on status flips (unconscious or
// dead) it's also 0 — the pose change carries the visual story instead.
//
// MIN_VITALITY_HEIGHT floor: at HP=1 a strict proportional value (1.8 SVG
// units) is invisible; we hold a sliver at the feet so the player can see
// they have SOMETHING left until HP literally hits 0 or status flips.
const SVG_HEIGHT = 180;
const MIN_VITALITY_HEIGHT = 12;
function vitalityHeightFor(hp, statusStr, placeholder) {
  if (placeholder) return 0;
  if (statusStr === 'dead' || statusStr === 'unconscious') return 0;
  if (hp <= 0) return 0;
  const proportional = (hp / 100) * SVG_HEIGHT;
  return Math.max(MIN_VITALITY_HEIGHT, proportional);
}

// Blood-palette token. Single solid color across the vitality region — no
// gradient (RFC-0001 decision 2). Matches the project's blood color
// elsewhere in the UI.
const BLOOD = '#8c3a3a';

// Skull-and-crossbones pictogram for status='dead' (RFC-0001 decision 3).
// Replaces the body silhouette entirely — no head ellipse, no body path, no
// vitality. Stroke-only to match the codex aesthetic; the eye sockets / nose
// / teeth use fill=currentColor so they inherit the parent SVG's text color.
// The skull is filled with the parchment-bg color so the bones don't show
// through where they pass behind it.
function SkullAndCrossbones() {
  return (
    <g
      data-testid="vitals-skull-crossbones"
      stroke="currentColor"
      strokeWidth="1.5"
      fill="none"
      strokeLinejoin="round"
      strokeLinecap="round"
    >
      {/* Crossbones — diagonal X behind the skull */}
      <line x1="20" y1="62" x2="80" y2="138" />
      <line x1="80" y1="62" x2="20" y2="138" />
      <circle cx="20" cy="62" r="5" />
      <circle cx="80" cy="62" r="5" />
      <circle cx="20" cy="138" r="5" />
      <circle cx="80" cy="138" r="5" />
      {/* Skull dome + jaw — filled with codex parchment so the bones don't
          bleed through where they pass behind. */}
      <path
        d="M 30 80 Q 30 50 50 50 Q 70 50 70 80 L 70 108 L 60 115 L 58 122 L 42 122 L 40 115 L 30 108 Z"
        fill="#0d0d0f"
      />
      {/* Eye sockets */}
      <ellipse cx="40" cy="80" rx="5" ry="6" fill="currentColor" stroke="none" />
      <ellipse cx="60" cy="80" rx="5" ry="6" fill="currentColor" stroke="none" />
      {/* Nose */}
      <path d="M 47 95 L 50 102 L 53 95 Z" fill="currentColor" stroke="none" />
      {/* Teeth — short vertical lines along the jaw */}
      <line x1="44" y1="111" x2="44" y2="120" />
      <line x1="48" y1="111" x2="48" y2="120" />
      <line x1="52" y1="111" x2="52" y2="120" />
      <line x1="56" y1="111" x2="56" y2="120" />
    </g>
  );
}

// Three "Z" glyphs ascending up-and-right from above the head — the
// universal "sleeping" cartoon convention (RFC-0001 decision 3). Rendered
// over the standard humanoid silhouette when status='unconscious'. Amber
// tone matches the band label color for unconscious.
function ZzzCaption() {
  return (
    <g data-testid="vitals-zzz-caption" fill="#c9973a" stroke="none">
      <text x="66" y="22" fontSize="14" fontFamily="Georgia, serif" fontWeight="bold">Z</text>
      <text x="77" y="13" fontSize="10" fontFamily="Georgia, serif" fontWeight="bold">z</text>
      <text x="85" y="6" fontSize="7" fontFamily="Georgia, serif" fontWeight="bold">z</text>
    </g>
  );
}

export function PlayerVitals() {
  const characters = useWorldStore((s) => s.characters);
  const playerName = usePlayerStore((s) => s.characterName);

  // Find the player. Priority order: (1) role=player AND name=playerName,
  // (2) name match alone, (3) any role=player.
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

  const placeholder = !player;

  // Missing health on a known player → 100. NaN / non-finite → 100.
  // Out-of-range → clamped.
  const rawHp = player?.health;
  const hpInput = rawHp === undefined ? 100 : rawHp;
  const hp = Number.isFinite(hpInput)
    ? Math.max(0, Math.min(100, hpInput))
    : 100;

  // Status normalization — case- and whitespace-tolerant (DM emits "Dead",
  // "DEAD", " dead ", "Unconscious", "UNCONSCIOUS" etc.). Empty string
  // means "no status emitted yet."
  const statusStr =
    typeof player?.status === 'string' ? player.status.trim().toLowerCase() : '';
  const isDead = !placeholder && statusStr === 'dead';
  const isUnconscious = !placeholder && statusStr === 'unconscious';

  const band = placeholder
    ? { label: 'Unknown', text: 'text-dust' }
    : bandFor(hp, statusStr);

  const vitalityHeight = vitalityHeightFor(hp, statusStr, placeholder);
  const vitalityY = SVG_HEIGHT - vitalityHeight; // anchor at the bottom
  const bodyPath = bodyPathFor(player?.race);

  // Silhouette dims slightly when dead (the body itself is replaced by the
  // skull pictogram — the dim applies to the whole pictogram for a "spent"
  // read). Unconscious keeps full opacity; the Zzz caption + empty body
  // do the work.
  const silhouetteOpacity = isDead ? 0.65 : 1;

  const ariaValueText = placeholder
    ? 'Unknown'
    : `${band.label} — ${hp}/100`;

  return (
    <div className="border-b border-border pb-4 mb-4">
      <h3 className="text-amber font-cinzel text-sm mb-2">VITALS</h3>
      {/* Stack vertically on narrow screens, side-by-side at sm+. */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <svg
          viewBox="0 0 100 180"
          className="h-20 sm:h-24 w-auto shrink-0 text-ink"
          style={{ opacity: silhouetteOpacity, transition: 'opacity 300ms' }}
          role="meter"
          aria-label="Player vitals"
          aria-valuenow={placeholder ? undefined : hp}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={ariaValueText}
        >
          {isDead ? (
            <SkullAndCrossbones />
          ) : (
            <>
              <defs>
                <clipPath id="vitals-body-clip">
                  <ellipse cx="50" cy="22" rx="11" ry="12" />
                  <path d={bodyPath} />
                </clipPath>
              </defs>

              {/* Vitality fill — solid blood, anchored at the bottom,
                  height + y move together as HP changes. `y` and `height`
                  live in the inline style object (not as XML attrs) so the
                  CSS transition actually fires — SVG presentation attributes
                  don't animate via CSS in Safari iOS. */}
              <rect
                data-testid="vitals-vitality-fill"
                x="0"
                width="100"
                fill={BLOOD}
                clipPath="url(#vitals-body-clip)"
                style={{
                  y: vitalityY,
                  height: vitalityHeight,
                  transition: 'y 400ms, height 400ms',
                }}
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

              {/* Sleep marker — three Z glyphs above the head when
                  status=unconscious. The silhouette is full-outline (no
                  vitality fill); the Zzz is what signals the state. */}
              {isUnconscious && <ZzzCaption />}
            </>
          )}
        </svg>

        <div className="flex-1 min-w-0 text-center sm:text-left">
          <div className={band.text + ' font-medium text-sm font-cinzel whitespace-nowrap'}>
            {band.label}
          </div>
          <div className="text-dust text-xs mt-0.5 whitespace-nowrap">
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
