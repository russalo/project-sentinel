import { useId } from 'react';
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
// in once authored). Each race is ONE entry of two path constants —
// { body, head } — and each constant is reused verbatim for BOTH the
// clip-path (vitality fill region) and the stroke outline, so fill and
// outline can never drift apart. All silhouettes span the same 180-unit
// canvas: short races (dwarf / halfling / gnome) read "short" through
// proportion — stocky torso, larger head ratio, short legs — not through
// absolute height, which keeps the bottom-anchored vitality-fill math
// identical across races.
//
// Heads are paths (not <ellipse>) so non-elliptical skulls — dwarf beard,
// gnome hat, orc tusks, tiefling horns, dragonborn snout — fit the same
// model. The human head path is the bezier equivalent of the original
// ellipse (cx 50, cy 22, rx 11, ry 12; kappa ≈ 0.5523).
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

const HUMAN_HEAD_PATH = `
  M 39 22
  C 39 15.4, 43.9 10, 50 10
  C 56.1 10, 61 15.4, 61 22
  C 61 28.6, 56.1 34, 50 34
  C 43.9 34, 39 28.6, 39 22
  Z
`.trim();

// Elf — slender: narrow shoulders, thin limbs, long legs (high crotch).
// Head sweeps to upward ear points.
const ELF_BODY_PATH = `
  M 38 36
  C 33 38, 30 42, 28 50
  L 23 88
  L 28 97
  L 35 76
  L 39 78
  L 39 100
  L 36 174
  L 44 176
  L 48 174
  L 48 110
  L 52 110
  L 52 174
  L 56 176
  L 64 174
  L 61 100
  L 61 78
  L 65 76
  L 72 97
  L 77 88
  L 72 50
  C 70 42, 67 38, 62 36
  L 50 34
  Z
`.trim();

const ELF_HEAD_PATH = `
  M 50 10
  C 55.5 10, 59 14, 59.5 19
  L 66 15
  L 60.5 25
  C 59.8 30.6, 55.5 34, 50 34
  C 44.5 34, 40.2 30.6, 39.5 25
  L 34 15
  L 40.5 19
  C 41 14, 44.5 10, 50 10
  Z
`.trim();

// Half-elf — human build, slightly slimmer; subtle ear points (own
// constants, not aliases, so each can drift in visual iteration).
const HALF_ELF_BODY_PATH = `
  M 37 36
  C 31 38, 27 42, 25 50
  L 20 89
  L 26 99
  L 33 77
  L 37 79
  L 37 101
  L 34 174
  L 43 176
  L 48 174
  L 48 111
  L 52 111
  L 52 174
  L 57 176
  L 66 174
  L 63 101
  L 63 79
  L 67 77
  L 74 99
  L 80 89
  L 75 50
  C 73 42, 69 38, 63 36
  L 50 34
  Z
`.trim();

const HALF_ELF_HEAD_PATH = `
  M 50 10
  C 56 10, 60.5 14.5, 61 21
  L 65 19
  L 61 26
  C 60 30.8, 55.5 34, 50 34
  C 44.5 34, 40 30.8, 39 26
  L 35 19
  L 39 21
  C 39.5 14.5, 44 10, 50 10
  Z
`.trim();

// Dwarf — stocky: broad shoulders, thick arms, short wide-stance legs.
// The head sits low with a beard wedge that overlaps the chest.
const DWARF_BODY_PATH = `
  M 32 54
  C 24 56, 19 61, 17 70
  L 13 102
  L 21 112
  L 28 90
  L 32 93
  L 32 118
  L 30 172
  L 42 176
  L 47 172
  L 47 128
  L 53 128
  L 53 172
  L 58 176
  L 70 172
  L 68 118
  L 68 93
  L 72 90
  L 79 112
  L 87 102
  L 83 70
  C 81 61, 76 56, 68 54
  L 50 52
  Z
`.trim();

const DWARF_HEAD_PATH = `
  M 50 22
  C 56 22, 61 26, 61 32
  L 61 40
  L 64 46
  L 58 60
  L 50 66
  L 42 60
  L 36 46
  L 39 40
  L 39 32
  C 39 26, 44 22, 50 22
  Z
`.trim();

