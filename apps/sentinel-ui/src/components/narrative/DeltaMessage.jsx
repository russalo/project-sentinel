/**
 * DeltaMessage — renders a structured world-state delta.
 *
 * Props:
 *   delta    {object}  — output of computeDelta()
 *   mode     {string}  — 'inline' (narrative scroll) | 'log' (system log tab)
 *   turnIdx  {number}  — optional, shown as "Turn N" label in log mode
 *   timestamp {Date}   — optional, shown in log mode
 */

const TYPE_LABEL = { characters: 'character', locations: 'location', factions: 'faction', items: 'item' };

const ACTION_ICON = { added: '+', removed: '−', changed: '~' };
const ACTION_COLOUR = {
  added:   'text-green-400',
  removed: 'text-red-400',
  changed: 'text-amber',
};

const FIELD_LABEL = {
  currentLocation: 'location',
  timeOfDay:       'time',
  weather:         'weather',
  tension:         'tension',
  health:          'hp',
  status:          'status',
  level:           'level',
  role:            'role',
  discovered:      'discovered',
  danger:          'danger',
  type:            'type',
  power:           'power',
  playerRelation:  'relation',
  alignment:       'alignment',
  ownedBy:         'owner',
  owned_by:        'owner',
  location:        'location',
  rarity:          'rarity',
};

function ChangeRow({ icon, colour, label, detail }) {
  return (
    <div className="flex gap-1.5 items-baseline leading-snug">
      <span className={`${colour} shrink-0 w-3 text-center font-mono`}>{icon}</span>
      <span className="text-ether shrink-0">{label}</span>
      {detail && <span className="text-ink/70">{detail}</span>}
    </div>
  );
}

function EntityLine({ entry, type }) {
  const icon   = ACTION_ICON[entry.action];
  const colour = ACTION_COLOUR[entry.action];
  const typeLabel = TYPE_LABEL[type] ?? type;

  if (entry.action === 'added') {
    const sub = entry.entity?.role ?? entry.entity?.type ?? entry.entity?.alignment ?? '';
    return (
      <ChangeRow icon={icon} colour={colour}
        label={entry.name}
        detail={sub ? `${typeLabel} · ${sub}` : typeLabel}
      />
    );
  }

  if (entry.action === 'removed') {
    return <ChangeRow icon={icon} colour={colour} label={entry.name} detail={typeLabel} />;
  }

  // changed
  const parts = entry.changes.map(c => {
    const label = FIELD_LABEL[c.field] ?? c.field;
    const from  = c.from ?? '—';
    const to    = c.to   ?? '—';
    return `${label} ${from}→${to}`;
  });
  return (
    <ChangeRow icon={icon} colour={colour}
      label={entry.name}
      detail={parts.join(' · ')}
    />
  );
}

export function DeltaMessage({ delta, mode = 'inline', turnIdx, timestamp }) {
  const isLog = mode === 'log';

  return (
    <div className={`text-xs font-mono ${isLog ? 'py-2 border-b border-border/40' : ''}`}>
      {isLog && (
        <div className="text-ether mb-1">
          {turnIdx != null ? `Turn ${turnIdx}` : ''}
          {timestamp ? ` · ${timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
        </div>
      )}

      {delta.world.map((w, i) => (
        <ChangeRow key={i} icon="~" colour="text-amber"
          label={FIELD_LABEL[w.field] ?? w.field}
          detail={`${w.from ?? '—'}→${w.to ?? '—'}`}
        />
      ))}

      {['characters', 'locations', 'factions', 'items'].flatMap(type =>
        (delta[type] ?? []).map((entry, i) => (
          <EntityLine key={`${type}-${i}`} entry={entry} type={type} />
        ))
      )}
    </div>
  );
}
