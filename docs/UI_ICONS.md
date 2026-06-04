# UI Icons & Visual Flourishes

Reference document for planned SVG icon and decorative element integration
across `apps/sentinel-ui/`. Updated: 2026-04-15.

**Icon library:** `lucide-react` — already installed, already used across six
files (e.g. `Menu`, `Share2`, `Users`, `BookOpen`, `Database`, `Send`, `Globe`,
`Plus`, `RefreshCw`, `Trash2`, `Download`, `ArrowLeft`, `X`, `Copy`). No new
packages needed for Tier 1 or Tier 2.

**Current state:** all panel section headers, entity list rows, and field labels
use Unicode glyphs (`◎ ▸ ◈ ◆ ✦`) or plain text. These are inconsistent and
hard to scan. Everything below is a planned replacement or addition.

---

## Design tokens (for reference)

| Token | Hex | Role |
|---|---|---|
| `void` | `#0d0d0f` | Main background |
| `codex` | `#16191f` | Panel / card backgrounds |
| `border` | `#2a2d35` | Dividers, inactive button fill |
| `ink` | `#e8e4d9` | Primary text |
| `dust` | `#8a8578` | Secondary text, placeholders |
| `amber` | `#c9973a` | Primary accent — player agency |
| `ether` | `#3a6a8c` | Secondary accent — lore / metadata |
| `leyline` | `#4a8c6f` | Success, calm states |
| `blood` | `#8c3a3a` | Danger, high tension |

Fonts: `crimson` (Crimson Pro, serif — narrative), `sans` (Inter — UI chrome),
`mono` (JetBrains Mono — system log), `cinzel` (Cinzel, serif — section titles).

---

## Tier 1 — Functional icons

These replace or augment text labels where a quick visual scan matters.
All are `lucide-react` imports at the sizes listed.

### Left panel section headers (`WorldStateDashboard`)

Currently plain uppercase text. Prepend icon + label.

| Section | Icon | Size | Class |
|---|---|---|---|
| Characters | `Users` | 14 | `text-dust` |
| Locations | `MapPin` | 14 | `text-dust` |
| Factions | `Shield` | 14 | `text-dust` |
| World Metrics | `Globe` | 14 | `text-dust` |

```jsx
import { Users, MapPin, Shield, Globe } from 'lucide-react';
<Users size={14} className="text-dust shrink-0" />
```

---

### Entity detail field labels (`EntityCard`)

Prepend a small icon to each field row so fields parse at a glance without
reading the label text. Icon + label text both stay — icon is decorative
reinforcement, not a replacement.

| Field | Icon | Size | Class |
|---|---|---|---|
| Health / hp | `Heart` | 12 | `text-dust` |
| Status | `Activity` | 12 | `text-dust` |
| Location / currentLocation | `MapPin` | 12 | `text-dust` |
| Role | `UserCheck` | 12 | `text-dust` |
| Class | `Swords` | 12 | `text-dust` |
| Level | `TrendingUp` | 12 | `text-dust` |
| Danger | `Flame` | 12 | `text-dust` |
| Power (faction) | `Zap` | 12 | `text-dust` |
| Relation (faction) | `Link` | 12 | `text-dust` |
| Alignment | `Compass` | 12 | `text-dust` |
| Rarity (item) | `Gem` | 12 | `text-dust` |
| Owner (item) | `User` | 12 | `text-dust` |
| Magical (item) | `Sparkles` | 12 | `text-amber` |
| Traits | `Tag` | 12 | `text-dust` |
| Description | `AlignLeft` | 12 | `text-dust` |

---

### Right panel tabs (`PanelRouter`)

Currently text-only buttons. Add icon before label. Active tab: icon
inherits `text-void` (amber bg). Inactive: icon inherits `text-ink`.

| Tab | Icon | Size |
|---|---|---|
| Codex | `BookOpen` | 14 |
| Inventory | `Backpack` | 14 |
| Quests | `Scroll` | 14 |
| Map | `Map` | 14 |

---

### Narrative tabs (`NarrativeScroll`)

Currently text-only tab buttons. Same treatment as PanelRouter tabs.

| Tab | Icon | Size |
|---|---|---|
| Narrative | `MessageCircle` | 14 |
| System Log | `ClipboardList` | 14 |

The existing unread badge on System Log stays; the icon sits to the left
of the label, badge to the right.

---

### Delta change indicators (`DeltaMessage`)