// Halfling — small and round: big head ratio, round belly, short limbs.
const HALFLING_BODY_PATH = `
  M 39 58
  C 33 60, 29 64, 27 71
  L 24 100
  L 30 108
  L 35 92
  L 38 94
  C 34 104, 33 116, 35 126
  L 33 170
  L 46 176
  L 48 170
  L 48 138
  L 52 138
  L 52 170
  L 54 176
  L 67 170
  L 65 126
  C 67 116, 66 104, 62 94
  L 65 92
  L 70 108
  L 76 100
  L 73 71
  C 71 64, 67 60, 61 58
  L 50 56
  Z
`.trim();

const HALFLING_HEAD_PATH = `
  M 40 44
  C 40 38.5, 44.5 34, 50 34
  C 55.5 34, 60 38.5, 60 44
  C 60 49.5, 55.5 54, 50 54
  C 44.5 54, 40 49.5, 40 44
  Z
`.trim();

// Gnome — smallest build, largest head ratio, spindly limbs, and the
// pointed hat that carries the silhouette.
const GNOME_BODY_PATH = `
  M 40 52
  C 35 54, 32 58, 31 64
  L 27 96
  L 31 103
  L 36 84
  L 39 86
  L 39 104
  L 37 172
  L 44 176
  L 47 172
  L 47 120
  L 53 120
  L 53 172
  L 56 176
  L 63 172
  L 61 104
  L 61 86
  L 64 84
  L 69 103
  L 73 96
  L 69 64
  C 68 58, 65 54, 60 52
  L 50 50
  Z
`.trim();

const GNOME_HEAD_PATH = `
  M 50 6
  L 62 34
  L 60 34
  C 60 42, 55 46, 50 46
  C 45 46, 40 42, 40 34
  L 38 34
  Z
`.trim();

// Orc — hulking: massive hunched shoulders the head sinks between, long
// thick arms, short legs. Jaw carries two upward tusks.
const ORC_BODY_PATH = `
  M 34 34
  C 22 36, 15 42, 13 52
  L 10 96
  L 18 108
  L 26 84
  L 31 88
  L 33 112
  L 31 172
  L 43 176
  L 48 172
  L 48 124
  L 52 124
  L 52 172
  L 57 176
  L 69 172
  L 67 112
  L 69 88
  L 74 84
  L 82 108
  L 90 96
  L 87 52
  C 85 42, 78 36, 66 34
  L 50 30
  Z
`.trim();

const ORC_HEAD_PATH = `
  M 50 10
  C 57 10, 62 14, 62 20
  L 61 28
  L 59 26
  L 58 34
  L 54 31
  L 46 31
  L 42 34
  L 41 26
  L 39 28
  L 38 20
  C 38 14, 43 10, 50 10
  Z
`.trim();

// Half-orc — between human and orc: heavier arms, slight hunch, small
// tusk notches on a human-proportioned head.
const HALF_ORC_BODY_PATH = `
  M 35 36
  C 27 38, 22 43, 20 52
  L 16 92
  L 23 103
  L 30 80
  L 34 83
  L 34 106
  L 31 173
  L 42 176
  L 48 173
  L 48 116
  L 52 116
  L 52 173
  L 58 176
  L 69 173
  L 66 106
  L 66 83
  L 70 80
  L 77 103
  L 84 92
  L 80 52
  C 78 43, 73 38, 65 36
  L 50 32
  Z
`.trim();

const HALF_ORC_HEAD_PATH = `
  M 50 10
  C 56 10, 61 15, 61 22
  C 61 26, 60 29, 58 31
  L 57 26
  L 55 32
  C 52 34, 48 34, 45 32
  L 43 26
  L 42 31
  C 40 29, 39 26, 39 22
  C 39 15, 44 10, 50 10
  Z
`.trim();

// Tiefling — slim human build; horns curve up and back from the brow.
const TIEFLING_BODY_PATH = `
  M 38 36
  C 32 38, 28 42, 26 50
  L 21 88
  L 27 98
  L 34 77
  L 38 79
  L 38 101
  L 35 174
  L 44 176
  L 48 174
  L 48 111
  L 52 111
  L 52 174
  L 56 176
  L 65 174
  L 62 101
  L 62 79
  L 66 77
  L 73 98
  L 79 88
  L 74 50
  C 72 42, 68 38, 62 36
  L 50 34
  Z
`.trim();

