const BLENDER_HOST = 'http://127.0.0.1:8000';

// Displays the Line Art SVG produced by the headless-Blender "build" tier
// (see pershing_headless_build.py's build_line_art() / _export_lineart_svg())
// -- a plain <img>, not an embedded/parsed SVG DOM, since this file can be
// several MB of individual stroke paths and the browser only needs to
// rasterize it, not expose it for scripting. Same full-screen overlay shell
// as PaintOverlay.jsx, since this project already established that pattern
// for "a thing that isn't the live 3D view but needs real screen space."
export default function LineArtOverlay({ svgUrl, onClose }) {
  if (!svgUrl) return null;
  const fullUrl = `${BLENDER_HOST}${svgUrl}`;

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">LINE ART</h3>
          <div className="flex items-center gap-2">
            <a
              href={fullUrl}
              download
              className="px-3 py-1 border border-accent text-accent font-mono-sm text-mono-sm uppercase hover:bg-accent hover:text-background transition-all"
            >
              Download SVG
            </a>
            <button
              onClick={onClose}
              className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
            >
              Close
            </button>
          </div>
        </div>

        {/* bg-white (not the app's own surface color) -- the SVG's strokes
            are black-on-transparent, same as when this pipeline's output
            was verified via Playwright renders during development. */}
        <div className="flex-1 overflow-auto flex items-center justify-center bg-white p-4">
          <img src={fullUrl} alt="Line Art export" className="max-w-full max-h-full" />
        </div>
      </div>
    </div>
  );
}