Currently `+`, `−`, `~` text chars in a monospace span. Replace with icons
at the same size. The icons hold their shape at `text-xs` where punctuation
blurs.

| Action | Icon | Size | Class |
|---|---|---|---|
| added | `CirclePlus` | 10 | `text-green-400 shrink-0` |
| removed | `CircleMinus` | 10 | `text-red-400 shrink-0` |
| changed | `ArrowLeftRight` | 10 | `text-amber shrink-0` |

Replace the existing `w-3 text-center font-mono` span with an icon component
using the same width (`w-3`) so column alignment is preserved.

---

## Tier 2 — Decorative / atmospheric

Lower priority. These add polish and breathing room without changing
information density.

### Empty states

Large dimmed icon above the existing placeholder text. Provides visual
weight without adding noise.

| Component | Condition | Icon | Size | Class |
|---|---|---|---|---|
| `NarrativeScroll` | `messages.length === 0` | `Scroll` | 48 | `text-dust/30` |
| `CodexPanel` | no characters/locations/factions | `Users` | 40 | `text-dust/30` |
| `InventoryPanel` | no items | `Backpack` | 40 | `text-dust/30` |
| System Log tab | `systemLog.length === 0` | `ClipboardList` | 40 | `text-dust/30` |

Centered in the existing empty-state `<div>`, above the text, no animation.

---

### Suggestion pills (planned feature)

When the pills feature ships, an optional leading tone icon on each pill
signals action type before the player reads the label. Only shown when
`tone` is present in the `suggestedActions` payload — no icon if tone is
omitted.

| Tone | Icon | Size | Class |
|---|---|---|---|
| `aggressive` | `Swords` | 12 | `text-blood` |
| `defensive` | `Shield` | 12 | `text-ether` |
| `clever` | `Lightbulb` | 12 | `text-amber` |
| `cautious` | `Eye` | 12 | `text-dust` |
| `social` | `MessageCircle` | 12 | `text-leyline` |
| (none / missing) | — | — | — |

---

### Inventory rarity badges

Currently colour-coded rarity text only. Add a small inline icon to the
right of the rarity label to reinforce the tier visually.

| Rarity | Icon | Size | Class |
|---|---|---|---|
| `common` | — | — | — |
| `uncommon` | `Gem` | 10 | `text-green-400` |
| `rare` | `Gem` | 10 | `text-blue-400` |
| `legendary` | `Star` | 10 | `text-amber` |
| `artifact` | `Sparkles` | 10 | `text-purple-400` |

---

## Tier 3 — Custom SVG

Only warranted where lucide doesn't have a thematic match. Low priority —
implement Tier 1 first.

| Use case | Description | Format |
|---|---|---|
| Roll button d20 | Proper d20 outline for a roll button (lucide's `Dices` is the generic fallback if one is ever needed). More distinctive for a tabletop RPG UI. | Inline `<svg>` React component, `currentColor`, viewBox `0 0 24 24`, 16px |
| Tension meter | 5-pip bar (some filled `blood`, some `border`) instead of a number. Shows tension 0–10 as a visual threat gauge. | Inline SVG, hardcode 5 segments, fill based on `tension / 2` | 
| Cinzel section ornament | Small decorative horizontal rule with a centred diamond glyph for Cinzel-font panel headings. | Pure CSS `::before`/`::after` with `border-border` + amber diamond, no SVG needed |

---

## Implementation notes

**Import pattern** — already established in `CommandBar.jsx` and `TopBar.jsx`:

```jsx
import { Heart, MapPin, Swords } from 'lucide-react';

// Inline with text label (field row):
<Heart size={12} className="text-dust shrink-0" />

// Standalone (section header):
<MapPin size={14} className="text-dust" />
```

**Sizing conventions:**
- `10px` — inline within `text-xs` delta rows
- `12px` — inline field labels in EntityCard rows
- `14px` — section headers, tab labels
- `40–48px` — empty-state centerpieces

**Custom SVGs** use Vite's `?react` transform if imported from a `.svg` file,
or inline JSX components. Use `currentColor` for stroke/fill so they respond
to Tailwind colour classes.

**No new packages required** for Tier 1 or Tier 2. Tier 3 custom SVGs are
hand-authored; no icon pack purchase or download needed.

---

## Status

| Tier | Status |
|---|---|
| Tier 1 — Functional | Planned — not yet implemented |
| Tier 2 — Decorative | Planned — not yet implemented |
| Tier 3 — Custom SVG | Speculative — implement Tier 1 first |