const TIEFLING_HEAD_PATH = `
  M 37 3
  C 41 7, 43 11, 43 15
  C 45 12, 47 10, 50 10
  C 53 10, 55 12, 57 15
  C 57 11, 59 7, 63 3
  C 64 9, 63 14, 60 18
  C 60.7 19.3, 61 20.6, 61 22
  C 61 28.6, 56.1 34, 50 34
  C 43.9 34, 39 28.6, 39 22
  C 39 20.6, 39.3 19.3, 40 18
  C 37 14, 36 9, 37 3
  Z
`.trim();

// Dragonborn — bulky trunk and limbs, a tail sweeping from the left hip
// to the ground, and a wedge head tapering to a blunt snout.
const DRAGONBORN_BODY_PATH = `
  M 34 40
  C 25 42, 19 47, 17 56
  L 13 96
  L 20 107
  L 27 85
  L 32 88
  L 32 112
  L 30 172
  L 42 176
  L 47 172
  L 47 122
  L 53 122
  L 53 172
  L 60 176
  L 70 172
  L 68 130
  C 76 146, 81 158, 84 168
  L 91 164
  C 86 144, 78 128, 69 116
  L 68 112
  L 68 88
  L 73 85
  L 80 107
  L 87 96
  L 83 56
  C 81 47, 75 42, 66 40
  L 50 36
  Z
`.trim();

const DRAGONBORN_HEAD_PATH = `
  M 50 8
  C 58 8, 63 12, 63 18
  L 62 24
  L 57 36
  L 53 40
  L 47 40
  L 43 36
  L 38 24
  L 37 18
  C 37 12, 42 8, 50 8
  Z
`.trim();

const RACE_BODIES = {
  human: { body: HUMAN_BODY_PATH, head: HUMAN_HEAD_PATH },
  elf: { body: ELF_BODY_PATH, head: ELF_HEAD_PATH },
  'half-elf': { body: HALF_ELF_BODY_PATH, head: HALF_ELF_HEAD_PATH },
  dwarf: { body: DWARF_BODY_PATH, head: DWARF_HEAD_PATH },
  halfling: { body: HALFLING_BODY_PATH, head: HALFLING_HEAD_PATH },
  gnome: { body: GNOME_BODY_PATH, head: GNOME_HEAD_PATH },
  orc: { body: ORC_BODY_PATH, head: ORC_HEAD_PATH },
  'half-orc': { body: HALF_ORC_BODY_PATH, head: HALF_ORC_HEAD_PATH },
  tiefling: { body: TIEFLING_BODY_PATH, head: TIEFLING_HEAD_PATH },
  dragonborn: { body: DRAGONBORN_BODY_PATH, head: DRAGONBORN_HEAD_PATH },
};

function raceGeometryFor(race) {
  if (typeof race !== 'string') return RACE_BODIES.human;
  const key = race.trim().toLowerCase();
  // `hasOwnProperty.call` guard so a race string that matches an
  // Object.prototype member (`'constructor'`, `'toString'`, `'__proto__'`)
  // falls back to human instead of returning the prototype function
  // (which would land as a non-string `d` attribute on <path>).
  return Object.prototype.hasOwnProperty.call(RACE_BODIES, key)
    ? RACE_BODIES[key]
    : RACE_BODIES.human;
}

// The registered Fantasy roster, for the DEV-only gallery (DevVitalsGallery)
// and for tests that want to iterate every race without hand-copying keys.
// The react-refresh rule is disabled for this one export: hand-copying the
// roster into the gallery + tests is a drift hazard, and the only cost is
// slightly coarser HMR for this file during dev.
// eslint-disable-next-line react-refresh/only-export-components
export const FANTASY_RACES = Object.keys(RACE_BODIES);

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

// Resolve a player's HP into a 0-100 percentage (for the band + fill) plus
// the real current/max for the readout (RFC-0007). Prefers the four-stat
// sheet's hp; falls back to the legacy flat `health` (max 100) so a
// character without a sheet hp still renders. Tolerant of missing/NaN/
// out-of-range values: a known player with no usable HP reads as full.
function playerHp(player) {
  if (!player) return { hp: 0, hpCurrent: 0, hpMax: 0 };
  const sheet = player?.module_data?.character_sheet?.hp;
  if (
    sheet &&
    Number.isFinite(sheet.current) &&
    Number.isFinite(sheet.max) &&
    sheet.max > 0
  ) {
    const current = Math.max(0, Math.min(sheet.max, sheet.current));
    const pct = Math.round((current / sheet.max) * 100);
    return { hp: pct, hpCurrent: current, hpMax: sheet.max };
  }
  // Legacy flat health (0-100; default 100 when absent).
  const raw = player?.health;
  const input = raw === undefined ? 100 : raw;
  const flat = Number.isFinite(input) ? Math.max(0, Math.min(100, input)) : 100;
  return { hp: flat, hpCurrent: flat, hpMax: 100 };
}

