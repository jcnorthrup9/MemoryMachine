import { captureAppScreenshot } from '../screenshotUtil.js';

const TABS = ['SPATIALIZE', 'RECONSTRUCT', 'DRAWINGS', 'ARCHIVE', 'DIAGNOSTICS'];

export default function Header({ activeTab, onSelectTab }) {
  const handleScreencap = () => {
    captureAppScreenshot(activeTab);
  };

  return (
    <header className="bg-background text-primary border-b border-border flex justify-between items-center w-full px-container h-8 z-50 shrink-0">
      <div className="flex items-center gap-4">
        <span className="font-mono-label text-mono-label tracking-widest text-accent uppercase">
          MEMORY_MACHINE
        </span>
        <div className="h-4 w-[1px] bg-border mx-2" />
        <span className="font-mono-label text-mono-label text-accent uppercase">PERSHING_SQUARE</span>
      </div>
      <div className="flex items-center gap-4 h-full">
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
        <button
          onClick={handleScreencap}
          title="Capture screenshot"
          aria-label="Capture screenshot"
          className="flex items-center justify-center w-5 h-5 rounded-full border border-border text-on-surface-variant hover:text-accent hover:border-accent transition-colors shrink-0"
        >
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
            <circle cx="12" cy="13" r="4" />
          </svg>
        </button>
      </div>
    </header>
  );
}
