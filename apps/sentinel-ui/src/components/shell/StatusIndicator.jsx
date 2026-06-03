import { useChatStore } from '../../stores/chatStore';

// Reflects the real turn state (Gemini-audit polish — the dot used to be a
// hardcoded fake "Connected"). Turns are one-shot SSE, so there's no persistent
// connection to report — instead: idle 'Ready', 'Streaming…' while a turn is in
// flight, and a 'Connection error' tint after a failed turn.
export function StatusIndicator() {
  const isStreaming = useChatStore((s) => s.isStreaming);
  const streamError = useChatStore((s) => s.streamError);

  const { dot, label } = streamError
    ? { dot: 'bg-blood', label: 'Connection error' }
    : isStreaming
      ? { dot: 'bg-amber animate-pulse-slow', label: 'Streaming…' }
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