// The silhouette SVG alone, props-driven and store-free, so the DEV-only
// gallery (/dev/vitals) can render every race × state combination on one
// page without touching the world store. PlayerVitals below is the only
// production consumer. The clip-path id comes from useId() (colons
// stripped — they're legal in a fragment but confuse devtools/CSS) so
// multiple instances on one page can't capture each other's clip.
export function VitalsSilhouette({
  race,
  hp,
  statusStr = '',
  placeholder = false,
  ariaValueText,
  className = 'h-20 sm:h-24 w-auto shrink-0 text-ink',
}) {
  const clipId = `vitals-body-clip-${useId().replace(/:/g, '')}`;
  const isDead = !placeholder && statusStr === 'dead';
  const isUnconscious = !placeholder && statusStr === 'unconscious';
  const vitalityHeight = vitalityHeightFor(hp, statusStr, placeholder);
  const vitalityY = SVG_HEIGHT - vitalityHeight; // anchor at the bottom
  const { body: bodyPath, head: headPath } = raceGeometryFor(race);

  // Silhouette dims slightly when dead (the body itself is replaced by the
  // skull pictogram — the dim applies to the whole pictogram for a "spent"
  // read). Unconscious keeps full opacity; the Zzz caption + empty body
  // do the work.
  const silhouetteOpacity = isDead ? 0.65 : 1;

  return (
    <svg
      viewBox="0 0 100 180"
      className={className}
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
            {/* Body first, head second — in BOTH the clip and the
                outline — so tests (and readers) can rely on path order:
                the first <path> in the SVG is always the body. */}
            <clipPath id={clipId}>
              <path d={bodyPath} />
              <path d={headPath} />
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
            clipPath={`url(#${clipId})`}
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
            <path d={bodyPath} />
            <path d={headPath} />
          </g>

          {/* Sleep marker — three Z glyphs above the head when
              status=unconscious. The silhouette is full-outline (no
              vitality fill); the Zzz is what signals the state. */}
          {isUnconscious && <ZzzCaption />}
        </>
      )}
    </svg>
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

  // HP source (RFC-0007): prefer the four-stat sheet's hp {current, max}
  // (variable max per character = Body × class factor). Fall back to the
  // legacy flat `health` 0-100 for characters not yet given a sheet hp
  // (created before RFC-0007 / not yet in combat) so existing worlds keep
  // rendering through the transition. `hp` below is always a 0-100
  // PERCENTAGE so the band + fill helpers (which expect 0-100) are unchanged;
  // `hpCurrent`/`hpMax` carry the real numbers for the readout.
  const { hp, hpCurrent, hpMax } = playerHp(player);

  // Status normalization — case- and whitespace-tolerant (DM emits "Dead",
  // "DEAD", " dead ", "Unconscious", "UNCONSCIOUS" etc.). Empty string
  // means "no status emitted yet."
  const statusStr =
    typeof player?.status === 'string' ? player.status.trim().toLowerCase() : '';

  const band = placeholder
    ? { label: 'Unknown', text: 'text-dust' }
    : bandFor(hp, statusStr);

  const ariaValueText = placeholder
    ? 'Unknown'
    : `${band.label} — ${hpCurrent}/${hpMax}`;

  return (
    <div className="border-b border-border pb-4 mb-4">
      <h3 className="text-amber font-cinzel text-sm mb-2">VITALS</h3>
      {/* Stack vertically on narrow screens, side-by-side at sm+. */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <VitalsSilhouette
          race={player?.race}
          hp={hp}
          statusStr={statusStr}
          placeholder={placeholder}
          ariaValueText={ariaValueText}
        />

        <div className="flex-1 min-w-0 text-center sm:text-left">
          <div className={band.text + ' font-medium text-sm font-cinzel whitespace-nowrap'}>
            {band.label}
          </div>
          <div className="text-dust text-xs mt-0.5 whitespace-nowrap">
            {placeholder ? '—' : `${hpCurrent}/${hpMax}`}
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
