export default function LogPanel({ entries }) {
  return (
    <div className="h-40 border-t border-border bg-surface-container-lowest flex flex-col shrink-0">
      <div className="px-4 py-2 border-b border-border flex justify-between items-center bg-surface-container">
        <span className="font-mono-label text-mono-label text-primary uppercase">rebuild_log</span>
        <span className="font-mono-label text-[10px] text-on-surface-variant">{entries.length} events</span>
      </div>
      <div className="flex-1 p-3 font-mono-sm text-mono-sm overflow-y-auto text-accent space-y-1 bg-[#050505]">
        {entries.length === 0 && (
          <div className="opacity-40">awaiting first rebuild...</div>
        )}
        {entries.map((e, i) => (
          <div key={i} className="flex gap-4">
            <span className="opacity-40">[{e.time}]</span>
            <span className={e.level === 'error' ? 'text-error' : e.level === 'warn' ? 'text-warning' : ''}>
              {e.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
