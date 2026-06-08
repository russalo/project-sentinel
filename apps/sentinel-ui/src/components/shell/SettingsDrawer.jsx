// SettingsDrawer — slide-in sheet for player-adjustable prefs.
//
// Today: font-size only. Future home for theme, density, audio toggles, and
// any other prefs the alpha cohort asks for — designed as a drawer rather
// than inline TopBar controls so the chrome stays clean as more settings
// accumulate (Russell's UX call, 2026-06-07).
//
// Open/close from `useUIStore` so anything in the app can open the drawer
// (e.g., a deep-link to "/?settings" later). Today only the TopBar gear
// triggers it.

import { useEffect, useRef } from 'react';
import { X, AArrowDown, AArrowUp } from 'lucide-react';
import { useUIStore, FONT_SIZES } from '../../stores/uiStore';

const FONT_SIZE_LABELS = {
  small: 'Small',
  normal: 'Normal',
  large: 'Large',
  xlarge: 'Extra large',
};

export function SettingsDrawer() {
  const settingsOpen = useUIStore((s) => s.settingsOpen);
  const closeSettings = useUIStore((s) => s.closeSettings);
  const fontSize = useUIStore((s) => s.fontSize);
  const stepFontSize = useUIStore((s) => s.stepFontSize);
  const drawerRef = useRef(null);

  // Focus management when drawer opens: capture previously-focused element
  // (the gear-icon button by default), move focus into the drawer container,
  // restore the prior focus on close. Standard WAI-ARIA modal pattern.
  // (gemini medium on PR #120 re-review.)
  useEffect(() => {
    if (settingsOpen) {
      const previouslyFocused = document.activeElement;
      drawerRef.current?.focus();
      return () => {
        previouslyFocused?.focus?.();
      };
    }
  }, [settingsOpen]);

  // Rescue focus back to the drawer container if the currently-focused element
  // becomes disabled (e.g., A+ button greys out when fontSize hits xlarge,
  // browser would otherwise drop focus to <body>). Pairs with the focus trap
  // below.
  useEffect(() => {
    if (settingsOpen && document.activeElement?.disabled) {
      drawerRef.current?.focus();
    }
  }, [fontSize, settingsOpen]);

  // Escape-to-close + focus trap inside the drawer. Tab/Shift-Tab cycles
  // within the drawer's focusable descendants; can't escape into the
  // background page. Only registers while open (no leaked global listener
  // when closed). (gemini medium on PR #120 — original + re-review.)
  useEffect(() => {
    if (!settingsOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        closeSettings();
        return;
      }
      if (e.key === 'Tab') {
        const focusable = Array.from(
          drawerRef.current?.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ) || [],
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          last.focus();
          e.preventDefault();
        } else if (!e.shiftKey && document.activeElement === last) {
          first.focus();
          e.preventDefault();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [settingsOpen, closeSettings]);

  const idx = FONT_SIZES.indexOf(fontSize);
  const atMin = idx === 0;
  const atMax = idx === FONT_SIZES.length - 1;

  // Drawer is always mounted so the slide animation works both directions;
  // visibility/pointer-events gate keeps it from intercepting taps when closed.
  return (
    <>
      {/* Backdrop — tap-outside-to-close. Always mounted; fades in. */}
      <div
        className={`fixed inset-0 z-40 bg-void/70 transition-opacity duration-200 ${
          settingsOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        onClick={closeSettings}
        aria-hidden={!settingsOpen}
      />

      {/* The drawer itself — slides in from the right on desktop, full-width on
          mobile. The `inert` attribute (when closed) removes its descendants
          from the tab order AND hides them from screen readers — without it,
          keyboard users tab into invisible Close + A−/A+ buttons before
          opening Settings. Pairs with aria-hidden for assistive-tech support.
          (gemini medium + codex P2 on PR #120.) */}
      <aside
        ref={drawerRef}
        tabIndex={-1}
        className={`fixed top-0 right-0 z-50 h-full w-full sm:w-96 bg-codex border-l border-border shadow-2xl transform transition-transform duration-200 flex flex-col outline-none ${
          settingsOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
        role="dialog"
        aria-label="Settings"
        aria-hidden={!settingsOpen}
        inert={!settingsOpen}
      >
        <header className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="font-cinzel text-lg text-amber">Settings</h2>
          <button
            onClick={closeSettings}
            className="text-dust hover:text-amber transition-colors p-1"
            aria-label="Close settings"
          >
            <X size={20} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {/* Font size — A− / A+ pair stepping through FONT_SIZES. The current
              size label sits between the buttons so the player sees both the
              control affordance and its current value. */}
          <section className="flex flex-col gap-2">
            <div className="text-sm text-dust">Narrative font size</div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => stepFontSize(-1)}
                disabled={atMin}
                className="px-3 py-2 rounded border border-border text-ink hover:border-amber hover:text-amber transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:text-ink"
                aria-label="Decrease font size"
                title="Decrease font size"
              >
                <AArrowDown size={18} />
              </button>
              <div
                className="flex-1 text-center text-amber font-crimson"
                aria-live="polite"
              >
                {FONT_SIZE_LABELS[fontSize]}
              </div>
              <button
                onClick={() => stepFontSize(1)}
                disabled={atMax}
                className="px-3 py-2 rounded border border-border text-ink hover:border-amber hover:text-amber transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:text-ink"
                aria-label="Increase font size"
                title="Increase font size"
              >
                <AArrowUp size={18} />
              </button>
            </div>
            <p className="text-xs text-ether">
              Applies to the DM narrative text. Chrome and UI controls stay at
              their default size for legibility.
            </p>
          </section>

          {/* Placeholder for future settings — theme, density, audio, etc.
              Don't add them speculatively; add when a tester asks for one. */}
        </div>
      </aside>
    </>
  );
}
