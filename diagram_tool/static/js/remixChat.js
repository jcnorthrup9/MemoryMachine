/**
 * MEMORY MACHINE // DIAGRAM TOOL // AI REMIX CHAT
 *
 * 2026-07-17: a conversational front end for logic/diagram_remix_chat.py's
 * DiagramRemixChatAgent, which itself just wraps the main app's already-
 * working Precedent Remixer pipeline (generate_spatial_seed + remix_layers)
 * with server-side turn history. This file's own job is purely local:
 * send the latest message, then translate the AI's layer picks into
 * MemoryState.stack items the existing sliders/HUD/export already know how
 * to render -- no parallel rendering path, no new stack-item shape.
 *
 * frac -> pixel conversion: the backend returns transform.x_frac/y_frac
 * (fraction of the base boundary's own size, e.g. +/-0.3 -- see
 * logic/urban_engine.py's LOCATION_OFFSET_FRAC), but state.js's
 * getProgramStats() (and engine2D.js's renderer) expect transform.x/y as
 * absolute offsets from the base boundary's own center, in that SVG's
 * native units. Same math ingest_diagram_svg.py's rasterize_precedent_layers()
 * already does server-side for the main app's bake pipeline -- computed
 * here instead because the boundary bbox only exists client-side in this
 * tool (Engine2D.getBoundaryBBox against the live-loaded base SVG).
 */

function _remixFracToPixel(x_frac, y_frac) {
  const baseSVG = MemoryState.svgCache['PershingSquare'];
  if (!baseSVG || !window.Engine2D) return { x: 0, y: 0 };
  const baseEl = window.Engine2D.parseSVG(baseSVG);
  const bbox = window.Engine2D.getBoundaryBBox(baseEl);
  return { x: (x_frac || 0) * bbox.w, y: (y_frac || 0) * bbox.h };
}

function _appendRemixLogEntry(role, text) {
  const log = document.getElementById('remix-chat-log');
  if (!log) return;
  const empty = log.querySelector('.remix-chat-empty');
  if (empty) empty.remove();
  const entry = document.createElement('div');
  entry.className = `remix-chat-entry remix-chat-${role.toLowerCase()}`;
  entry.innerHTML = `<span class="remix-chat-role">${role}</span><span class="remix-chat-text"></span>`;
  entry.querySelector('.remix-chat-text').textContent = text;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

window.clearRemixChatLog = function () {
  const log = document.getElementById('remix-chat-log');
  if (!log) return;
  log.innerHTML = '<div class="remix-chat-empty">Describe the space you want — e.g. "a quiet, shady corner with water" — and refine it turn by turn.</div>';
};

async function _sendRemixMessage(message) {
  _appendRemixLogEntry('Designer', message);
  setStatus('Remixing...', 'running');
  try {
    const res = await fetch('/api/remix-diagram', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    _appendRemixLogEntry('AI', data.narrative || '(no narrative returned)');

    // Each remix turn is a fresh curated proposal reflecting the
    // conversation so far, not an ever-growing pile -- replace prior
    // non-locked picks, same as CLR does, but keep the locked base-context
    // rows (BOUNDARY/STREET/etc.) untouched.
    MemoryState.stack = MemoryState.stack.filter((i) => i.contextLayer);

    const layers = Array.isArray(data.layers) ? data.layers : [];
    const uniqueSites = [...new Set(layers.map((l) => l.site))];
    await Promise.all(uniqueSites.map((s) => fetchSVG(s).catch(() => null)));

    const now = Date.now();
    layers.forEach((layer, idx) => {
      const { x, y } = _remixFracToPixel(layer.transform?.x_frac, layer.transform?.y_frac);
      MemoryState.stack.push({
        id: now + idx,
        site: layer.site,
        layerId: layer.layerId,
        color: _getLayerColor(layer.layerId),
        label: layer.layerId,
        visible: true,
        locked: false,
        contextLayer: false,
        transform: {
          x, y,
          scale: layer.transform?.scale ?? 1.0,
          rot: layer.transform?.rot ?? 0,
        },
      });
    });

    window.renderRemixSVG?.();
    refreshStackUI();
    setStatus('Remix applied', 'success');
  } catch (e) {
    setStatus('Remix failed: ' + e.message, 'error');
  }
}

function _wireRemixChat() {
  const input = document.getElementById('remix-chat-input');
  const sendBtn = document.getElementById('remix-chat-send');
  if (!input || !sendBtn) return;

  const send = () => {
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';
    _sendRemixMessage(msg);
  };

  sendBtn.addEventListener('click', send);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') send();
  });
}

document.addEventListener('DOMContentLoaded', _wireRemixChat);
