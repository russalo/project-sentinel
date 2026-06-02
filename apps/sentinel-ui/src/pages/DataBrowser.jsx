import { useState, useEffect, useCallback } from 'react';
import { Link } from 'wouter';
import { Database, Download, ArrowLeft, RefreshCw } from 'lucide-react';
import { apiClient, API_BASE } from '../api/client';

// Read-only browser over recorded mock sessions (Phase 3 of training capture).
// Lists sessions from GET /api/sessions, shows a selected session's turns, and
// offers per-session downloads of the schema JSONL / chatlog (the same
// artifacts `just export-training-data` writes, served by the export endpoint).
export default function DataBrowser() {
  const [sessions, setSessions] = useState(null); // null = loading
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const fetchSessions = useCallback(
    () =>
      apiClient
        .get('/sessions')
        .then(setSessions)
        .catch((e) => {
          setError(String(e));
          setSessions([]);
        }),
    [],
  );

  // Initial load. State starts at null (loading); fetchSessions only sets
  // state in its async callbacks, so there's no synchronous setState here.
  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Refresh is an event handler, so the synchronous loading-reset is fine.
  const refresh = () => {
    setSessions(null);
    setError(null);
    fetchSessions();
  };

  const openSession = (id) => {
    setLoadingDetail(true);
    setSelected(null);
    apiClient
      .get(`/sessions/${id}`)
      .then(setSelected)
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingDetail(false));
  };

  const exportUrl = (id, format) =>
    `${API_BASE}/sessions/${id}/export?format=${format}`;

  return (
    <div className="min-h-screen bg-void text-ink p-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="font-cinzel text-2xl text-amber flex items-center gap-2">
          <Database size={22} /> Training Data
        </h1>
        <div className="flex items-center gap-4">
          <button
            onClick={refresh}
            className="text-dust hover:text-amber transition-colors"
            aria-label="Refresh sessions"
          >
            <RefreshCw size={16} />
          </button>
          <Link
            href="/"
            className="text-sm text-dust hover:text-amber flex items-center gap-1 transition-colors"
          >
            <ArrowLeft size={14} /> Back to game
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[20rem_1fr] gap-6">
        <aside className="bg-codex border border-border rounded p-3 h-fit">
          <div className="text-amber font-cinzel text-xs mb-3">RECORDED SESSIONS</div>
          {sessions === null && <p className="text-xs text-dust">Loading…</p>}
          {error && <p className="text-xs text-blood">{error}</p>}
          {sessions && sessions.length === 0 && !error && (
            <p className="text-xs text-dust">
              No recorded sessions yet. Play a world to record one.
            </p>
          )}
          <ul className="space-y-1">
            {(sessions || []).map((s) => (
              <li key={s.sessionId}>
                <button
                  onClick={() => openSession(s.sessionId)}
                  className={`w-full text-left px-2 py-2 rounded text-sm transition-colors ${
                    selected?.sessionId === s.sessionId
                      ? 'bg-amber text-void'
                      : 'hover:bg-border'
                  }`}
                >
                  <div className="font-medium truncate">{s.worldName || 'Untitled'}</div>
                  <div className="text-xs opacity-70 truncate">
                    {[s.persona, s.character].filter(Boolean).join(' · ') || '—'} ·{' '}
                    {s.turnCount} turn{s.turnCount === 1 ? '' : 's'}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="bg-codex border border-border rounded p-4 min-h-[60vh]">
          {!selected && !loadingDetail && (
            <p className="text-sm text-dust">
              Select a session to view its captured turns and export training data.
            </p>
          )}
          {loadingDetail && <p className="text-sm text-dust">Loading session…</p>}
          {selected && (
            <>
              <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
                <div>
                  <h2 className="font-cinzel text-lg text-amber">{selected.worldName}</h2>
                  <p className="text-xs text-dust">
                    {[selected.persona, selected.character].filter(Boolean).join(' · ')} ·{' '}
                    {selected.turns.length} turns · {selected.sessionId}
                  </p>
                </div>
                <div className="flex gap-2">
                  <a
                    href={exportUrl(selected.sessionId, 'schema')}
                    download
                    className="btn flex items-center gap-1.5 text-sm"
                  >
                    <Download size={14} /> Schema .jsonl
                  </a>
                  <a
                    href={exportUrl(selected.sessionId, 'chatlog')}
                    download
                    className="btn flex items-center gap-1.5 text-sm"
                  >
                    <Download size={14} /> Chatlog .md
                  </a>
                </div>
              </div>
              <ol className="space-y-4">
                {selected.turns.map((t, i) => (
                  <li key={t.id ?? i} className="border-b border-border pb-3 last:border-0">
                    <div className="text-xs text-amber/80 mb-1">Turn {t.turn_number ?? i}</div>
                    {t.player_action && (
                      <p className="text-sm text-dust italic mb-1">▸ {t.player_action}</p>
                    )}
                    <p className="text-sm whitespace-pre-wrap">{t.narrative}</p>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
