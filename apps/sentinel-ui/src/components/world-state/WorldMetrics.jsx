// Tension is the world's encounter pressure (0-10 int). The DM prompt
// (engine/prompts/dm.py § TENSION & ENCOUNTER PRESSURE) treats 0-3 as calm,
// 4-6 as off-balance, 7-8 as encounter-overdue, 9-10 as encounter-must.
// The meter renders that gradient so the player has an ambient cue of
// rising pressure without the DM having to say it explicitly.
function tensionTone(t) {
  if (t >= 9) return { fill: 'bg-blood', text: 'text-blood', label: 'Critical' };
  if (t >= 7) return { fill: 'bg-blood/80', text: 'text-blood', label: 'Overdue' };
  if (t >= 4) return { fill: 'bg-amber', text: 'text-amber', label: 'Off-balance' };
  return { fill: 'bg-leyline', text: 'text-leyline', label: 'Calm' };
}

export function WorldMetrics({ day, tension }) {
  const t = typeof tension === 'number' ? Math.max(0, Math.min(10, tension)) : 0;
  const tone = tensionTone(t);
  const widthPct = t * 10;

  return (
    <div className="border-t border-border pt-4 mt-4">
      <div className="text-xs text-dust space-y-3">
        <div><span className="text-amber">Day</span> {day} of 365</div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-amber">Tension</span>
            <span className={tone.text + ' font-medium'}>
              {tone.label} <span className="text-dust font-normal">({t}/10)</span>
            </span>
          </div>
          <div
            className="h-1.5 rounded-sm bg-border overflow-hidden"
            role="progressbar"
            aria-label="Tension"
            aria-valuenow={t}
            aria-valuemin={0}
            aria-valuemax={10}
          >
            <div
              className={`h-full ${tone.fill} transition-all duration-300`}
              style={{ width: `${widthPct}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
