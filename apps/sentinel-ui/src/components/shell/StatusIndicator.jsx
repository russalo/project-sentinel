import { useChatStore } from '../../stores/chatStore';

// Reflects the real turn state (Gemini-audit polish — the dot used to be a
// hardcoded fake "Connected"). Turns are one-shot SSE, so there's no persistent
// connection to report — instead: idle 'Ready', 'Streaming…' while a turn is in
// flight, and a 'Connection error' tint after a failed turn.
export function StatusIndicator() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamError = useChatStore((s) => s.streamError);
  const rollPending = useChatStore((s) => s.rollPending);

  // `rollPending` (a rolled-but-unresolved check awaiting the player's tap)
  // is NOT streaming — the DM isn't working, we're waiting on the player —
  // so it gets a distinct, steady (non-pulsing) state rather than reading
  // "Streaming…". Ordered below streamError but above isStreaming so an
  // in-flight error still wins; isStreaming only goes true once the player
  // resolves, by which point rollPending has cleared.
  const { dot, label } = streamError
    ? { dot: 'bg-blood', label: 'Connection error' }
    : isStreaming
      ? { dot: 'bg-amber animate-pulse-slow', label: 'Streaming…' }
      : rollPending
        ? { dot: 'bg-amber', label: 'Roll ready — resolve to continue' }
        : { dot: 'bg-leyline', label: 'Ready' };

  return (
    <div
      className="flex items-center gap-2 text-xs text-dust"
      role="status"
      aria-live="polite"
    >
      <div className={`w-2 h-2 rounded-full ${dot}`} />
      <span>{label}</span>
    </div>
  );
}
