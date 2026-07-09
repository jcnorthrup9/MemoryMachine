const NAV_ITEMS = [
  { label: 'RECONSTRUCT', active: true },
  { label: 'ARCHIVE', active: false },
  { label: 'DIAGNOSTICS', active: false },
];

export default function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col h-full bg-surface-container-lowest border-r border-border w-64 shrink-0">
      <div className="px-6 py-4 border-b border-border mb-4">
        <div className="font-headline-md text-headline-md leading-none">PERSHING_SQ</div>
        <div className="font-mono-label text-mono-label text-accent uppercase mt-1">CANYON_ENGINE</div>
      </div>
      <nav className="flex-1">
        {NAV_ITEMS.map((item) => (
          <div
            key={item.label}
            className={`border-l-2 pl-4 py-3 flex items-center gap-3 font-mono-sm text-mono-sm uppercase tracking-wider cursor-pointer transition-colors ${
              item.active
                ? 'text-accent border-accent bg-surface-container-high'
                : 'text-on-surface-variant border-transparent hover:bg-surface-container hover:text-primary'
            }`}
          >
            {item.label}
          </div>
        ))}
      </nav>
    </aside>
  );
}
