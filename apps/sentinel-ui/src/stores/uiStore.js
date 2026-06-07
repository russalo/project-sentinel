import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

// Font-size enum: ordered smallest-to-largest. The order array doubles as the
// cycling map for A− / A+ button stepping (clamped at ends; greyed-out at
// min/max in the SettingsDrawer UI).
export const FONT_SIZES = ['small', 'normal', 'large', 'xlarge'];
export const FONT_SIZE_DEFAULT = 'normal';

// Map enum → Tailwind class. Applied to the narrative wrapper in
// NarrativeScroll.jsx (DM messages + streamBuffer) ONLY — chrome / pills /
// system log stay at chrome scale for legibility and hit-target reasons.
export const FONT_SIZE_CLASS = {
  small: 'text-sm',
  normal: 'text-base',
  large: 'text-lg',
  xlarge: 'text-xl',
};

export const useUIStore = create(
  // Persist a small subset of state to localStorage so player prefs survive
  // refresh / world switch. `partialize` whitelists the fields — ephemeral
  // panel state (collapse toggles, mobilePanelOpen) is intentionally NOT
  // persisted, since saving them creates surprising sticky layouts that the
  // player didn't ask for. Only the prefs that are explicit, deliberate
  // choices (font size, settings-drawer open state IS NOT one of those —
  // exclude it too) get persisted.
  persist(
    (set) => ({
      // Panel collapse state
      leftPanelCollapsed: false,
      rightPanelCollapsed: false,
      toggleLeftPanel: () => set((state) => ({ leftPanelCollapsed: !state.leftPanelCollapsed })),
      toggleRightPanel: () => set((state) => ({ rightPanelCollapsed: !state.rightPanelCollapsed })),

      // Right panel active tab
      activeTab: 'codex', // 'codex' | 'inventory'
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

      // Settings drawer open/closed — ephemeral, NOT persisted (re-open on
      // demand each session rather than spawning the drawer unexpectedly
      // after refresh).
      settingsOpen: false,
      openSettings: () => set({ settingsOpen: true }),
      closeSettings: () => set({ settingsOpen: false }),

      // Font size — first player-pref setting. Cycled via A− / A+ buttons in
      // SettingsDrawer; persisted so refresh keeps the tester's choice.
      fontSize: FONT_SIZE_DEFAULT,
      setFontSize: (size) => {
        if (!FONT_SIZES.includes(size)) return;
        set({ fontSize: size });
      },
      // Step ±1 within the FONT_SIZES array; clamps at ends (used by the
      // A− / A+ buttons in SettingsDrawer to keep state-transitions inside
      // the store rather than re-deriving in the component).
      stepFontSize: (delta) =>
        set((state) => {
          const i = FONT_SIZES.indexOf(state.fontSize);
          const next = Math.max(0, Math.min(FONT_SIZES.length - 1, i + delta));
          return { fontSize: FONT_SIZES[next] };
        }),
    }),
    {
      name: 'sentinel.uiPrefs',
      storage: createJSONStorage(() => localStorage),
      // Persist only the explicit player-prefs. Ephemeral UI state
      // (panel collapse, focusMode, mobilePanelOpen, settingsOpen,
      // selectedEntity, activeTab) is intentionally NOT persisted.
      partialize: (state) => ({ fontSize: state.fontSize }),
      // Version bump if/when the persisted shape changes — Zustand's
      // migration hook handles it. Today: nothing to migrate.
      version: 1,
    },
  ),
);
