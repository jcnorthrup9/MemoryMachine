import os
import json
import csv
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_FILE = os.path.join(BASE_DIR, 'html', 'digitalPalimpsest.html')

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Machine // Palimpsest Zine</title>
    <style>
        :root {
            --bg-color: #050505;
            --text-color: #e0e0e0;
            --accent-glow: #fff4ca;
            --border-dim: #222;
        }
        * { box-sizing: border-box; }
        body { background-color: var(--bg-color); color: var(--text-color); font-family: 'Courier New', Courier, monospace; margin: 0; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        .zine-viewer { width: 96vw; max-width: 1800px; height: 92vh; background-color: #000; border: 1px solid var(--border-dim); display: flex; flex-direction: column; position: relative; }
        .spread-container { flex-grow: 1; display: flex; position: relative; overflow: hidden; z-index: 2; }
        .spine { position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: var(--border-dim); z-index: 10; }
        
        .binary-texture { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0.05; font-size: 0.6rem; line-height: 1.1; color: #fff; overflow: hidden; z-index: 1; user-select: none; word-wrap: break-word; }

        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; }
        .left-page { padding: 60px 100px 60px 60px; } 
        .right-page { padding: 60px 60px 60px 100px; } 

        .grid-layout { display: grid; grid-template-columns: repeat(12, 1fr); grid-template-rows: auto 1fr; gap: 20px; height: 100%; }
        
        .abstract-flow { column-count: 2; column-gap: 40px; column-rule: 1px solid #1a1a1a; text-align: justify; font-size: 0.85rem; line-height: 1.6; color: #bbb; height: 100%; column-fill: auto; overflow: hidden; grid-column: 1 / -1; }
        
        .vessel { display: flex; flex-direction: column; height: 100%; overflow: hidden; justify-content: center; }
        .vessel-span-8 { grid-column: span 8; }
        .vessel-span-4 { grid-column: span 4; border-left: 1px solid var(--border-dim); padding-left: 20px; }
        
        .vignette { border-left: 1px solid var(--accent-glow); padding-left: 20px; margin-bottom: 30px; font-size: 0.85em; color: #aaa; text-align: left; }
        h1.zine-title { font-size: 3rem; color: var(--accent-glow); margin-bottom: 5px; }
        h2.page-header { color: #444; font-size: 0.8rem; text-transform: uppercase; border-bottom: 1px solid #111; padding-bottom: 10px; margin-bottom: 30px; flex-shrink: 0; grid-column: 1 / -1; }
        
        pre { margin: 0; font-size: 0.7rem; line-height: 1.4; color: #555; white-space: pre-wrap; }
        .json-block { color: #88ff88; text-align: left; width: 100%; }
        .binary-block { color: #444; letter-spacing: 3px; text-align: center; font-size: 0.65rem; }
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 20; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; }

        .matrix-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; width: 100%; margin-top: 20px; }
        .matrix-item { aspect-ratio: 1; background: #080808; border: 1px solid #111; display: flex; align-items: center; justify-content: center; overflow: hidden; }
        .matrix-item img { width: 100%; height: 100%; object-fit: cover; }
        
        .bleed-center { position: absolute; left: -100px; width: calc(100% + 160px); top: 20%; z-index: 0; opacity: 0.8; mix-blend-mode: screen; }
    </style>
</head>
<body>
    <div class="zine-viewer">
        <div class="binary-texture">{{BINARY_DATA}}</div>
        <div class="spread-container">
            <div class="spine"></div>

            <div class="spread active" id="spread-1">
                <div class="page-side left-page" style="background-color: #030303; z-index: 10;"></div>
                <div class="page-side right-page" style="background-color: #000; z-index: 10;">
                    <div style="margin: auto 0;">
                        <h1 class="zine-title">Forensic_Palimpsest</h1>
                        <div style="letter-spacing: 5px; color: #444; margin-bottom: 40px;">THE MEMORY MACHINE // JOHN C. NORTHRUP II</div>
                        <img src="../archive/render_output/front_cover.jpg" style="width: 100%; border: 1px solid var(--border-dim); filter: grayscale(100%);">
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-2">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">01 // System Manifest & Index</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre style="color: #666; font-size: 0.65rem;">{{SYSTEM_DATA}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">02 // The Machine That Forgets // A</h2>
                        <div class="abstract-flow">{{ABSTRACT_1}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-3">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">02 // The Machine That Forgets // B</h2>
                        <div class="abstract-flow">{{ABSTRACT_2}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">02 // The Machine That Forgets // C</h2>
                        <div class="abstract-flow">{{ABSTRACT_3}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-4">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">03 // Forensic Asset Catalog</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <div class="matrix-grid">{{ASSET_GRID}}</div>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">04 // Node: {{NODE_ID}} // Narrative</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; justify-content: flex-start; overflow-y: auto;">
                            {{NARRATIVE_DATA}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-5">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">05 // Structural Logic // JSON</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                             <pre class="json-block" style="font-size: 0.55rem;">{{JSON_DATA}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">06 // Forensic Strata // Binary</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre class="binary-block">{{BINARY_DATA}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-6">
                <div class="page-side left-page" style="background-color: #030303;"></div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">07 // Visual Output // Rhino Arctic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <img src="../archive/render_output/1988_trailer.png" class="bleed-center">
                        </div>
                    </div>
                </div>
            </div>

        </div>

        <footer class="zine-footer">
            <div id="page-indicator">I</div>
            <div class="nav-controls">
                <button onclick="prevSpread()">[ PREV ]</button>
                <button onclick="nextSpread()">[ NEXT ]</button>
            </div>
        </footer>
    </div>

    <script>
        let currentSpread = 1;
        const totalSpreads = 6;
        function showSpread(n) {
            document.querySelectorAll('.spread').forEach(s => s.classList.remove('active'));
            document.getElementById(`spread-${n}`).classList.add('active');
            const labels = ["I", "II // INDEX", "III // THEORY", "IV // CATALOG & NARRATIVE", "V // LOGIC & STRATA", "VI // OUTPUT"];
            document.getElementById('page-indicator').innerText = labels[n-1];
            currentSpread = n;
        }
        function nextSpread() { currentSpread < totalSpreads ? showSpread(currentSpread + 1) : showSpread(1); }
        function prevSpread() { currentSpread > 1 ? showSpread(currentSpread - 1) : showSpread(totalSpreads); }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') nextSpread();
            if (e.key === 'ArrowLeft') prevSpread();
        });
    </script>
</body>
</html>"""

def get_data(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return f"[MISSING DATA: {filename}]"

def get_asset_grid_html():
    manifest_path = os.path.join(DATA_DIR, 'asset_manifest.csv')
    grid_html = ""
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert absolute project path to relative HTML path (../archive/...)
                # Assuming CSV path is like "archive/assets/thumbnails/image.jpg"
                rel_path = "../" + row['Thumbnail_Path'].replace("\\", "/")
                grid_html += f'<div class="matrix-item"><img src="{rel_path}"></div>'
    # Pad with empty items if needed to maintain grid structure (optional)
    return grid_html

def get_redacted_reviews(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return f"[MISSING DATA: {filename}]"
    
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Redact all variations of the business name (case-insensitive)
    redacted = re.sub(r'(?i)bottega louie\'s|bottega louie|bottega louis|botegga louie|bottega', '[BUSINESS NAME]', content)
    
    # Split by double-newlines so each block of the review becomes its own vignette
    paragraphs = [p.strip() for p in redacted.split('\n\n') if p.strip()]
    return "---".join(paragraphs)

def compile_zine():
    print("\n--- Waking up the Memory Machine ---")
    
    system_data = get_data('system_manifest.txt')
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    binary = get_data('1988_trailer_binary_strata.txt')
    asset_grid = get_asset_grid_html()
    
    # Ingest the manually scraped Yelp reviews instead of the trailer narrative
    narrative = get_redacted_reviews('bottega_louie_reviews.txt')

    # Check if a dynamic target has been generated, otherwise use default
    target_file = 'target_node.json' if os.path.exists(os.path.join(DATA_DIR, 'target_node.json')) else '1988_trailer_logic.json'
    json_data = get_data(target_file)
    
    # extract node_id for header
    node_id = "UNKNOWN_NODE"
    try:
        if not json_data.startswith("[MISSING"):
            data_obj = json.loads(json_data)
            node_id = data_obj.get("node_id", "1988_TRAILER")
    except:
        pass

    words = abstract.split()
    if len(words) > 0:
        chunk = len(words) // 3 + 1
        abs_1 = " ".join(words[:chunk])
        abs_2 = " ".join(words[chunk:chunk*2])
        abs_3 = " ".join(words[chunk*2:])
    else:
        abs_1 = abs_2 = abs_3 = ""

    snippets = narrative.split('---')
    vignette_html = "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    print("Injecting data into HTML matrix...")
    html = HTML_TEMPLATE.replace('{{ABSTRACT_1}}', abs_1)
    html = html.replace('{{ABSTRACT_2}}', abs_2)
    html = html.replace('{{ABSTRACT_3}}', abs_3)
    html = html.replace('{{SYSTEM_DATA}}', system_data)
    html = html.replace('{{NARRATIVE_DATA}}', vignette_html)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{NODE_ID}}', node_id)
    html = html.replace('{{BINARY_DATA}}', binary)
    html = html.replace('{{ASSET_GRID}}', asset_grid)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ BUILD SUCCESSFUL: {OUTPUT_FILE} has been updated!\n")

if __name__ == "__main__":
    compile_zine()