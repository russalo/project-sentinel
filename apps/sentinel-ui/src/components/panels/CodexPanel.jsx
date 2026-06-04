import { useWorldStore } from '../../stores/worldStore';
import { useUIStore } from '../../stores/uiStore';
import codexHeader from '../../assets/generated/codex-header.webp';

// A4 illuminated-manuscript banner: ornate filigree across the top, dark lower
// band the title sits on (the image was generated with that empty dark strip
// for exactly this). Shared by both panel states.
function CodexHeader() {
  return (
    <div
      className="relative h-20 w-full bg-cover bg-center flex items-end px-4 pb-2"
      style={{ backgroundImage: `url(${codexHeader})` }}
    >
      <span className="text-amber font-cinzel text-xs tracking-wide drop-shadow-[0_1px_3px_rgba(0,0,0,0.9)]">
        DISCOVERED ENTITIES
      </span>
    </div>
  );
}

function EntityRow({ icon, entity, type, label, onSelect }) {
  return (
    <li
      className="hover:text-amber cursor-pointer transition-colors text-xs flex gap-1.5 items-baseline"
      onClick={() => onSelect(entity, type)}
    >
      <span className="text-ether">{icon}</span>
      <span>{entity.name}</span>
      {label && <span className="text-ether ml-auto shrink-0">{label}</span>}
    </li>
  );
}

export function CodexPanel() {
  const { characters, locations, factions } = useWorldStore();
  const { setSelectedEntity } = useUIStore();

  const total = characters.length + locations.length + factions.length;

  if (total === 0) {
    return (
      <div className="text-sm text-dust">
        <CodexHeader />
        <div className="px-4 pb-4">
          <p className="text-xs mb-2">No discoveries yet.</p>
          <p className="text-xs text-ether">As you explore, locations, NPCs, and factions will appear here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="text-sm">
      <CodexHeader />
      <div className="px-4 pb-4">
      {characters.length > 0 && (
        <div className="mb-4">
          <div className="text-ether text-xs mb-1.5 uppercase tracking-wide">Characters</div>
          <ul className="space-y-1.5 text-ink">
            {characters.map((c, i) => (
              <EntityRow
                key={c.unique_id ?? c.name ?? i}
                entity={c}
                type="character"
                icon="◎"
                label={c.role}
                onSelect={setSelectedEntity}
              />
            ))}
          </ul>
        </div>
      )}

      {locations.length > 0 && (
        <div className="mb-4">
          <div className="text-ether text-xs mb-1.5 uppercase tracking-wide">Locations</div>
          <ul className="space-y-1.5 text-ink">
            {locations.map((l, i) => (
              <EntityRow
                key={l.unique_id ?? l.name ?? i}
                entity={l}
                type="location"
                icon="▸"
                label={l.type}
                onSelect={setSelectedEntity}
              />
            ))}
          </ul>
        </div>
      )}

      {factions.length > 0 && (
        <div className="mb-4">
          <div className="text-ether text-xs mb-1.5 uppercase tracking-wide">Factions</div>
          <ul className="space-y-1.5 text-ink">
            {factions.map((f, i) => (
              <EntityRow
                key={f.unique_id ?? f.name ?? i}
                entity={f}
                type="faction"
                icon="◈"
                label={f.alignment}
                onSelect={setSelectedEntity}
              />
            ))}
          </ul>
        </div>
      )}
      </div>
    </div>
  );
}
