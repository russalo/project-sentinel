import { useEffect, useRef } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { DeltaMessage } from './DeltaMessage';
import { NarrativeText } from './NarrativeText';

export function NarrativeScroll() {
  // Fine-grained selectors instead of full-store destructuring so the scroll
  // does NOT re-render on every command-bar keystroke (which writes to the
  // `input` slice). Without these selectors, every character typed in
  // CommandBar would trigger a full re-render of the message scroll. (gemini
  // HIGH on PR #112.)
  const messages = useChatStore((state) => state.messages);
  const streamBuffer = useChatStore((state) => state.streamBuffer);
  const systemLog = useChatStore((state) => state.systemLog);
  const activeView = useChatStore((state) => state.activeView);
  const setActiveView = useChatStore((state) => state.setActiveView);
  const unreadSystemLog = useChatStore((state) => state.unreadSystemLog);
  const scrollRef = useRef(null);
  const scrollLogRef = useRef(null);

  // Auto-scroll narrative to bottom when new content arrives
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamBuffer]);

  // Auto-scroll system log to bottom when new entries arrive
  useEffect(() => {
    if (scrollLogRef.current) {
      scrollLogRef.current.scrollTop = scrollLogRef.current.scrollHeight;
    }
  }, [systemLog]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Tab bar */}
      <div className="flex gap-1 px-4 pt-3 pb-0 border-b border-border shrink-0">
        <button
          onClick={() => setActiveView('narrative')}
          className={`px-3 py-2 lg:py-1 text-xs rounded-t transition-colors min-h-[2.75rem] lg:min-h-0 ${
            activeView === 'narrative'
              ? 'bg-codex text-amber border border-b-codex border-border -mb-px'
              : 'text-dust hover:text-amber'
          }`}
        >
          Narrative
        </button>
        <button
          onClick={() => setActiveView('system-log')}
          className={`px-3 py-2 lg:py-1 text-xs rounded-t transition-colors flex items-center gap-1.5 min-h-[2.75rem] lg:min-h-0 ${
            activeView === 'system-log'
              ? 'bg-codex text-amber border border-b-codex border-border -mb-px'
              : 'text-dust hover:text-amber'
          }`}
        >
          System Log
          {unreadSystemLog > 0 && (
            <span className="bg-amber text-void text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-tight">
              {unreadSystemLog}
            </span>
          )}
        </button>
      </div>

      {/* Narrative view — always mounted to preserve scroll position */}
      <div ref={scrollRef} className={`flex flex-col p-4 lg:p-6 gap-4 overflow-y-auto flex-1 ${activeView !== 'narrative' ? 'hidden' : ''}`}>
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-center text-dust">
            <div>
              <p className="text-2xl font-crimson mb-2">The world awaits.</p>
              <p className="text-sm">Start your adventure by typing an action.</p>
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className="animate-fade-in">
            {msg.type === 'dm' && (
              <div className="text-ink font-crimson leading-relaxed prose-narrative">
                <NarrativeText>{msg.content}</NarrativeText>
              </div>
            )}
            {msg.type === 'player' && (
              <div className="text-amber/80 text-sm italic">&gt; {msg.content}</div>
            )}
            {msg.type === 'system' && (
              <div className="text-ether text-xs font-mono">[{msg.content}]</div>
            )}
            {msg.type === 'delta' && (
              <div className="border-l-2 border-border pl-3 ml-1">
                <DeltaMessage delta={msg.delta} mode="inline" />
              </div>
            )}
          </div>
        ))}

        {streamBuffer && (
          <div className="text-ink font-crimson leading-relaxed prose-narrative animate-fade-in">
            <NarrativeText>{streamBuffer}</NarrativeText>
            <span className="cursor"></span>
          </div>
        )}
      </div>

      {/* System log view — always mounted to preserve scroll position */}
      <div ref={scrollLogRef} className={`flex flex-col p-4 gap-0 overflow-y-auto flex-1 ${activeView !== 'system-log' ? 'hidden' : ''}`}>
        {systemLog.length === 0 ? (
          <div className="flex items-center justify-center h-full text-center text-dust">
            <div>
              <p className="text-sm font-crimson mb-1">No events yet.</p>
              <p className="text-xs text-ether">World state changes will appear here after each turn.</p>
            </div>
          </div>
        ) : (
          systemLog.map((entry, i) => (
            <DeltaMessage
              key={entry.id}
              delta={entry.delta}
              mode="log"
              turnIdx={i + 1}
              timestamp={entry.timestamp}
            />
          ))
        )}
      </div>
    </div>
  );
}
