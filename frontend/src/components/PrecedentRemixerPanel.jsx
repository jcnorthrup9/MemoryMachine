import { useCallback, useState } from 'react';
import { remixPrecedent } from '../api.js';

// "Precedent Remixer" MVP (2026-07-12) -- AI-curated selection of layers
// from the data/ParkSVG/ precedent library for a text prompt, reusing the
// OLD app's already-working generate_spatial_seed()/remix_layers() (see
// logic/pershing_api.py's remix_precedent() docstring). Preview-only in
// this pass: shows the curated narrative + layer/role breakdown, but does
// NOT yet rasterize these layers into live paint masks or call bake() --
// that conversion (precedent SVG-unit space -> real site feet -> voxel
// grids) is real, separate engineering intentionally left for a following
// pass rather than shipped untested. Modeled on DiagramInputPanel.jsx's
// modal structure.

const ROLE_LABELS = {
  hardscape: 'Hardscape', water: 'Water', shade: 'Shade',
  greenscape: 'Greenscape', amenity_resting: 'Amenity / Rest',
};

export default function PrecedentRemixerPanel({ onClose, log }) {
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null); // { narrative, layers }

  const handleGenerate = useCallback(async () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    try {
      const res = await remixPrecedent(prompt.trim());
      setResult(res);
      log?.(`precedent remix: ${res.layers.length} layers curated`);
    } catch (err) {
      log?.(String(err), 'error');
    } finally {
      setGenerating(false);
    }
  }, [prompt, log]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6">
      <div className="bg-surface border border-border max-w-[90vw] max-h-[90vh] w-[640px] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-container border-b border-border">
          <h3 className="font-headline-md text-headline-md text-primary">PRECEDENT REMIXER</h3>
          <button
            onClick={onClose}
            className="px-3 py-1 border border-border font-mono-sm text-mono-sm uppercase text-on-surface-variant hover:text-on-surface"
          >
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-container space-y-4">
          <p className="font-mono-sm text-[11px] text-on-surface-variant">
            Describe the atmosphere you want and an AI curator selects layers from the precedent
            library (Parc de la Villette, Zaryadye Park, Schouwburgplein, Gardens by the Bay, ...) to
            match. Preview only for now -- applying the result to the live paint masks isn't wired
            up yet.
          </p>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="e.g. a quiet shady park with water features for reflection"
            rows={3}
            className="w-full bg-background border border-border p-2 font-mono-sm text-mono-sm text-on-surface resize-none"
          />
          <button
            onClick={handleGenerate}
            disabled={generating || !prompt.trim()}
            className="w-full py-3 border border-accent text-accent font-mono-sm text-mono-sm font-bold uppercase tracking-widest hover:bg-accent hover:text-background transition-all active:scale-[0.98] disabled:opacity-50"
          >
            {generating ? 'Curating...' : 'Generate'}
          </button>

          {result && (
            <div className="space-y-3 pt-2 border-t border-border">
              <p className="font-mono-sm text-[11px] text-on-surface-variant italic leading-relaxed">
                {result.narrative}
              </p>
              <div className="space-y-1">
                {result.layers.map((l, i) => (
                  <div
                    key={i}
                    className="flex justify-between font-mono-sm text-[11px] text-on-surface-variant border-b border-border/50 py-1"
                  >
                    <span>{l.site} / {l.layerId}</span>
                    <span className="text-accent">{ROLE_LABELS[l.role] ?? l.role}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
