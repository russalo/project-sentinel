import { create } from 'zustand';

export const useUIStore = create((set) => ({
  // Panel collapse state
  leftPanelCollapsed: false,
  rightPanelCollapsed: false,
  toggleLeftPanel: () => set((state) => ({ leftPanelCollapsed: !state.leftPanelCollapsed })),
  toggleRightPanel: () => set((state) => ({ rightPanelCollapsed: !state.rightPanelCollapsed })),

  // Right panel active tab
  activeTab: 'codex', // 'codex', 'inventory', 'quests', 'map'
  setActiveTab: (tab) => set({ activeTab: tab }),

  // Selected entity for right-panel detail view
  // Stores { name, type } only — PanelRouter resolves the live entity from worldStore
  selectedEntity: null,
  setSelectedEntity: (entity, type) => set({ selectedEntity: { name: entity.name, type }, rightPanelCollapsed: false }),
  clearSelectedEntity: () => set({ selectedEntity: null }),

  // Focus mode (full narrative, no side panels)
  focusMode: false,
  toggleFocusMode: () => set((state) => ({ focusMode: !state.focusMode })),

  // Mobile panel drawer ('left' | 'right' | null)
  mobilePanelOpen: null,
  openMobilePanel: (side) => set({ mobilePanelOpen: side }),
  closeMobilePanel: () => set({ mobilePanelOpen: null }),
}));
