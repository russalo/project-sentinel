// AdminMessages — operator surface for RFC 0002 system messages.
//
// Lives at /admin/messages. Tailnet-only by design: Caddyfile 404s
// `/api/admin/*` on the public edge (tests/test_caddy_invariant.py), so even
// though the operator UI route is technically reachable from the public SPA
// bundle, every API call it makes returns 404 unless you're on tailnet.
// Russell 2026-06-14: "If easier route the admin inside tailnet" — topology IS
// the credential, no in-band auth.
//
// Layout: compose form on top, then a full table of every message (active +
// pinned + soft-deleted + expired) so the operator can edit, pin/unpin, or
// delete in place.

import { useCallback, useEffect, useState } from 'react';
import {
  listAllMessages,
  createMessage,
  updateMessage,
  deleteMessage,
} from '../api/systemMessages';

const CATEGORIES = ['info', 'warning', 'release', 'maintenance'];

function emptyDraft() {
  return {
    title: '',
    body: '',
    category: 'info',
    pinned: false,
    expires_at: '',
  };
}

function isExpired(message) {
  if (!message.expires_at) return false;
  const t = new Date(message.expires_at).getTime();
  if (Number.isNaN(t)) return false;
  return t < Date.now();
}

export default function AdminMessages() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [submitting, setSubmitting] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const msgs = await listAllMessages();
      setMessages(msgs);
      setError(null);
    } catch (err) {
      setError(err?.message || 'failed to load messages');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleCreate(e) {
    e.preventDefault();
    if (!draft.title.trim() || !draft.body.trim()) return;
    setSubmitting(true);
    try {
      await createMessage({
        title: draft.title.trim(),
        body: draft.body,
        category: draft.category,
        pinned: draft.pinned,
        expires_at: draft.expires_at ? draft.expires_at : null,
      });
      setDraft(emptyDraft());
      await refresh();
    } catch (err) {
      setError(err?.message || 'failed to create message');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTogglePin(message) {
    try {
      await updateMessage(message.id, { pinned: !message.pinned });
      await refresh();
    } catch (err) {
      setError(err?.message || 'failed to update message');
    }
  }

  async function handleDelete(message) {
    if (!confirm(`Delete "${message.title}"?`)) return;
    try {
      await deleteMessage(message.id);
      await refresh();
    } catch (err) {
      setError(err?.message || 'failed to delete message');
    }
  }

  function startEdit(message) {
    setEditingId(message.id);
    setEditDraft({
      title: message.title,
      body: message.body,
      category: message.category,
      pinned: message.pinned,
      expires_at: message.expires_at || '',
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditDraft(null);
  }

  async function saveEdit(message) {
    try {
      const patch = {
        title: editDraft.title,
        body: editDraft.body,
        category: editDraft.category,
        pinned: editDraft.pinned,
      };
      if (editDraft.expires_at) {
        patch.expires_at = editDraft.expires_at;
      } else if (message.expires_at) {
        patch.clear_expires_at = true;
      }
      await updateMessage(message.id, patch);
      cancelEdit();
      await refresh();
    } catch (err) {
      setError(err?.message || 'failed to update message');
    }
  }

  return (
    <div className="min-h-screen bg-void text-ink font-crimson p-4 lg:p-8">
      <header className="max-w-4xl mx-auto mb-6">
        <h1 className="font-cinzel text-2xl text-amber">System Messages</h1>
        <p className="text-sm text-dust mt-1">
          Operator broadcast channel for the alpha cohort. This UI is
          tailnet-only — public Caddy 404s <code>/api/admin/*</code>.
        </p>
      </header>

      {error ? (
        <div
          className="max-w-4xl mx-auto mb-4 p-2 border border-rose-400/60 text-rose-400 text-sm rounded"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <section className="max-w-4xl mx-auto mb-8 p-4 border border-border rounded bg-codex">
        <h2 className="font-cinzel text-lg text-amber mb-3">Compose</h2>
        <form onSubmit={handleCreate} className="flex flex-col gap-3">
          <div>
            <label className="block text-xs text-dust mb-1" htmlFor="msg-title">
              Title
            </label>
            <input
              id="msg-title"
              type="text"
              maxLength={200}
              required
              value={draft.title}
              onChange={(e) => setDraft({ ...draft, title: e.target.value })}
              className="w-full px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber"
            />
          </div>
          <div>
            <label className="block text-xs text-dust mb-1" htmlFor="msg-body">
              Body (markdown: *italic*, **bold**, [label](https://url))
            </label>
            <textarea
              id="msg-body"
              maxLength={4000}
              required
              rows={5}
              value={draft.body}
              onChange={(e) => setDraft({ ...draft, body: e.target.value })}
              className="w-full px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber font-mono text-sm"
            />
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="block text-xs text-dust mb-1" htmlFor="msg-cat">
                Category
              </label>
              <select
                id="msg-cat"
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                className="px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber"
              >
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-dust mb-1" htmlFor="msg-exp">
                Expires at (optional, ISO timestamp)
              </label>
              <input
                id="msg-exp"
                type="datetime-local"
                value={draft.expires_at}
                onChange={(e) => setDraft({ ...draft, expires_at: e.target.value })}
                className="px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={draft.pinned}
                onChange={(e) => setDraft({ ...draft, pinned: e.target.checked })}
              />
              Pinned
            </label>
            <button
              type="submit"
              disabled={submitting || !draft.title.trim() || !draft.body.trim()}
              className="ml-auto px-4 py-2 bg-amber text-void rounded font-semibold hover:bg-amber/90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? 'Posting…' : 'Post'}
            </button>
          </div>
        </form>
      </section>

      <section className="max-w-4xl mx-auto">
        <h2 className="font-cinzel text-lg text-amber mb-3">
          All messages {loading ? '· loading…' : `· ${messages.length}`}
        </h2>
        <div className="flex flex-col gap-3">
          {messages.length === 0 && !loading ? (
            <p className="text-sm text-ether italic">No messages yet.</p>
          ) : null}
          {messages.map((m) => {
            const expired = isExpired(m);
            const deleted = !!m.deleted_at;
            const editing = editingId === m.id;
            return (
              <article
                key={m.id}
                className={`p-3 border rounded ${
                  deleted
                    ? 'border-border bg-void/20 opacity-50'
                    : expired
                      ? 'border-border bg-void/40 opacity-70'
                      : 'border-border bg-codex'
                }`}
              >
                {editing ? (
                  <div className="flex flex-col gap-2">
                    <input
                      type="text"
                      value={editDraft.title}
                      onChange={(e) =>
                        setEditDraft({ ...editDraft, title: e.target.value })
                      }
                      className="px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber"
                    />
                    <textarea
                      rows={4}
                      value={editDraft.body}
                      onChange={(e) =>
                        setEditDraft({ ...editDraft, body: e.target.value })
                      }
                      className="px-2 py-1 bg-void border border-border rounded text-ink focus:outline-none focus:border-amber font-mono text-sm"
                    />
                    <div className="flex flex-wrap gap-3 items-center">
                      <select
                        value={editDraft.category}
                        onChange={(e) =>
                          setEditDraft({ ...editDraft, category: e.target.value })
                        }
                        className="px-2 py-1 bg-void border border-border rounded text-ink"
                      >
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                      <input
                        type="datetime-local"
                        value={editDraft.expires_at}
                        onChange={(e) =>
                          setEditDraft({
                            ...editDraft,
                            expires_at: e.target.value,
                          })
                        }
                        className="px-2 py-1 bg-void border border-border rounded text-ink"
                      />
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={editDraft.pinned}
                          onChange={(e) =>
                            setEditDraft({
                              ...editDraft,
                              pinned: e.target.checked,
                            })
                          }
                        />
                        Pinned
                      </label>
                      <button
                        type="button"
                        onClick={() => saveEdit(m)}
                        className="ml-auto px-3 py-1 bg-amber text-void rounded text-sm font-semibold"
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        onClick={cancelEdit}
                        className="px-3 py-1 border border-border rounded text-sm"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <header className="flex items-start gap-2 mb-1">
                      <h3 className="font-cinzel text-base text-amber flex-1">
                        {m.pinned ? <span aria-label="Pinned">📌 </span> : null}
                        {m.title}
                      </h3>
                      <span className="text-[10px] uppercase tracking-wide text-ether border border-border px-1.5 py-0.5 rounded">
                        {m.category}
                      </span>
                      {deleted ? (
                        <span className="text-[10px] uppercase tracking-wide text-rose-400 border border-rose-400/60 px-1.5 py-0.5 rounded">
                          Deleted
                        </span>
                      ) : expired ? (
                        <span className="text-[10px] uppercase tracking-wide text-ether border border-border px-1.5 py-0.5 rounded">
                          Expired
                        </span>
                      ) : null}
                    </header>
                    <div className="text-xs text-ether mb-2">
                      Published {m.published_at}
                      {m.expires_at ? ` · expires ${m.expires_at}` : ''}
                      {m.deleted_at ? ` · deleted ${m.deleted_at}` : ''}
                    </div>
                    <pre className="text-sm text-ink font-mono whitespace-pre-wrap break-words mb-3">
                      {m.body}
                    </pre>
                    {deleted ? null : (
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => startEdit(m)}
                          className="px-3 py-1 border border-border rounded text-sm hover:border-amber hover:text-amber"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleTogglePin(m)}
                          className="px-3 py-1 border border-border rounded text-sm hover:border-amber hover:text-amber"
                        >
                          {m.pinned ? 'Unpin' : 'Pin'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(m)}
                          className="px-3 py-1 border border-rose-400/60 text-rose-400 rounded text-sm hover:bg-rose-400/10"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </>
                )}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
