import { useUIStore } from '../../stores/uiStore';
import { useWorldStore } from '../../stores/worldStore';
import { CodexPanel } from './CodexPanel';
import { InventoryPanel } from './InventoryPanel';
import { EntityCard } from './EntityCard';

// Only tabs backed by real session state are listed. Quests and Map were
// removed (no data model yet) rather than shown as empty/fabricated panels.
const TABS = [
  { id: 'codex',     label: 'Codex',  component: CodexPanel },
  { id: 'inventory', label: 'Inv',    component: InventoryPanel },
];

const COLLECTIONS = {
  character: (s) => s.characters,
  location:  (s) => s.locations,
  faction:   (s) => s.factions,
  item:      (s) => s.items,
};

export function PanelRouter() {
  const { activeTab, setActiveTab, selectedEntity, clearSelectedEntity } = useUIStore();

  // Selector resolves only the specific entity needed — avoids full worldStore subscription
  const liveEntity = useWorldStore((s) => {
    if (!selectedEntity) return null;
    const collection = COLLECTIONS[selectedEntity.type]?.(s) ?? [];
    return collection.find(e => e.name === selectedEntity.name) ?? null;
  });

  if (selectedEntity) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-1 p-2 border-b border-border">
          <button
            onClick={clearSelectedEntity}
            className="px-3 py-1 text-xs rounded transition-colors bg-border text-ink hover:bg-border/80"
          >
            ← Back
          </button>
          <span className="text-xs text-ether ml-1 capitalize">{selectedEntity.type}</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {liveEntity
            ? <EntityCard entity={liveEntity} type={selectedEntity.type} />
            : <p className="p-4 text-xs text-ether">Entity no longer exists.</p>
          }
        </div>
      </div>
    );
  }

  const activeTabConfig = TABS.find(t => t.id === activeTab);
  const ActiveComponent = activeTabConfig?.component;

  return (
    <div className="flex flex-col h-full">
      {/* Tab buttons */}
      <div className="flex gap-1 p-2 border-b border-border">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              activeTab === tab.id
                ? 'bg-amber text-void'
                : 'bg-border text-ink hover:bg-border/80'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">
        {ActiveComponent && <ActiveComponent />}
      </div>
    </div>
  );
}
