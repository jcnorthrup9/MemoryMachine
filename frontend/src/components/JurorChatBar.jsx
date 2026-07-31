import { useCallback, useState } from 'react';

// Persistent single-line chat bar (not a modal) sitting just above LogPanel
// -- replies get logged into the same rebuild-log stream (App.jsx's log()),
// so the conversation reads inline with everything else already happening
// in the app instead of needing its own transcript UI.
export default function JurorChatBar({ onSend }) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);

  const handleSend = useCallback(async () => {
    const message = input.trim();
    if (!message || sending) return;
    setInput('');
    setSending(true);
    try {
      await onSend(message);
    } finally {
      setSending(false);
    }
  }, [input, sending, onSend]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex gap-2 p-2 border-t border-border bg-surface shrink-0">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about this design..."
        disabled={sending}
        className="flex-1 bg-background border border-border font-mono-sm text-mono-sm px-3 py-2 focus:ring-0 focus:border-accent text-on-surface outline-none disabled:opacity-50"
      />
      <button
        onClick={handleSend}
        disabled={sending || !input.trim()}
        className="px-4 py-2 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
      >
        {sending ? '...' : 'Ask'}
      </button>
    </div>
  );
}
