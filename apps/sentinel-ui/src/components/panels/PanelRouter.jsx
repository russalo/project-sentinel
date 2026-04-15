import { useUIStore } from '../../stores/uiStore';
import { CodexPanel } from './CodexPanel';
import { InventoryPanel } from './InventoryPanel';
import { QuestLogPanel } from './QuestLogPanel';
import { MapPanel } from './MapPanel';
import { EntityCard } from './EntityCard';

const TABS = [
  { id: 'codex',     label: 'Codex',  component: CodexPanel },
  { id: 'inventory', label: 'Inv',    component: InventoryPanel },
  { id: 'quests',    label: 'Quests', component: QuestLogPanel },
  { id: 'map',       label: 'Map',    component: MapPanel },
];

export function PanelRouter() {
  const { activeTab, setActiveTab, selectedEntity, clearSelectedEntity } = useUIStore();

  // Entity detail view overrides normal tab content
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
          <EntityCard entity={selectedEntity.entity} type={selectedEntity.type} />
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
