import { useState, useEffect, useCallback } from 'react';
import { Link } from 'wouter';
import { Globe, Plus, Database, RefreshCw } from 'lucide-react';
import { apiClient } from '../api/client';

// The "my worlds" landing (ADR 0002 Slice 5). Lists provisioned worlds from
// GET /api/worlds (most-recently-played first); each resumes at /w/<worldId>.
// Replaces the bare /→/create redirect now that worlds are resumable.
export default function WorldList() {
  const [worlds, setWorlds] = useState(null); // null = loading
  const [error, setError] = useState(null);

  const fetchWorlds = useCallback(
    () =>
      apiClient
        .get('/worlds')
        .then((w) => {
          setWorlds(Array.isArray(w) ? w : []);
          setError(null);
        })
        .catch((e) => {
          setError(String(e));
          setWorlds([]);
        }),
    [],
  );

  useEffect(() => {
    fetchWorlds();
  }, [fetchWorlds]);

  return (
    <div className="min-h-screen bg-void text-ink p-6">
      <div className="max-w-3xl mx-auto">
        <header className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <Globe size={20} className="text-amber" /> Your Worlds
          </h1>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchWorlds}
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
          <div className="text-center py-16 border border-border rounded bg-codex">
            <p className="text-blood mb-4">Could not load worlds: {error}</p>
            <button
              onClick={fetchWorlds}
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
            {worlds.map((w) => (
              <li key={w.worldId}>
                <Link
                  href={`/w/${w.worldId}`}
                  className="block border border-border rounded bg-codex px-4 py-3 hover:border-amber transition-colors"
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
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
