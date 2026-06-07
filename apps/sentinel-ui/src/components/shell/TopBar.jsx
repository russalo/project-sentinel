import { useState } from 'react';
import { usePersonaStore } from '../../stores/personaStore';
import { usePlayerStore } from '../../stores/playerStore';
import { useUIStore } from '../../stores/uiStore';
import { Link } from 'wouter';
import { Menu, Share2, Users, BookOpen, Database, MessageSquare } from 'lucide-react';
import { PersonaSheet } from '../persona/PersonaSheet';
import { SeedShareModal } from '../seed/SeedShareModal';
import { StatusIndicator } from './StatusIndicator';

// NOTE: seedString is still a placeholder — world-seed persistence/sharing
// isn't built yet (see docs/BACKLOG.md § "World Identity & Multi-Session").
// The seed-share UI is intentionally kept as a visible reminder of that gap.
export function TopBar({ seedString = 'ABC-DEF-GHI-JKL' }) {
  const { personaName, mood, isLocked, availableMoods } = usePersonaStore();
  const worldName = usePlayerStore((s) => s.worldName) || 'The Shattered Expanse';
  const { focusMode, openMobilePanel } = useUIStore();
  const [personaSheetOpen, setPersonaSheetOpen] = useState(false);
  const [seedModalOpen, setSeedModalOpen] = useState(false);

  return (
    <>
      <header className="bg-codex border-b border-border px-4 lg:px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Mobile: left panel toggle */}
          <button
            className="lg:hidden text-ink hover:text-amber transition-colors p-1"
            onClick={() => openMobilePanel('left')}
            aria-label="Open world state"
          >
            <Users size={20} />
          </button>
          <h1 className="font-cinzel text-xl lg:text-2xl text-amber">⚔ SENTINEL</h1>
          <div className="hidden sm:block text-sm text-dust">{worldName}</div>
        </div>

        <div className="flex items-center gap-3 lg:gap-6">
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

          {/* Feedback form — tester reports go to <SENTINEL_FEEDBACK_ROOT>
              via POST /api/feedback. Available to all alpha testers (basic_auth
              gate already enforces who reaches this surface). See
              docs/ALPHA_FEEDBACK.md for the triage pipeline. */}
          <Link
            href="/feedback"
            className="text-dust hover:text-amber transition-colors"
            aria-label="Send feedback"
            title="Send feedback"
          >
            <MessageSquare size={18} />
          </Link>

          {/* Training-data browser */}
          <Link
            href="/data"
            className="text-dust hover:text-amber transition-colors"
            aria-label="Training data"
          >
            <Database size={18} />
          </Link>

          {/* Seed string — hidden on small screens */}
          <button
            onClick={() => setSeedModalOpen(true)}
            className="hidden sm:flex text-xs font-mono text-amber hover:text-amber/80 transition-colors items-center gap-1"
          >
            {seedString} <Share2 size={14} />
          </button>

          {/* Persona + mood */}
          <button
            onClick={() => setPersonaSheetOpen(true)}
            className="text-sm hover:text-amber transition-colors"
          >
            <span className="text-amber font-medium">{personaName}</span>
            <span className="hidden sm:inline text-dust mx-1">•</span>
            <span className="hidden sm:inline text-dust">{mood}</span>
            <span className="ml-1">
              {isLocked ? '🔒' : '▾'}
            </span>
          </button>

          {/* Mobile: right panel toggle */}
          <button
            className="lg:hidden text-ink hover:text-amber transition-colors p-1"
            onClick={() => openMobilePanel('right')}
            aria-label="Open codex"
          >
            <BookOpen size={20} />
          </button>

          <button className="hidden lg:block text-ink hover:text-amber transition-colors">
            <Menu size={20} />
          </button>
        </div>
      </header>

      <PersonaSheet open={personaSheetOpen} onClose={() => setPersonaSheetOpen(false)} moods={availableMoods} />
      <SeedShareModal open={seedModalOpen} onClose={() => setSeedModalOpen(false)} seed={seedString} worldName={worldName} />
    </>
  );
}
