"""
zine_compiler.py
----------------
Builds html/digitalPalimpsest.html from all project assets.

Sources (in order of injection):
  1. data/thesis_abstract.txt       - theory text
  2. data/memory_manifest.json      - intervention list
  3. data/cross_pollination/*.json  - per-intervention AI output packages
  4. archive/diagrams/*_annotated.jpg
  5. archive/rhinoScreenshots/intervention_masterplan_capture.png

Usage:
    .venv/Scripts/python.exe logic/zine_compiler.py
"""

import os, re, csv, json

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, 'data')
DIAG_DIR   = os.path.join(BASE_DIR, 'archive', 'diagrams')
RHINO_DIR  = os.path.join(BASE_DIR, 'archive', 'rhinoScreenshots')
CP_DIR     = os.path.join(DATA_DIR, 'cross_pollination')
OUTPUT     = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')

# ---------------------------------------------------------------------------
# CSS — shared design language
# ---------------------------------------------------------------------------
CSS = """
    :root {
        --bg-color: #050505;
        --text-color: #e0e0e0;
        --accent-glow: #fff4ca;
        --border-dim: #222;
        --trans-speed: 0.4s;
    }
    * { box-sizing: border-box; }
    body { background-color: var(--bg-color); color: var(--text-color);
           font-family: 'Courier New', Courier, monospace; margin: 0;
           height: 100vh; display: flex; justify-content: center;
           align-items: center; overflow: hidden; }
    .zine-viewer { width: 96vw; max-width: 1800px; height: 92vh;
                   background-color: #000; border: 1px solid var(--border-dim);
                   display: flex; flex-direction: column; position: relative; }
    .spread-container { flex-grow: 1; display: flex; position: relative;
                        overflow: hidden; z-index: 2; }
    .spine { position: absolute; left: 50%; top: 0; bottom: 0; width: 2px;
             background: var(--border-dim); z-index: 10; }

    .binary-texture { position: absolute; top: 0; left: 0; width: 100%; height: 100%;
                      opacity: 0.05; font-size: 0.6rem; line-height: 1.1; color: #fff;
                      overflow: hidden; z-index: 1; user-select: none;
                      word-wrap: break-word; pointer-events: none; }

    .page-side { width: 50%; height: 100%; display: flex; flex-direction: column;
                 position: relative; z-index: 5;
                 transition: all var(--trans-speed) cubic-bezier(0.2, 0.8, 0.2, 1); }
    .left-page  { padding: 60px 100px 60px 60px; }
    .right-page { padding: 60px 60px 60px 100px; }

    .grid-layout { display: grid; grid-template-columns: repeat(12, 1fr);
                   grid-template-rows: auto 1fr; gap: 20px; height: 100%; }

    .abstract-flow { column-count: 2; column-gap: 40px;
                     column-rule: 1px solid #1a1a1a; text-align: justify;
                     text-align-last: left; font-size: 0.85rem; line-height: 1.6;
                     color: #bbb; height: 100%; column-fill: balance; overflow: hidden;
                     grid-column: 1 / -1;
                     transition: all var(--trans-speed) ease-out; }

    .vessel { display: flex; flex-direction: column; height: 100%; overflow: hidden;
              transition: all var(--trans-speed) ease-out; }
    .vessel-span-8  { grid-column: span 8; }
    .vessel-span-4  { grid-column: span 4; border-left: 1px solid var(--border-dim);
                      padding-left: 20px; }
    .vessel-span-12 { grid-column: 1 / -1; }

    .vignette { border-left: 1px solid var(--accent-glow); padding-left: 20px;
                margin-bottom: 30px; font-size: 0.85em; color: #aaa; text-align: left; }
    h1.zine-title { font-size: 3rem; color: var(--accent-glow); margin-bottom: 5px;
                    transition: all var(--trans-speed) ease-out; }
    h2.page-header { color: #444; font-size: 0.8rem; text-transform: uppercase;
                     border-bottom: 1px solid #111; padding-bottom: 10px;
                     margin-bottom: 30px; flex-shrink: 0; grid-column: 1 / -1;
                     transition: all var(--trans-speed) ease-out; }

    pre { margin: 0; font-size: 0.7rem; line-height: 1.4; color: #555;
          white-space: pre-wrap; transition: all var(--trans-speed) ease-out; }
    .json-block   { color: #88ff88; text-align: left; width: 100%; }
    .binary-block { color: #444; letter-spacing: 3px; text-align: center;
                    font-size: 0.65rem; }

    .spread { display: none; width: 100%; height: 100%; position: absolute;
              top: 0; left: 0; }
    .spread.active { display: flex; }

    .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim);
                   display: flex; justify-content: space-between; align-items: center;
                   font-size: 0.8em; color: #444; background: #000; z-index: 100;
                   position: relative; }
    .nav-controls button { background: none; border: 1px solid #222;
                           color: var(--text-color); padding: 5px 20px; cursor: pointer; }
    .nav-controls button:hover { background: #111; border-color: #444; }

    .matrix-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;
                   width: 100%; align-content: start; }
    .matrix-item { background: #080808; border: 1px solid #111; position: relative;
                   display: flex; flex-direction: column; }
    .matrix-item img { width: 100%; aspect-ratio: 4/3; object-fit: cover;
                       object-position: center; display: block; }
    .matrix-label { padding: 8px; font-size: 0.6rem; color: #888;
                    text-transform: uppercase; text-align: center;
                    border-top: 1px solid #111; letter-spacing: 1px; }

    .single-image-view { width: 100%; height: 100%; display: flex;
                         flex-direction: column; border: 1px solid #111;
                         background: #080808; }
    .single-image-view img { flex-grow: 1; width: 100%; height: 100%;
                              object-fit: contain; object-position: center; display: block; }
    .single-image-view .matrix-label { border-top: 1px solid #111; padding: 10px;
                                        font-size: 0.7rem; color: #aaa;
                                        text-transform: uppercase; letter-spacing: 2px;
                                        text-align: center; }

    .yearbook-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
                     width: 100%; }
    .yearbook-entry { display: flex; flex-direction: column; align-items: center; }
    .yearbook-placeholder { width: 100%; aspect-ratio: 1; background: #0a0a0a;
                             border: 1px dashed #333; display: flex;
                             align-items: center; justify-content: center; color: #444;
                             font-size: 0.6rem; overflow: hidden; }
    .yearbook-placeholder img { width: 100%; height: 100%; object-fit: cover; }
    .yearbook-label { margin-top: 5px; font-size: 0.55rem; color: #666;
                      text-transform: uppercase; text-align: center; letter-spacing: 1px; }

    @keyframes fade-in-image {
        from { opacity: 0; transform: scale(0.98); }
        to   { opacity: 1; transform: scale(1); }
    }
    .watercolor-image { opacity: 0; }
    .spread.active .watercolor-image {
        animation: fade-in-image 1.5s ease-out 0.4s forwards;
    }

    /* ── GHOST FRAGMENTS ── */
    .ghost-fragment {
        position: absolute; pointer-events: none; opacity: 0.6; z-index: 50;
        filter: grayscale(1) contrast(2); mix-blend-mode: hard-light;
        transform: rotate(var(--r, 0deg)) scale(var(--s, 1));
        animation: ghost-flicker 4s infinite ease-in-out,
                   ghost-shift   8s infinite ease-in-out;
        max-width: 300px;
        box-shadow: 2px 0 0 rgba(255,0,0,0.5), -2px 0 0 rgba(0,0,255,0.5);
        overflow: hidden; border: 1px solid red; background: #000;
    }
    @keyframes ghost-flicker {
        0%   { opacity: 0; clip-path: inset(0 0 0 0); filter: blur(0px); }
        20%  { opacity: 0.4; clip-path: polygon(10% 0, 90% 0, 100% 100%, 0 90%);
               filter: blur(2px) hue-rotate(45deg); }
        50%  { opacity: 0.7; clip-path: polygon(0 0, 100% 10%, 100% 90%, 0 100%);
               filter: blur(1px) hue-rotate(90deg); }
        80%  { opacity: 0.3; clip-path: polygon(20% 0, 80% 0, 100% 100%, 0 100%);
               filter: blur(4px) hue-rotate(135deg); }
        100% { opacity: 0; clip-path: inset(0 0 0 0); filter: blur(10px); }
    }
    @keyframes ghost-shift {
        0%   { translate: 0 0; }    20% { translate: 10px -10px; }
        40%  { translate: -15px 15px; } 60% { translate: 20px 5px; }
        80%  { translate: -10px -20px; } 100% { translate: 0 0; }
    }

    /* ── STABILITY BUTTON ── */
    .stability-btn { position: absolute; top: 0; right: 0; width: 150px; height: 150px;
                     z-index: 10000; cursor: crosshair; }
    .stability-btn:active { background-color: rgba(255,255,255,0.05); }

    /* ── DEGRADATION STAGES ── */
    @keyframes subtle-rot {
        0%   { filter: hue-rotate(0deg) blur(0px); opacity: 1; }
        50%  { filter: hue-rotate(5deg) blur(0.5px) sepia(0.2); opacity: 0.95; }
        100% { filter: hue-rotate(0deg) blur(0px); opacity: 1; }
    }
    body.degrading-mild .spread-container {
        animation: subtle-rot 6s infinite ease-in-out;
    }
    @keyframes datamosh-freeze {
        0%   { filter: none; transform: none; clip-path: inset(0 0 0 0); }
        20%  { filter: contrast(1.2) hue-rotate(20deg) blur(2px);
               transform: scale(1.02) skewX(2deg); }
        40%  { filter: contrast(1.5) hue-rotate(40deg) blur(4px);
               transform: translate(-5px,5px) skewY(2deg);
               clip-path: polygon(0 0, 100% 10%, 100% 100%, 0 90%); }
        60%  { filter: contrast(2) hue-rotate(90deg) blur(8px);
               transform: scale(1.1) rotate(1deg); clip-path: inset(5% 10% 5% 5%); }
        80%  { filter: contrast(3) hue-rotate(180deg) blur(12px) opacity(0.8);
               transform: scale(1.2) translate(10px,-10px); }
        100% { filter: contrast(4) grayscale(1) blur(20px) opacity(0);
               transform: scale(1.3) rotate(5deg); pointer-events: none; }
    }
    @keyframes gpu-tear {
        0%   { transform: translate(0,0) skew(0deg); clip-path: inset(0 0 0 0); filter: none; }
        20%  { transform: translate(-2px,1px) skew(5deg);
               clip-path: polygon(0 0, 100% 2%, 100% 98%, 0 100%); filter: blur(1px); }
        40%  { transform: translate(4px,-4px) skew(-10deg);
               clip-path: polygon(5% 0, 95% 0, 100% 100%, 0 100%);
               filter: contrast(1.5) blur(2px); }
        60%  { transform: translate(-5px,5px) skew(20deg);
               clip-path: polygon(0 10%, 100% 0, 90% 100%, 10% 100%);
               filter: hue-rotate(90deg) blur(4px); }
        80%  { transform: translate(10px,-10px) skew(-30deg) scale(1.1);
               clip-path: polygon(0 0, 50% 10%, 100% 0, 100% 100%, 50% 90%, 0 100%);
               filter: hue-rotate(180deg) blur(8px); }
        100% { transform: translate(50px,50px) scale(1.2);
               opacity: 0; filter: blur(15px); }
    }
    body.degrading-severe .spread-container {
        animation: datamosh-freeze 45s cubic-bezier(0.7, 0, 0.84, 0) forwards;
    }
    body.degrading-severe .page-side h1,
    body.degrading-severe .page-side h2,
    body.degrading-severe .page-side p,
    body.degrading-severe .page-side img {
        animation: gpu-tear 40s steps(60) forwards;
    }

    /* ── GLITCH ── */
    @keyframes glitch-anim {
        0%   { clip-path: polygon(0 2%, 100% 2%, 100% 5%, 0 5%);
               transform: translate(0,0) skew(0); }
        20%  { clip-path: polygon(0 15%, 100% 15%, 100% 15%, 0 15%);
               transform: translate(-25px,2px) skew(40deg); }
        40%  { clip-path: polygon(0 10%, 100% 10%, 100% 20%, 0 20%);
               transform: translate(25px,-2px) skew(-40deg); }
        60%  { clip-path: polygon(0 1%, 100% 1%, 100% 2%, 0 2%);
               transform: translate(15px,0) skew(15deg); }
        80%  { clip-path: polygon(0 33%, 100% 33%, 100% 33%, 0 33%);
               transform: translate(-15px,2px) skew(-10deg); }
        100% { clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%);
               transform: translate(0,0) skew(0); }
    }
    body.glitch-mode .page-side { animation: glitch-anim 0.6s infinite steps(2);
                                   filter: invert(1); }
    body.glitch-mode .left-page  { transform: translateX(20px) rotate(-1deg); }
    body.glitch-mode .right-page { transform: translateX(-20px) rotate(1deg);
                                    margin-left: -50px; }
    body.glitch-mode h1, body.glitch-mode h2 {
        animation: glitch-anim 4s infinite linear alternate-reverse;
        color: #ff0000; text-shadow: 2px 0 #00ff00;
    }
    body.glitch-mode pre { animation: glitch-anim 1s infinite; opacity: 0.5; }
    body.glitch-mode .binary-texture { animation: glitch-anim 0.2s infinite reverse;
                                        color: #00ff00; opacity: 0.2; }
    .nav-controls button.reboot-mode { background-color: #f00; color: #000;
                                        border: 1px solid #f00;
                                        animation: glitch-anim 0.2s infinite;
                                        font-weight: bold; }

    /* ── INTERVENTION SPREADS ── */
    .intervention-tag { display: inline-block; font-size: 0.6rem; letter-spacing: 3px;
                         color: var(--accent-glow); border: 1px solid var(--accent-glow);
                         padding: 2px 8px; margin-bottom: 14px; text-transform: uppercase; }
    .intervention-name { font-size: 2rem; color: var(--accent-glow);
                          line-height: 1.1; margin-bottom: 20px; }
    .narrative-block { font-size: 0.8rem; line-height: 1.7; color: #bbb;
                        overflow: hidden; flex: 1; }
    .narrative-block p { margin: 0 0 1em; }
    .mermaid-container { width: 100%; height: 100%; display: flex;
                          align-items: center; justify-content: center;
                          overflow: auto; }
    .mermaid { font-size: 0.6rem !important; }
    .render-full { width: 100%; height: 100%; object-fit: contain;
                   object-position: center; display: block;
                   filter: brightness(0.9) contrast(1.1); }
    .source-chip { display: inline-block; font-size: 0.55rem; color: #666;
                    border: 1px solid #222; padding: 2px 6px; margin: 2px 2px 0 0;
                    letter-spacing: 1px; }

    /* ── PRINT ── */
    @media print {
        @page { size: letter landscape; margin: 0; }
        html, body { display: block !important; width: 100%; height: auto !important;
                     overflow: visible !important; background-color: #050505 !important;
                     -webkit-print-color-adjust: exact; print-color-adjust: exact; }
        .zine-viewer { display: block !important; width: 100%; height: auto !important;
                        max-width: none; border: none; position: static; overflow: visible;
                        margin: 0 !important; }
        .spread-container { display: block !important; position: static;
                             overflow: visible; height: auto !important; }
        .spine, .nav-controls, .stability-btn, .binary-texture,
        #page-indicator { display: none !important; }
        .spread { display: flex !important; position: relative !important; width: 100%;
                  height: 100vh !important; page-break-after: always; break-after: page;
                  top: auto; left: auto; opacity: 1 !important;
                  visibility: visible !important; }
        .ghost-fragment { mix-blend-mode: normal !important; opacity: 0.7 !important;
                           filter: contrast(1.5) grayscale(1); border-color: #ff0000 !important; }
        .watercolor-image { opacity: 1 !important; animation: none !important; }
        .mermaid svg { max-height: 80vh; }
    }
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_file(path, fallback="[MISSING DATA]"):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return f.read().strip()
    return fallback

def get_data(filename):
    return read_file(os.path.join(DATA_DIR, filename))

def slug(name):
    """'Canopy of Whispers' → 'canopy_of_whispers'"""
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

def esc(text):
    """Minimal HTML escaping for injected text."""
    return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def process_vignettes(text):
    if "MISSING DATA" in text:
        return f'<div class="vignette" style="color:#666;">{esc(text)}</div>'
    return "".join(
        f'<div class="vignette">{s.strip()}</div>'
        for s in text.split('---') if s.strip()
    )

def generate_html_for_group(file_list, rel_prefix="../archive/precedents/"):
    if not file_list:
        return '<div class="vignette" style="color:#666;">[NO DATA]</div>'
    items = [f'<img src="{rel_prefix}{f}">' for f in file_list]
    if len(items) == 1:
        return f'<div class="single-image-view">{items[0]}<div class="matrix-label">{file_list[0]}</div></div>'
    grid = "".join(f'<div class="matrix-item">{item}</div>' for item in items)
    return f'<div class="matrix-grid">{grid}</div>'

def split_group(file_list):
    mid = (len(file_list) + 1) // 2
    return file_list[:mid], file_list[mid:]

# ---------------------------------------------------------------------------
# Intervention loading
# ---------------------------------------------------------------------------

def load_interventions():
    """
    Returns a list of intervention dicts, sourced from data/cross_pollination/*.json.
    Manifest entries without a matching cross_pollination file are included as stubs.

    Expected cross_pollination JSON schema:
    {
      "name":               string,
      "narrative":          string   (may contain newlines/paragraphs),
      "spatial_parameters": dict,
      "mermaid_diagram":    string   (raw mermaid graph TD / flowchart text),
      "sources":            list of {name, location, notes},
      "annotated_image":    string   (filename only, inside archive/diagrams/),
      "blueprint_sources":  list of strings  (optional)
    }
    """
    os.makedirs(CP_DIR, exist_ok=True)

    # Load manifest names
    manifest_path = os.path.join(DATA_DIR, 'memory_manifest.json')
    manifest_names = []
    if os.path.exists(manifest_path):
        try:
            manifest = json.loads(read_file(manifest_path))
            manifest_names = [e.get('name','') for e in manifest if e.get('name')]
        except Exception as e:
            print(f"   [WARN] Could not parse memory_manifest.json: {e}")

    # Load cross_pollination JSON files
    cp_files = {}
    if os.path.exists(CP_DIR):
        for f in sorted(os.listdir(CP_DIR)):
            if f.endswith('.json'):
                path = os.path.join(CP_DIR, f)
                try:
                    data = json.loads(read_file(path))
                    name = data.get('name', os.path.splitext(f)[0])
                    cp_files[name] = data
                except Exception as e:
                    print(f"   [WARN] Could not parse {f}: {e}")

    # Merge: manifest entries + any extra CP files not in manifest
    seen = set()
    interventions = []

    # Process manifest entries first (preserves order)
    for name in manifest_names:
        if name in seen:
            continue
        seen.add(name)
        data = cp_files.get(name, {"name": name})  # stub if no CP file
        interventions.append(data)

    # Add any CP files not in the manifest
    for name, data in cp_files.items():
        if name not in seen:
            seen.add(name)
            interventions.append(data)

    return interventions

# ---------------------------------------------------------------------------
# Intervention spread builders
# ---------------------------------------------------------------------------

def _narrative_page(n, idx, total, iv):
    """Left page: tag + name + narrative + source chips."""
    name      = esc(iv.get('name', 'UNKNOWN'))
    narrative = iv.get('narrative', '[NARRATIVE PENDING]')
    sources   = iv.get('sources', [])
    sp        = iv.get('spatial_parameters', {})
    geo       = esc(sp.get('geometry_type', '—'))
    height    = esc(str(sp.get('height_m', '—')))
    mats      = ', '.join(sp.get('materials', [])) or '—'

    chips = "".join(
        f'<span class="source-chip">{esc(s.get("name","?"))}</span>'
        for s in sources
    ) or '<span class="source-chip">NO SOURCES</span>'

    paras = "".join(f'<p>{esc(p.strip())}</p>' for p in narrative.split('\n') if p.strip())

    return f'''
        <div class="page-side left-page">
            <div class="grid-layout">
                <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // NARRATIVE</h2>
                <div class="vessel vessel-span-12">
                    <div class="intervention-tag">[ MEMORY MACHINE // AI SYNTHESIS ]</div>
                    <div class="intervention-name">{name}</div>
                    <div class="narrative-block">{paras}</div>
                    <div style="margin-top: 16px; flex-shrink: 0;">
                        <pre style="color:#444; font-size:0.65rem; margin-bottom:8px;">
GEOMETRY  : {geo}
HEIGHT    : {height}m
MATERIALS : {esc(mats)}</pre>
                        <div>{chips}</div>
                    </div>
                </div>
            </div>
        </div>'''


def _spatial_params_page(n, idx, total, iv):
    """Right page: spatial parameters JSON dump."""
    sp = iv.get('spatial_parameters', {})
    pretty = json.dumps(sp, indent=2, ensure_ascii=False) if sp else '{ "status": "PENDING" }'

    return f'''
        <div class="page-side right-page">
            <div class="grid-layout">
                <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // SPATIAL PARAMETERS</h2>
                <div class="vessel vessel-span-12">
                    <pre class="json-block">{esc(pretty)}</pre>
                </div>
            </div>
        </div>'''


def _mermaid_page(n, idx, total, iv):
    """Left page: Mermaid.js logic diagram."""
    mmd = iv.get('mermaid_diagram', '').strip()
    if mmd:
        content = f'<div class="mermaid-container"><div class="mermaid">{esc(mmd)}</div></div>'
    else:
        content = '<div class="vignette" style="color:#666;">[LOGIC DIAGRAM PENDING]</div>'

    return f'''
        <div class="page-side left-page">
            <div class="grid-layout">
                <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // LOGIC DIAGRAM</h2>
                <div class="vessel vessel-span-12">
                    {content}
                </div>
            </div>
        </div>'''


def _annotated_image_page(n, idx, total, iv):
    """Right page: annotated diagram image."""
    img_file  = iv.get('annotated_image', '')
    iv_name   = iv.get('name', '')

    # Try explicit field first, then discover from diagrams dir
    if not img_file and iv_name:
        pattern = slug(iv_name)
        candidates = [
            f for f in os.listdir(DIAG_DIR)
            if '_annotated' in f.lower() and pattern in f.lower()
        ] if os.path.exists(DIAG_DIR) else []
        img_file = candidates[0] if candidates else ''

    if img_file and os.path.exists(os.path.join(DIAG_DIR, img_file)):
        img_src   = f'../archive/diagrams/{img_file}'
        img_label = esc(img_file.replace('_', ' ').upper())
        content   = f'''<div class="single-image-view">
                            <img src="{img_src}" class="watercolor-image">
                            <div class="matrix-label">{img_label}</div>
                        </div>'''
    else:
        content = '<div class="vignette" style="color:#666;">[ANNOTATED IMAGE PENDING]</div>'

    return f'''
        <div class="page-side right-page">
            <div class="grid-layout">
                <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // ANNOTATED DIAGRAM</h2>
                <div class="vessel vessel-span-12">
                    {content}
                </div>
            </div>
        </div>'''


def _render_spread(n, idx, total, iv):
    """Full-bleed Rhino render spread (or stub)."""
    render_path = os.path.join(RHINO_DIR, 'intervention_masterplan_capture.png')
    name = esc(iv.get('name', 'GENERATED INTERVENTION'))

    if os.path.exists(render_path):
        render_html = f'''
            <div class="page-side left-page" style="padding: 0; overflow: hidden;">
                <img src="../archive/rhinoScreenshots/intervention_masterplan_capture.png"
                     class="render-full watercolor-image">
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // RHINO MASTERPLAN</h2>
                    <div class="vessel vessel-span-12">
                        <div class="intervention-tag">[ RHINO 8 // MEM_GENERATED LAYER ]</div>
                        <div class="intervention-name" style="font-size:1.4rem;">{name}</div>
                        <pre style="color:#444; font-size:0.65rem;">
CAPTURE : intervention_masterplan_capture.png
ORIGIN  : logic/bake_to_rhino.py
LAYER   : MEM_GENERATED
UNITS   : 1 unit = 5m</pre>
                    </div>
                </div>
            </div>'''
    else:
        render_html = f'''
            <div class="page-side left-page">
                <div class="grid-layout">
                    <h2 class="page-header">{n:02d} // GENERATED INTERVENTION {idx+1}/{total} // RHINO MASTERPLAN</h2>
                    <div class="vessel vessel-span-12">
                        <div class="vignette" style="color:#666;">[RHINO RENDER PENDING — run bake_to_rhino.py and capture viewport]</div>
                    </div>
                </div>
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">{n:02d} // — </h2>
                </div>
            </div>'''

    return render_html


def build_intervention_spreads(interventions, start_spread_num):
    """
    Build all intervention spreads and return (html_string, label_list).
    Per intervention: 3 spreads (narrative+params, diagram+image, render).
    """
    html_parts = []
    labels     = []
    n          = start_spread_num
    total      = len(interventions)

    for idx, iv in enumerate(interventions):
        tag = f'IV_{idx+1:02d}'

        # Spread A: Narrative (L) + Spatial Params (R)
        html_parts.append(f'<div class="spread" id="spread-{n}">')
        html_parts.append(_narrative_page(n, idx, total, iv))
        html_parts.append(_spatial_params_page(n, idx, total, iv))
        html_parts.append('</div>')
        labels.append(f'{tag} // NARRATIVE')
        n += 1

        # Spread B: Mermaid (L) + Annotated Image (R)
        html_parts.append(f'<div class="spread" id="spread-{n}">')
        html_parts.append(_mermaid_page(n, idx, total, iv))
        html_parts.append(_annotated_image_page(n, idx, total, iv))
        html_parts.append('</div>')
        labels.append(f'{tag} // DIAGRAM')
        n += 1

        # Spread C: Rhino render (full-bleed)
        html_parts.append(f'<div class="spread" id="spread-{n}">')
        html_parts.append(_render_spread(n, idx, total, iv))
        html_parts.append('</div>')
        labels.append(f'{tag} // MASTERPLAN')
        n += 1

    return '\n'.join(html_parts), labels

# ---------------------------------------------------------------------------
# Fixed-spread builders (thesis/precedents sections — unchanged logic)
# ---------------------------------------------------------------------------

def build_fixed_spreads(binary_data, abs_chunks, vignettes, yearbook_grids,
                         precedent_groups, arch_memory, references, pipeline_data,
                         toc_placeholder, fixed_labels):
    """Returns HTML for all 19 fixed spreads as a string."""

    abs_1, abs_2, abs_3, abs_4, abs_5, abs_6 = abs_chunks
    v88, v92, v94                             = vignettes
    json_88, bin_88, json_92, bin_92, json_94, bin_94 = precedent_groups['jsons_bins']
    yb_1, yb_2                               = yearbook_grids
    (rossi, neu_l, neu_r, zeitz_l, zeitz_r,
     genbaku_l, genbaku_r, dosuh_l, dosuh_r) = precedent_groups['images']

    def spread(sid, left_header, left_body, right_header, right_body, extra_class=""):
        return f'''
            <div class="spread{" " + extra_class if extra_class else ""}" id="spread-{sid}">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{left_header}</h2>
                        <div class="vessel vessel-span-12">{left_body}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{right_header}</h2>
                        <div class="vessel vessel-span-12">{right_body}</div>
                    </div>
                </div>
            </div>'''

    parts = []

    # Spread 1 — Cover
    parts.append(f'''
        <div class="spread active" id="spread-1"
             style="justify-content: center; align-items: center; flex-direction: column;
                    background-color: #030303; z-index: 10;">
            <div style="text-align: center; width: 80%; max-width: 1400px;
                        padding: 40px; position: relative; z-index: 10;">
                <h1 class="zine-title" style="font-size: 5rem; margin-bottom: 10px;">
                    Forensic_Palimpsest
                </h1>
                <div style="letter-spacing: 8px; color: #666; margin-bottom: 60px; font-size: 1.2rem;">
                    THE MEMORY MACHINE // JOHN C. NORTHRUP II
                </div>
                <img src="../archive/render_output/front_cover.jpg"
                     style="width: 100%; max-height: 65vh; object-fit: contain;
                            border: 1px solid var(--border-dim); filter: grayscale(100%);
                            box-shadow: 0 0 40px rgba(0,0,0,0.8);">
            </div>
        </div>''')

    # Spread 2 — TOC + Pipeline
    parts.append(spread(
        2, "01 // Table of Contents",
        f'<pre style="color:#666; font-size:1rem;">{toc_placeholder}</pre>',
        "02 // System Pipeline Logic",
        f'<pre style="color:#666; font-size:0.8rem;">{esc(pipeline_data)}</pre>'
    ))

    # Spreads 3-8 — Abstract
    for i, chunk in enumerate(abs_chunks, start=1):
        pg = 2 + i
        parts.append(f'''
            <div class="spread" id="spread-{pg}">
                <div class="page-side {"left" if i%2==1 else "right"}-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{(pg*2-3):02d} // The Machine That Forgets // {["I","II","III","IV","V","VI"][i-1]}</h2>
                        <div class="abstract-flow">{chunk}</div>
                    </div>
                </div>
                <div class="page-side {"right" if i%2==1 else "left"}-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{(pg*2-2):02d} // The Machine That Forgets // {["II","III","IV","V","VI","VII"][i-1]}</h2>
                        <div class="abstract-flow">{abs_chunks[i] if i < len(abs_chunks) else ""}</div>
                    </div>
                </div>
            </div>''')
        if i % 2 == 0:  # pair up: spread 3 covers chunks 1+2, spread 4 covers 3+4, etc.
            break
        # Actually let's keep original: one chunk per page
    # Reset — rebuild abstract spreads properly (pairs)
    parts = parts[:-4]  # remove the incorrect ones above and rebuild

    for pair in range(3):
        sid = 3 + pair
        left_i  = pair * 2
        right_i = left_i + 1
        roman = ["I","II","III","IV","V","VI"]
        lh = f"{(sid*2-3):02d} // The Machine That Forgets // {roman[left_i]}"
        rh = f"{(sid*2-2):02d} // The Machine That Forgets // {roman[right_i]}"
        parts.append(f'''
            <div class="spread" id="spread-{sid}">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{lh}</h2>
                        <div class="abstract-flow">{abs_chunks[left_i]}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">{rh}</h2>
                        <div class="abstract-flow">{abs_chunks[right_i]}</div>
                    </div>
                </div>
            </div>''')

    # Spread 6 — Yearbook A + B
    parts.append(f'''
        <div class="spread" id="spread-6">
            <div class="page-side left-page">
                <div class="grid-layout">
                    <h2 class="page-header">09 // Forensic Asset Catalog // A</h2>
                    <div class="vessel vessel-span-12">{yb_1}</div>
                </div>
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">10 // Forensic Asset Catalog // B</h2>
                    <div class="vessel vessel-span-12">{yb_2}</div>
                </div>
            </div>
        </div>''')

    # Spreads 7-10 — 1988 / 1992 / 1994 nodes
    node_data = [
        ("1988_Trailer", v88, json_88, bin_88, 7),
        ("1992_Birthday", v92, json_92, bin_92, 9),
        ("1994_Basin",    v94, json_94, bin_94, 11),
    ]
    for label, vignette, js, bn, sid in node_data:
        parts.append(f'''
            <div class="spread" id="spread-{sid}">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Node: {label} // Narrative</h2>
                        <div class="vessel vessel-span-12">{vignette}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Node: {label} // Logic + Binary</h2>
                        <div class="vessel vessel-span-8">
                            <pre class="json-block">{esc(js)}</pre>
                        </div>
                        <div class="vessel vessel-span-4">
                            <pre class="binary-block">{esc(bn[:1200])}</pre>
                        </div>
                    </div>
                </div>
            </div>''')
        parts.append(f'''
            <div class="spread" id="spread-{sid+1}">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Node: {label} // Render</h2>
                        <div class="vessel vessel-span-12">
                            <div class="vignette" style="color:#666;">[RENDER PLACEHOLDER]</div>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Node: {label} // Watercolors</h2>
                        <div class="vessel vessel-span-12">
                            <div class="vignette" style="color:#666;">[WATERCOLOR PLACEHOLDER]</div>
                        </div>
                    </div>
                </div>
            </div>''')

    # Spread 13 — Rossi + Arch Memory
    parts.append(f'''
        <div class="spread" id="spread-13">
            <div class="page-side left-page">
                <div class="grid-layout">
                    <h2 class="page-header">// Precedent: Aldo Rossi</h2>
                    <div class="vessel vessel-span-12">{rossi}</div>
                </div>
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">// Theory: Architectural Memory</h2>
                    <div class="vessel vessel-span-12">{arch_memory}</div>
                </div>
            </div>
        </div>''')

    # Spreads 14-17 — Precedent image groups
    prec_spreads = [
        (14, "Neu Museum",   neu_l,      neu_r),
        (15, "Zeitz MOCAA",  zeitz_l,    zeitz_r),
        (16, "Genbaku Dome", genbaku_l,  genbaku_r),
        (17, "Do Ho Suh",    dosuh_l,    dosuh_r),
    ]
    for sid, label, left_imgs, right_imgs in prec_spreads:
        parts.append(f'''
            <div class="spread" id="spread-{sid}">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Precedent: {label} // I</h2>
                        <div class="vessel vessel-span-12">{left_imgs}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">// Precedent: {label} // II</h2>
                        <div class="vessel vessel-span-12">{right_imgs}</div>
                    </div>
                </div>
            </div>''')

    # Spread 18 — References
    parts.append(f'''
        <div class="spread" id="spread-18">
            <div class="page-side left-page">
                <div class="grid-layout">
                    <h2 class="page-header">// References</h2>
                    <div class="vessel vessel-span-12">
                        <pre style="color:#555; font-size:0.7rem;">{esc(references)}</pre>
                    </div>
                </div>
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">// System Status</h2>
                    <div class="vessel vessel-span-12">
                        <pre style="color:#333; font-size:0.65rem;">{esc(pipeline_data)}</pre>
                    </div>
                </div>
            </div>
        </div>''')

    return '\n'.join(parts)

# ---------------------------------------------------------------------------
# Main compiler
# ---------------------------------------------------------------------------

def compile_zine():
    print("\n--- Waking up the Memory Machine ---")

    # ── Thesis abstract ───────────────────────────────────────────────────
    abstract = get_data('thesis_abstract.txt')
    words = abstract.split()
    chunk = max(1, len(words) // 6)
    abs_chunks = [" ".join(words[i*chunk:(i+1)*chunk]) for i in range(6)]
    while len(abs_chunks) < 6:
        abs_chunks.append("")

    # ── Node narratives ───────────────────────────────────────────────────
    v88 = process_vignettes(get_data('1988_trailer_parsed.txt'))
    v92 = process_vignettes(get_data('1992_birthday_parsed.txt'))
    v94 = process_vignettes(get_data('1994_basin_parsed.txt'))

    json_88 = get_data('1988_trailer_logic.json')
    bin_88  = get_data('1988_trailer_binary_strata.txt')
    json_92 = get_data('1992_birthday_logic.json')
    bin_92  = get_data('1992_birthday_binary_strata.txt')
    json_94 = get_data('1994_basin_logic.json')
    bin_94  = get_data('1994_basin_binary_strata.txt')

    references = get_data('references.txt')

    # ── Yearbook thumbnails ───────────────────────────────────────────────
    thumb_dir = os.path.join(BASE_DIR, 'archive', 'assets', 'thumbnails')
    yearbook_data = []
    if os.path.exists(thumb_dir):
        for f in sorted(os.listdir(thumb_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                content = f'<img src="../archive/assets/thumbnails/{f}">'
                yearbook_data.append(content)
    while len(yearbook_data) < 32:
        yearbook_data.append('<span style="color:#444; font-size:0.5rem;">[PENDING]</span>')

    def make_yb_grid(items):
        entries = "".join(
            f'<div class="yearbook-entry"><div class="yearbook-placeholder">{c}</div></div>'
            for c in items
        )
        return f'<div class="yearbook-grid">{entries}</div>'

    yb_1 = make_yb_grid(yearbook_data[:16])
    yb_2 = make_yb_grid(yearbook_data[16:32])

    # ── Precedent images ──────────────────────────────────────────────────
    prec_dir = os.path.join(BASE_DIR, 'archive', 'precedents')
    groups = {"rossi": [], "neu": [], "zeitz": [], "genbaku": [], "dohosuh": []}
    if os.path.exists(prec_dir):
        print(f"   > Scanning: {prec_dir}")
        for f in sorted(os.listdir(prec_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                n = f.lower()
                if "rossi"   in n: groups["rossi"].append(f)
                elif "neu"   in n: groups["neu"].append(f)
                elif "zeitz" in n: groups["zeitz"].append(f)
                elif "genbaku" in n: groups["genbaku"].append(f)
                elif "suh" in n or "doho" in n: groups["dohosuh"].append(f)

    rossi                     = generate_html_for_group(groups["rossi"])
    neu_l,    neu_r           = [generate_html_for_group(g) for g in split_group(groups["neu"])]
    zeitz_l,  zeitz_r         = [generate_html_for_group(g) for g in split_group(groups["zeitz"])]
    genbaku_l, genbaku_r      = [generate_html_for_group(g) for g in split_group(groups["genbaku"])]
    dosuh_l,  dosuh_r         = [generate_html_for_group(g) for g in split_group(groups["dohosuh"])]

    arch_memory = f'<div class="vignette">{get_data("ThePersistentArtifact.txt")}</div>'

    # ── Pipeline scan ─────────────────────────────────────────────────────
    skip_dirs = {'.git','__pycache__','venv','env','.pytest_cache','node_modules','.venv'}
    lines = ["DETECTED PYTHON MODULES:"]
    for root, dirs, files in os.walk(BASE_DIR):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs)
        py_files = [f for f in files if f.endswith('.py')]
        if py_files:
            rel = os.path.relpath(root, BASE_DIR)
            label = "ROOT" if rel == "." else rel.upper().replace(os.sep, " :: ")
            lines.append(f"\n[ {label} ]")
            lines += [f"   > {f}" for f in sorted(py_files)]
    pipeline_data = "\n".join(lines)

    # ── Load interventions ────────────────────────────────────────────────
    interventions = load_interventions()
    print(f"   > Interventions found: {len(interventions)}")
    for iv in interventions:
        print(f"     - {iv.get('name','?')}")

    # ── Load precedent analyses ───────────────────────────────────────────
    analyses = load_precedent_analyses(interventions)
    print(f"   > Precedent Analyses found: {len(analyses)}")
    for a in analyses:
        print(f"     - {a.get('name','?')}")

    # ── Determine spread counts ───────────────────────────────────────────
    FIXED_SPREADS = 17  # spreads 1-17 (References moved to end)
    SPREADS_PER_IV = 3
    iv_spread_count = len(interventions) * SPREADS_PER_IV
    total_spreads = FIXED_SPREADS + len(analyses) + iv_spread_count + 1

    # ── Build spread labels (JS array) ────────────────────────────────────
    fixed_labels = [
        "I", "II // SYSTEM",
        "III // THEORY A", "IV // THEORY B", "V // THEORY C",
        "VI // CATALOG",
        "VII // 1988 NODE", "VIII // 1988 RENDER",
        "IX // 1992 NODE", "X // 1992 RENDER",
        "XI // 1994 NODE", "XII // 1994 RENDER",
        "XIII // ROSSI", "XIV // NEU MUSEUM",
        "XV // ZEITZ MOCAA", "XVI // GENBAKU", "XVII // DO HO SUH"
    ]
    ana_labels = [f"ANALYSIS // {esc(a['name']).upper()}" for a in analyses]
    iv_labels = []
    for i, iv in enumerate(interventions):
        tag = f"IV_{i+1:02d}"
        iv_labels += [f"{tag} // NARRATIVE", f"{tag} // DIAGRAM", f"{tag} // MASTERPLAN"]

    ref_labels = ["XVIII // REFERENCES"]
    all_labels = fixed_labels + ana_labels + iv_labels + ref_labels
    labels_js  = ", ".join(f'"{l}"' for l in all_labels)

    # ── TOC ───────────────────────────────────────────────────────────────
    toc_lines = [f"{i+1:02d} // {l}" for i, l in enumerate(all_labels)]
    toc_text  = "\n".join(toc_lines)

    # ── Build binary texture data ─────────────────────────────────────────
    binary_data = get_data('1988_trailer_binary_strata.txt')[:4000]

    # ── Assemble fixed spreads ────────────────────────────────────────────
    fixed_html = build_fixed_spreads(
        binary_data, abs_chunks,
        (v88, v92, v94),
        (yb_1, yb_2),
        {
            'jsons_bins': (json_88, bin_88, json_92, bin_92, json_94, bin_94),
            'images': (rossi, neu_l, neu_r, zeitz_l, zeitz_r,
                       genbaku_l, genbaku_r, dosuh_l, dosuh_r)
        },
        arch_memory, references, pipeline_data, toc_text, fixed_labels
    )

    # ── Assemble precedent analyses spreads ───────────────────────────────
    ana_html, _, next_n = build_precedent_analysis_spreads(analyses, FIXED_SPREADS + 1)

    # ── Assemble intervention spreads ─────────────────────────────────────
    iv_html, _ = build_intervention_spreads(interventions, next_n)

    # ── Assemble references spread ────────────────────────────────────────
    ref_n = total_spreads
    ref_html = f'''
        <div class="spread" id="spread-{ref_n}">
            <div class="page-side left-page">
                <div class="grid-layout">
                    <h2 class="page-header">{ref_n:02d} // References</h2>
                    <div class="vessel vessel-span-12">
                        <pre style="color:#555; font-size:0.7rem;">{esc(references)}</pre>
                    </div>
                </div>
            </div>
            <div class="page-side right-page">
                <div class="grid-layout">
                    <h2 class="page-header">{ref_n:02d} // System Status</h2>
                    <div class="vessel vessel-span-12">
                        <pre style="color:#333; font-size:0.65rem;">{esc(pipeline_data)}</pre>
                    </div>
                </div>
            </div>
        </div>'''

    # ── Write final HTML ──────────────────────────────────────────────────
    print("   > Assembling HTML...")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Machine // Palimpsest Zine</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <style>{CSS}</style>
</head>
<body>
    <div class="zine-viewer">
        <div class="stability-btn" onclick="resetDegradation()" title="[ MANUAL OVERRIDE ]"></div>
        <div class="binary-texture">{esc(binary_data)}</div>

        <div class="spread-container">
            <div class="spine"></div>
            {fixed_html}
            {ana_html}
            {iv_html}
            {ref_html}
        </div>

        <div class="zine-footer">
            <div class="nav-controls">
                <button onclick="prevSpread()">&#9666; PREV</button>
            </div>
            <span id="page-indicator">I</span>
            <div class="nav-controls">
                <button id="btn-next" onclick="nextSpread()">NEXT &#9656;</button>
            </div>
        </div>
    </div>

    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'dark',
            themeVariables: {{ background: '#050505', primaryColor: '#1a1a2e',
                edgeLabelBackground: '#000', tertiaryColor: '#050505' }} }});

        const totalSpreads = {total_spreads};
        const labels = [{labels_js}];

        let glitchInterval, artifactInterval, degradeTimer1, degradeTimer2;

        function resetDegradation() {{
            document.body.classList.remove('degrading-mild','degrading-severe');
            clearTimeout(degradeTimer1); clearTimeout(degradeTimer2);
            clearInterval(artifactInterval);
            degradeTimer1 = setTimeout(() => {{
                document.body.classList.add('degrading-mild');
                artifactInterval = setInterval(injectArtifact, 4000);
            }}, 30000);
            degradeTimer2 = setTimeout(() => {{
                document.body.classList.remove('degrading-mild');
                document.body.classList.add('degrading-severe');
                setTimeout(() => {{
                    const nextBtn = document.getElementById('btn-next');
                    nextBtn.innerText = "[ REINITIALIZE ]";
                    nextBtn.classList.add('reboot-mode');
                    nextBtn.onclick = () => location.reload();
       