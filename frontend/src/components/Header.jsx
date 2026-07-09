export default function Header() {
  return (
    <header className="bg-background text-primary border-b border-border flex justify-between items-center w-full px-container h-16 z-50 shrink-0">
      <div className="flex items-center gap-4">
        <span className="font-mono-label text-mono-label tracking-widest text-accent uppercase">
          MEMORY_MACHINE
        </span>
        <div className="h-4 w-[1px] bg-border mx-2" />
        <span className="font-mono-sm text-mono-sm text-on-surface-variant">PERSHING_METABOLIZER</span>
      </div>
      <nav className="hidden md:flex gap-6 h-full items-center">
        <a className="text-accent font-bold font-mono-sm text-mono-sm h-full flex items-center border-b-2 border-accent" href="#">
          RECONSTRUCT
        </a>
        <a className="text-on-surface-variant font-mono-sm text-mono-sm h-full flex items-center border-b-2 border-transparent hover:text-accent transition-colors" href="#">
          ARCHIVE
        </a>
        <a className="text-on-surface-variant font-mono-sm text-mono-sm h-full flex items-center border-b-2 border-transparent hover:text-accent transition-colors" href="#">
          DIAGNOSTICS
        </a>
      </nav>
    </header>
  );
}
