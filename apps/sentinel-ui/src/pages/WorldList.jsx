import { useState, useEffect, useCallback } from 'react';
import { Link } from 'wouter';
import { Globe, Plus, Database, RefreshCw, Trash2 } from 'lucide-react';
import { apiClient } from '../api/client';

// The "my worlds" landing (ADR 0002 Slice 5). Lists provisioned worlds from
// GET /api/worlds (most-recently-played first); each resumes at /w/<worldId>.
// Replaces the bare /→/create redirect now that worlds are resumable.
export default function WorldList() {
  const [worlds, setWorlds] = useState(null); // null = loading
  const [error, setError] = useState(null);

  // Only sets state in async callbacks (no synchronous setState), so calling
  // it from the mount effect doesn't trip react-hooks/set-state-in-effect.
  // The synchronous loading/error reset lives in `refresh` (an event handler),
  // matching DataBrowser.
  const fetchWorlds = useCallback(
    () =>
      apiClient
        .get('/worlds')
        .then((w) => {
          // A 200 with a non-array body (e.g. a proxy's HTML/JSON error page)
          // is an error, not an empty account — surface it rather than render
          // the "No worlds yet" create CTA.
          if (!Array.isArray(w)) throw new Error('unexpected response shape');
          setWorlds(w);
          setError(null);
        })
        .catch((e) => {
          setError(String(e));
          setWorlds([]);
        }),
    [],
  );

  // Refresh/Retry: reset to loading + clear the stale error first (event
  // handler, so synchronous setState is fine), then refetch.
  const refresh = () => {
    setWorlds(null);
    setError(null);
    fetchWorlds();
  };

  // Hard delete (ADR 0002 Slice 5), gated behind a confirmation since it's
  // irreversible. On success, refresh the list so the world drops out.
  const handleDelete = async (w) => {
    const name = w.worldName || 'Unnamed World';
    if (!window.confirm(`Delete "${name}"? This permanently removes the world and cannot be undone.`)) {
      return;
    }
    try {
      await apiClient.delete(`/world/${w.worldId}`);
      refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    fetchWorlds();
  }, [fetchWorlds]);

  return (
    <div className="min-h-screen bg-void text-ink p-6">
      <div className="max-w-3xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <h1 className="font-cinzel text-2xl text-amber flex items-center gap-2">
            <Globe size={20} className="text-amber" /> Your Worlds
          </h1>
          <div className="flex items-center gap-3">
            <button
              onClick={refresh}
              aria-label="Refresh"
              className="text-dust hover:text-amber transition-colors"
            >
              <RefreshCw size={16} />
            </button>
            <Link
              href="/data"
              className="text-sm text-dust hover:text-amber flex items-center gap-1 transition-colors"
            >
              <Database size={14} /> Data
            </Link>
            <Link
              href="/create"
              className="text-sm bg-amber text-void rounded px-3 py-1.5 flex items-center gap-1 font-medium hover:opacity-90 transition-opacity"
            >
              <Plus size={14} /> New world
            </Link>
          </div>
        </header>

        {worlds === null && <p className="text-dust">Loading worlds…</p>}

        {/* Error is distinct from empty: a backend outage offers a Retry, not a
            "make a new world" CTA (which would just fail against the same down
            backend and misleads as if the account were simply empty). */}
        {worlds !== null && error && (
          <div className="text-center py-16 border border-blood/30 rounded bg-blood/10">
            <p className="text-blood mb-4">Could not load worlds: {error}</p>
            <button
              onClick={refresh}
              className="inline-flex items-center gap-1 border border-border rounded px-4 py-2 hover:border-amber transition-colors"
            >
              <RefreshCw size={16} /> Retry
            </button>
          </div>
        )}

        {worlds !== null && !error && worlds.length === 0 && (
          <div className="text-center py-16 border border-border rounded bg-codex">
            <p className="text-dust mb-4">No worlds yet.</p>
            <Link
              href="/create"
              className="inline-flex items-center gap-1 bg-amber text-void rounded px-4 py-2 font-medium hover:opacity-90 transition-opacity"
            >
              <Plus size={16} /> Begin a new world
            </Link>
          </div>
        )}

        {worlds !== null && !error && worlds.length > 0 && (
          <ul className="space-y-2">
            {worlds
              .filter((w) => w && typeof w === 'object' && w.worldId)
              .map((w) => (
                <li key={w.worldId} className="flex items-stretch gap-2">
                  <Link
                    href={`/w/${w.worldId}`}
                    className="flex-1 min-w-0 block border border-border rounded bg-codex px-4 py-3 hover:border-amber transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-amber"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-medium truncate">
                        {w.worldName || 'Unnamed World'}
                      </span>
                      <span className="text-xs text-dust whitespace-nowrap">
                        {w.turnCount} {w.turnCount === 1 ? 'turn' : 'turns'}
                      </span>
                    </div>
                    <div className="text-xs text-dust mt-1 truncate">
                      {[w.character, w.persona].filter(Boolean).join(' · ') || '—'}
                    </div>
                  </Link>
                  <button
                    onClick={() => handleDelete(w)}
                    aria-label={`Delete ${w.worldName || 'Unnamed World'}`}
                    className="px-3 border border-border rounded bg-codex text-dust hover:text-blood hover:border-blood transition-colors"
                  >
                    <Trash2 size={16} />
                  </button>
                </li>
              ))}
          </ul>
        )}
      </div>
    </div>
  );
}
