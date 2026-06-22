import { useEffect, useState } from 'react';
import { usePersonaStore } from '../../stores/personaStore';
import { usePlayerStore } from '../../stores/playerStore';
import { useUIStore } from '../../stores/uiStore';
import { Link } from 'wouter';
import { Menu, Share2, Users, BookOpen, Database, MessageSquare, HelpCircle, Settings as SettingsIcon } from 'lucide-react';
import { PersonaSheet } from '../persona/PersonaSheet';
import { SeedShareModal } from '../seed/SeedShareModal';
import { StatusIndicator } from './StatusIndicator';
import { listMessages } from '../../api/systemMessages';

// NOTE: seedString is still a placeholder — world-seed persistence/sharing
// isn't built yet (see docs/BACKLOG.md § "World Identity & Multi-Session").
// The seed-share UI is intentionally kept as a visible reminder of that gap.
export function TopBar({ seedString = 'ABC-DEF-GHI-JKL' }) {
  const { personaName, mood, isLocked, availableMoods } = usePersonaStore();
  const worldName = usePlayerStore((s) => s.worldName) || 'The Shattered Expanse';
  const { focusMode, openMobilePanel, openSettings } = useUIStore();
  const messagesLastSeenAt = useUIStore((s) => s.messagesLastSeenAt);
  const [personaSheetOpen, setPersonaSheetOpen] = useState(false);
  const [seedModalOpen, setSeedModalOpen] = useState(false);
  const [hasUnreadMessages, setHasUnreadMessages] = useState(false);

  // Light the gear dot if any active message was published after the
  // tester's last drawer-open. Fetched once on mount; the SettingsDrawer
  // re-fetches + marks-seen on its own when opened. A failed fetch
  // silently leaves the dot off — failing closed is fine for an
  // ambient nudge.
  useEffect(() => {
    let cancelled = false;
    listMessages()
      .then((msgs) => {
        if (cancelled) return;
        if (!msgs || msgs.length === 0) {
          setHasUnreadMessages(false);
          return;
        }
        if (!messagesLastSeenAt) {
          setHasUnreadMessages(true);
          return;
        }
        const seenAt = new Date(messagesLastSeenAt).getTime();
        const unread = msgs.some(
          (m) => new Date(m.published_at).getTime() > seenAt,
        );
        setHasUnreadMessages(unread);
      })
      .catch(() => {
        // failing closed — no dot on network/API failure
      });
    return () => {
      cancelled = true;
    };
  }, [messagesLastSeenAt]);

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
          <h1 className="font-cinzel text-xl lg:text-2xl text-amber" data-testid="topbar-logo">⚔ SENTINEL</h1>
          <div className="hidden sm:block text-sm text-dust" data-testid="topbar-world-name">{worldName}</div>
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

          {/* Tester guide (RFC 0003) — in-app onboarding doc. If the icon
              cluster gets crowded, this entry can migrate into the settings
              drawer alongside Messages; the /guide route stays put. */}
          <Link
            href="/guide"
            className="text-dust hover:text-amber transition-colors"
            aria-label="Tester guide"
            title="Tester guide"
          >
            <HelpCircle size={18} />
          </Link>

          {/* Settings drawer — player-adjustable prefs (font size today; theme /
              density / audio later as testers ask). Opens via uiStore; the
              drawer itself is rendered in AppShell so it overlays the whole
              page rather than just the TopBar's bounding box.
              An unread system-message (RFC 0002) lights an amber dot on the
              gear so the tester notices without us nagging them with a banner. */}
          <button
            onClick={openSettings}
            className="relative text-dust hover:text-amber transition-colors"
            aria-label={hasUnreadMessages ? 'Settings (unread messages)' : 'Settings'}
            title={hasUnreadMessages ? 'Settings — unread messages' : 'Settings'}
          >
            <SettingsIcon size={18} />
            {hasUnreadMessages ? (
              <span
                data-testid="settings-unread-dot"
                aria-hidden="true"
                className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber ring-2 ring-codex"
              />
            ) : null}
          </button>

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
            data-testid="topbar-persona"
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
