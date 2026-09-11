import { VitalsSilhouette, FANTASY_RACES } from '../components/world-state/PlayerVitals';

// DEV-only gallery — every registered Fantasy race × a spread of vitals
// states on one page, so per-race silhouette art can be iterated visually
// without playing a session into each state. Mounted only when
// import.meta.env.DEV (see App.jsx); the route and this module are absent
// from production builds via the lazy() behind the same guard.
//
// Not linked from anywhere: visit /dev/vitals on the Vite dev server.

const STATES = [
  { label: 'Whole', hp: 100, statusStr: '' },
  { label: 'Wounded', hp: 55, statusStr: '' },
  { label: 'Near death', hp: 5, statusStr: '' },
  { label: 'Unconscious', hp: 20, statusStr: 'unconscious' },
  { label: 'Dead', hp: 0, statusStr: 'dead' },
];

export default function DevVitalsGallery() {
  return (
    <div className="min-h-screen bg-void text-ink p-6">
      <h1 className="text-amber font-cinzel text-lg mb-1">
        Vitals silhouette gallery (DEV)
      </h1>
      <p className="text-dust text-xs mb-6">
        {FANTASY_RACES.length} races × {STATES.length} states. Not part of any
        production route.
      </p>
      <div className="space-y-8">
        {FANTASY_RACES.map((race) => (
          <section key={race}>
            <h2 className="text-ink font-cinzel text-sm mb-2 capitalize">{race}</h2>
            <div className="flex flex-wrap gap-6">
              {STATES.map((state) => (
                <figure key={state.label} className="text-center">
                  <VitalsSilhouette
                    race={race}
                    hp={state.hp}
                    statusStr={state.statusStr}
                    ariaValueText={`${race} — ${state.label}`}
                    className="h-32 w-auto text-ink"
                  />
                  <figcaption className="text-dust text-[10px] mt-1">
                    {state.label}
                  </figcaption>
                </figure>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
