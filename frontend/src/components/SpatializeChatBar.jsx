import { useCallback, useState } from 'react';

// Bottom-centered generate control for SPATIALIZE (2026-08-03) -- mirrors
// JurorChatBar's exact position (bottom of the main content column, below
// the canvas) and structure. The placeholder doubles as the example prompt
// (ghosted until the user types), GENERATE is embedded in the bar itself,
// and an empty submit is valid (randomizes), so unlike JurorChatBar's "Ask"
// the button is never disabled just because the input is empty.
export default function SpatializeChatBar({ onGenerate, generating }) {
  const [input, setInput] = useState('');

  const handleGenerate = useCallback(async () => {
    if (generating) return;
    const message = input;
    setInput('');
    await onGenerate(message);
  }, [input, generating, onGenerate]);

  const handleKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleGenerate();
      }
    },
    [handleGenerate],
  );

  return (
    <div className="flex gap-2 p-2 border-t border-border bg-surface shrink-0">
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="e.g. a quiet shady park with water features -- or leave blank to randomize"
        disabled={generating}
        className="flex-1 bg-background border border-border font-mono-sm text-mono-sm px-3 py-2 focus:ring-0 focus:border-accent text-on-surface outline-none disabled:opacity-50 rounded"
      />
      <button
        onClick={handleGenerate}
        disabled={generating}
        className="px-4 py-2 bg-accent text-background font-mono-sm text-mono-sm font-bold uppercase tracking-widest rounded hover:brightness-110 transition-all active:scale-[0.98] disabled:opacity-50"
      >
        {generating ? '...' : 'GENERATE'}
      </button>
    </div>
  );
}
