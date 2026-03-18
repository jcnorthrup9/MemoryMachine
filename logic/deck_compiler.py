import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_FILE = os.path.join(BASE_DIR, 'html', 'presentation_deck.html')

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Memory Machine // Presentation Deck</title>
    <style>
        :root {
            --bg-color: #050505;
            --text-color: #e0e0e0;
            --accent-glow: #fff4ca;
            --border-dim: #222;
            --trans-speed: 0.4s;
        }
        * { box-sizing: border-box; }
        body { background-color: var(--bg-color); color: var(--text-color); font-family: 'Courier New', Courier, monospace; margin: 0; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        .zine-viewer { width: 96vw; max-width: 1800px; height: 92vh; background-color: #000; border: 1px solid var(--border-dim); display: flex; flex-direction: column; position: relative; }
        .spread-container { flex-grow: 1; display: flex; position: relative; overflow: hidden; z-index: 2; }
        .spine { position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: var(--border-dim); z-index: 10; }
        
        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; padding: 60px; overflow-y: auto;}
        .left-page { padding-right: 100px; } 
        .right-page { padding-left: 100px; } 

        h1.zine-title { font-size: 2.5rem; color: var(--accent-glow); margin-bottom: 20px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 10px;}
        h2.page-header { color: #888; font-size: 1rem; text-transform: uppercase; margin-bottom: 30px; letter-spacing: 2px;}
        
        .vignette { border-left: 2px solid var(--accent-glow); padding-left: 20px; margin-bottom: 20px; font-size: 1rem; color: #ccc; line-height: 1.5; background: rgba(255,255,255,0.02); padding: 15px 15px 15px 20px;}
        
        pre.markdown-block { background: #0a0a0a; border: 1px solid #222; padding: 20px; color: #88ff88; font-size: 0.85rem; line-height: 1.6; white-space: pre-wrap; overflow-x: hidden; }
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; font-family: inherit; font-size: 1rem;}
        .nav-controls button:hover { background: #111; border-color: #666; color: #fff; }

        .image-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; width: 100%; }
        .image-card { display: flex; flex-direction: column; background: #080808; border: 1px solid #222; padding: 10px; }
        .image-card img { width: 100%; aspect-ratio: 1; object-fit: cover; border: 1px solid #111; }
        .image-label { text-align: center; font-size: 0.75rem; color: #888; margin-top: 10px; text-transform: uppercase; letter-spacing: 1px; }
        
        .full-img { width: 100%; height: auto; border: 1px solid #333; max-height: 60vh; object-fit: contain; }
    </style>
</head>
<body>
    <div class="zine-viewer">
        <div class="spread-container">
            <div class="spine"></div>

            <!-- SPREAD 1: PRECEDENTS -->
            <div class="spread active" id="spread-1">
                <div class="page-side left-page">
                    <h1 class="zine-title">01 // Architectural Memory Precedents</h1>
                    <div class="vignette"><strong>Aldo Rossi:</strong> Architecture as a permanent artifact that survives its original function, holding the collective memory of the city.</div>
                    <div class="vignette"><strong>Do Ho Suh:</strong> Spatial memory rendered as translucent fabric. Architecture as a ghostly, transportable shell of personal history.</div>
                    <div class="vignette"><strong>Neues Museum & Zeitz MOCAA:</strong> The palimpsest. Carving into the old to reveal the strata of history rather than overwriting it entirely.</div>
                </div>
                <div class="page-side right-page">
                    <h2 class="page-header">Visual Reference Matrix</h2>
                    <div class="image-grid">
                        <div class="image-card"><img src="../archive/precedents/aldo_rossi.jpg"><div class="image-label">Aldo Rossi // Urban Artifact</div></div>
                        <div class="image-card"><img src="../archive/precedents/dohosuh1.jpg"><div class="image-label">Do Ho Suh // Ghost Architecture</div></div>
                        <div class="image-card"><img src="../archive/precedents/neues_museum.jpg"><div class="image-label">Neues Museum // Historic Strata</div></div>
                        <div class="image-card"><img src="../archive/precedents/zeitz_mocaa.jpg"><div class="image-label">Zeitz MOCAA // Subtractive Void</div></div>
                    </div>
                </div>
            </div>

            <!-- SPREAD 2: BOTTEGA DATA -->
            <div class="spread" id="spread-2">
                <div class="page-side left-page">
                    <h1 class="zine-title">02 // Node: Bottega Louie</h1>
                    <h2 class="page-header">Data Extraction // Crowdsourced Memory</h2>
                    <div class="vignette">"Its high ceilings, beautiful white walls, and fresh flour decorations are luxurious and old world gorgeous. Even the cacophony of voices that echo off the large ceilings add to the luxurious, Italian glow."</div>
                    <div class="vignette">"The place is huge, but feels stark with the white walls. They call it minimalist, I guess. It IS very loud due to the wall-to-wall marble."</div>
                    <div class="vignette">"A beautiful pastries section right when you walk in with all the artful creation in the glass display. The open kitchen adds to the vibe, letting you watch the action."</div>
                </div>
                <div class="page-side right-page">
                    <h2 class="page-header">Generated Markdown Logic</h2>
                    <pre class="markdown-block">{{BOTTEGA_MARKDOWN}}</pre>
                </div>
            </div>

            <!-- SPREAD 3: BOTTEGA VISUALS -->
            <div class="spread" id="spread-3">
                <div class="page-side left-page">
                    <h1 class="zine-title">03 // Bottega Louie Synthesis</h1>
                    <h2 class="page-header">AI Generated Hallucinations</h2>
                    <!-- Placeholder paths for your AI renders -->
                    <div class="image-card" style="margin-bottom: 20px;">
                        <img class="full-img" src="../archive/render_output/bottega_ai_exterior.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'">
                        <div class="image-label">AI Render // Exterior Proxy</div>
                    </div>
                    <div class="image-card">
                        <img class="full-img" src="../archive/render_output/bottega_ai_interior.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'">
                        <div class="image-label">AI Render // Interior Proxy</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <h2 class="page-header">Actual Photographic Artifacts</h2>
                    <div class="image-grid">
                        <div class="image-card"><img src="../archive/reference_images/BottegaLouie/bottega_louie_ref_1.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Facade</div></div>
                        <div class="image-card"><img src="../archive/reference_images/BottegaLouie/bottega_louie_ref_2.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Interior</div></div>
                        <div class="image-card"><img src="../archive/reference_images/BottegaLouie/bottega_louie_ref_3.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Macarons</div></div>
                        <div class="image-card"><img src="../archive/reference_images/BottegaLouie/bottega_louie_ref_4.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Pizza Oven</div></div>
                    </div>
                </div>
            </div>

            <!-- SPREAD 4: OT JOHNSON DATA -->
            <div class="spread" id="spread-4">
                <div class="page-side left-page">
                    <h1 class="zine-title">04 // Node: O.T. Johnson</h1>
                    <h2 class="page-header">Data Extraction // Historic Archives</h2>
                    <div class="vignette">"Constructed in 1902, the seven-story Romanesque Revival building sits prominently at the intersection of 4th and Broadway."</div>
                    <div class="vignette">"The exterior facade is constructed of rich, dark red glazed brick with intricate contrasting stone spandrels, wrapping heavily around the corner."</div>
                    <div class="vignette">"The top floor features distinctive stepped Romanesque brick arches over the windows, capped by a heavy, ornate stone wrap-around cornice."</div>
                </div>
                <div class="page-side right-page">
                    <h2 class="page-header">Generated Markdown Logic</h2>
                    <pre class="markdown-block">{{OT_JOHNSON_MARKDOWN}}</pre>
                </div>
            </div>

            <!-- SPREAD 5: OT JOHNSON VISUALS -->
            <div class="spread" id="spread-5">
                <div class="page-side left-page">
                    <h1 class="zine-title">05 // O.T. Johnson Synthesis</h1>
                    <h2 class="page-header">AI Generated / Rhino Massing</h2>
                    <!-- Placeholder paths for your renders -->
                    <div class="image-card" style="margin-bottom: 20px;">
                        <img class="full-img" src="../archive/render_output/ot_johnson_rhino_iso.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'">
                        <div class="image-label">Rhino System // Isometric Massing</div>
                    </div>
                    <div class="image-card">
                        <img class="full-img" src="../archive/render_output/ot_johnson_ai_render.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'">
                        <div class="image-label">AI Render // Romanesque Details</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <h2 class="page-header">Actual Photographic Artifacts</h2>
                    <div class="image-grid">
                        <div class="image-card"><img src="../archive/reference_images/ot_johnson/ot_johnson_ref_1.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Facade Detail</div></div>
                        <div class="image-card"><img src="../archive/reference_images/ot_johnson/ot_johnson_ref_2.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Street Corner</div></div>
                        <div class="image-card"><img src="../archive/reference_images/ot_johnson/ot_johnson_ref_3.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Historical Era</div></div>
                        <div class="image-card"><img src="../archive/reference_images/ot_johnson/ot_johnson_ref_4.jpg" onerror="this.src='../archive/assets/thumbnails/placeholder.jpg'"><div class="image-label">Archive // Interior Remnant</div></div>
                    </div>
                </div>
            </div>

        </div>

        <footer class="zine-footer">
            <div id="page-indicator">SLIDE 1 of 5</div>
            <div class="nav-controls">
                <button onclick="prevSpread()">&#9664; PREV</button>
                <button onclick="nextSpread()">NEXT &#9654;</button>
            </div>
        </footer>
    </div>

    <script>
        let currentSpread = 1;
        const totalSpreads = 5;
        function showSpread(n) {
            document.querySelectorAll('.spread').forEach(s => s.classList.remove('active'));
            document.getElementById(`spread-${n}`).classList.add('active');
            document.getElementById('page-indicator').innerText = `SLIDE ${n} of ${totalSpreads}`;
            currentSpread = n;
        }
        function nextSpread() { if(currentSpread < totalSpreads) showSpread(currentSpread + 1); }
        function prevSpread() { if(currentSpread > 1) showSpread(currentSpread - 1); }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') nextSpread();
            if (e.key === 'ArrowLeft') prevSpread();
        });
    </script>
</body>
</html>"""

def get_json_as_markdown(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return f"### Missing Data\nCould not locate `{filename}` in the archives."
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        md = f"### NODE: {data.get('node_id', 'UNKNOWN')}\n"
        md += f"**Geo-Lock:** {data.get('geo_lock', {}).get('lat')}, {data.get('geo_lock', {}).get('lon')}\n"
        md += "---\n"
        md += "### Extracted Materials\n"
        for color in data.get('chromatic_palette', []):
            md += f"- **{color['material'].replace('_', ' ').title()}** (Hex: {color['hex']})\n"
            
        md += "---\n"
        md += "### Spatial Massing Elements\n"
        elements = data.get('spatial_logic', [])
        # Just show the top 8 elements to keep the slide clean
        for el in elements[:8]:
            md += f"- **{el['element']}**: {el['instances']} instance(s) [Layer: {el['layer']}]\n"
            
        if len(elements) > 8:
            md += f"- *...and {len(elements) - 8} more elements extracted.*\n"
            
        return md
    except Exception as e:
        return f"Error parsing JSON: {str(e)}"

def compile_deck():
    print("\n--- Compiling Presentation Deck ---")
    
    bottega_md = get_json_as_markdown('target_node.json')
    ot_johnson_md = get_json_as_markdown('target_node_ot_johnson.json')
    
    html = HTML_TEMPLATE.replace('{{BOTTEGA_MARKDOWN}}', bottega_md)
    html = html.replace('{{OT_JOHNSON_MARKDOWN}}', ot_johnson_md)
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ DECK COMPILED SUCCESSFULLY: {OUTPUT_FILE}\n")

if __name__ == "__main__":
    compile_deck()