import { useWorldStore } from '../../stores/worldStore';
import { useUIStore } from '../../stores/uiStore';
import { usePlayerStore } from '../../stores/playerStore';

const RARITY_COLOUR = {
  common:    'text-ink',
  uncommon:  'text-green-400',
  rare:      'text-blue-400',
  legendary: 'text-amber',
  artifact:  'text-purple-400',
};

export function InventoryPanel() {
  const items = useWorldStore((s) => s.items);
  const { setSelectedEntity } = useUIStore();
  const playerName = usePlayerStore((s) => s.characterName);

  // Player-owned items first, then world items (unowned / location-placed)
  const carried = items.filter(i => i.ownedBy && i.ownedBy === playerName);
  const world   = items.filter(i => !i.ownedBy || i.ownedBy !== playerName);

  if (items.length === 0) {
    return (
      <div className="p-4 text-sm text-dust">
        <div className="text-amber font-cinzel text-xs mb-3">INVENTORY</div>
        <p className="text-xs mb-2">You carry nothing yet.</p>
        <p className="text-xs text-ether">Items will appear here as you acquire them.</p>
      </div>
    );
  }

  const ItemRow = ({ item }) => (
    <li
      className={`hover:text-amber cursor-pointer transition-colors text-xs flex gap-1.5 items-baseline ${RARITY_COLOUR[item.rarity] ?? 'text-ink'}`}
      onClick={() => setSelectedEntity(item, 'item')}
    >
      <span className="text-ether">◆</span>
      <span>{item.name}</span>
      {item.magical && <span className="text-ether ml-1">✦</span>}
      <span className="text-ether ml-auto shrink-0">{item.type}</span>
    </li>
  );

  return (
    <div className="p-4 text-sm">
      <div className="text-amber font-cinzel text-xs mb-3">INVENTORY</div>

      {carried.length > 0 && (
        <div className="mb-4">
          <div className="text-ether text-xs mb-1.5 uppercase tracking-wide">Carried</div>
          <ul className="space-y-1.5">
            {carried.map((item, i) => <ItemRow key={item.name ?? i} item={item} />)}
          </ul>
        </div>
      )}

      {world.length > 0 && (
        <div className="mb-4">
          <div className="text-ether text-xs mb-1.5 uppercase tracking-wide">In the World</div>
          <ul className="space-y-1.5">
            {world.map((item, i) => <ItemRow key={item.name ?? i} item={item} />)}
          </ul>
        </div>
      )}
    </div>
  );
}
