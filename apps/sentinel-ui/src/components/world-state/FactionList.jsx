import { useUIStore } from '../../stores/uiStore';

export function FactionList({ factions }) {
  const { setSelectedEntity } = useUIStore();

  return (
    <div>
      <h3 className="text-amber font-cinzel text-sm mb-2">▸ FACTIONS</h3>
      {factions.length === 0 ? (
        <p className="text-dust text-xs">Powers yet unseen...</p>
      ) : (
        <ul className="text-xs text-ink space-y-1">
          {factions.map((fac, i) => (
            <li
              key={fac.unique_id ?? fac.name ?? i}
              className="hover:text-amber cursor-pointer transition-colors animate-fade-in"
              onClick={() => setSelectedEntity(fac, 'faction')}
            >
              ▸ {fac.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
