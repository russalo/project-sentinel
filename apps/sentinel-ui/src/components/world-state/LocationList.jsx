import { useUIStore } from '../../stores/uiStore';

export function LocationList({ locations }) {
  const { setSelectedEntity } = useUIStore();

  return (
    <div>
      <h3 className="text-amber font-cinzel text-sm mb-2">LOCATIONS</h3>
      {locations.length === 0 ? (
        <p className="text-dust text-xs">Unknown territories ahead...</p>
      ) : (
        <ul className="text-xs text-ink space-y-1">
          {locations.map((loc, i) => (
            <li
              key={loc.unique_id ?? loc.name ?? i}
              className="hover:text-amber cursor-pointer transition-colors animate-fade-in"
              onClick={() => setSelectedEntity(loc, 'location')}
            >
              ▸ {loc.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
