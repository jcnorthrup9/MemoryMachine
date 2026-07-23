const TABS = ['SPATIALIZE', 'RECONSTRUCT', 'ARCHIVE', 'DIAGNOSTICS'];

export default function Header({ activeTab, onSelectTab }) {
  return (
    <header className="bg-background text-primary border-b border-border flex justify-between items-center w-full px-container h-16 z-50 shrink-0">
      <div className="flex items-center gap-4">
        <span className="font-mono-label text-mono-label tracking-widest text-accent uppercase">
          MEMORY_MACHINE
        </span>
        <div className="h-4 w-[1px] bg-border mx-2" />
        <div className="flex flex-col leading-none">
          <span className="font-headline-md text-headline-md leading-none">PERSHING_SQ</span>
          <span className="font-mono-label text-mono-label text-accent uppercase mt-1">PERSHING_METABOLIZER</span>
        </div>
      </div>
      <nav className="hidden md:flex gap-6 h-full items-center">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => onSelectTab(tab)}
            className={`font-mono-sm text-mono-sm h-full flex items-center border-b-2 transition-colors ${
              activeTab === tab
                ? 'text-accent font-bold border-accent'
                : 'text-on-surface-variant border-transparent hover:text-accent'
            }`}
          >
            {tab}
          </button>
        ))}
      </nav>
    </header>
  );
}
