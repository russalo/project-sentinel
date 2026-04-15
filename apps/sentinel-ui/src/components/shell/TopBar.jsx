import { useState } from 'react';
import { usePersonaStore } from '../../stores/personaStore';
import { useUIStore } from '../../stores/uiStore';
import { Menu, Share2 } from 'lucide-react';
import { PersonaSheet } from '../persona/PersonaSheet';
import { SeedShareModal } from '../seed/SeedShareModal';
import { StatusIndicator } from './StatusIndicator';

export function TopBar({ worldName = 'The Shattered Expanse', seedString = 'ABC-DEF-GHI-JKL' }) {
  const { personaName, mood, isLocked, availableMoods } = usePersonaStore();
  const { focusMode } = useUIStore();
  const [personaSheetOpen, setPersonaSheetOpen] = useState(false);
  const [seedModalOpen, setSeedModalOpen] = useState(false);

  return (
    <>
      <header className="bg-codex border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="font-cinzel text-2xl text-amber">⚔ SENTINEL</h1>
          <div className="text-sm text-dust">{worldName}</div>
        </div>

        <div className="flex items-center gap-6">
          {/* Focus mode indicator — only renders while focus mode is
              active. Tells the player they're in a degraded layout
              (side panels hidden) and how to get out. The keybinding
              itself is intentionally not advertised in the normal UI
              to keep the chrome quiet, but once it fires accidentally
              the indicator surfaces both the state AND the escape
              key in one place. */}
          {focusMode && (
            <div
              className="flex items-center gap-2 px-3 py-1 rounded border border-amber/60 bg-amber/10 text-xs"
              role="status"
              aria-label="Focus mode active. Press F to exit."
            >
              <span className="text-amber">●</span>
              <span className="text-amber font-medium uppercase tracking-wide">
                Focus Mode
              </span>
              <span className="text-dust">·</span>
              <span className="text-dust">
                press <kbd className="font-mono text-amber bg-void/40 px-1 rounded">F</kbd> to exit
              </span>
            </div>
          )}

          {/* Connection status */}
          <StatusIndicator />

          {/* Seed string */}
          <button
            onClick={() => setSeedModalOpen(true)}
            className="text-xs font-mono text-amber hover:text-amber/80 transition-colors flex items-center gap-1"
          >
            {seedString} <Share2 size={14} />
          </button>

          {/* Persona + mood */}
          <button
            onClick={() => setPersonaSheetOpen(true)}
            className="text-sm hover:text-amber transition-colors"
          >
            <span className="text-amber font-medium">{personaName}</span>
            <span className="text-dust mx-1">•</span>
            <span className="text-dust">{mood}</span>
            <span className="ml-2">
              {isLocked ? '🔒' : '▾'}
            </span>
          </button>

          <button className="text-ink hover:text-amber transition-colors">
            <Menu size={20} />
          </button>
        </div>
      </header>

      <PersonaSheet open={personaSheetOpen} onClose={() => setPersonaSheetOpen(false)} moods={availableMoods} />
      <SeedShareModal open={seedModalOpen} onClose={() => setSeedModalOpen(false)} seed={seedString} worldName={worldName} />
    </>
  );
}
