import os

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
        
        .binary-texture { position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0.05; font-size: 0.6rem; line-height: 1.1; color: #fff; overflow: hidden; z-index: 1; user-select: none; word-wrap: break-word; pointer-events: none; }
        
        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; transition: all 0.4s ease-out; }
        .left-page { padding: 60px 100px 60px 60px; } 
        .right-page { padding: 60px 60px 60px 100px; } 

        .grid-layout { display: grid; grid-template-columns: repeat(12, 1fr); grid-template-rows: auto 1fr; gap: 20px; height: 100%; }
        
        .abstract-flow { column-count: 2; column-gap: 40px; column-rule: 1px solid #1a1a1a; text-align: justify; text-align-last: left; font-size: 0.85rem; line-height: 1.6; color: #bbb; height: 100%; column-fill: balance; overflow: hidden; grid-column: 1 / -1; transition: all 0.4s ease-out; }
        
        .vessel { display: flex; flex-direction: column; height: 100%; overflow: hidden; transition: all 0.4s ease-out; }
        .vessel-span-8 { grid-column: span 8; }
        .vessel-span-4 { grid-column: span 4; border-left: 1px solid var(--border-dim); padding-left: 20px; }
        
        .vignette { border-left: 1px solid var(--accent-glow); padding-left: 20px; margin-bottom: 30px; font-size: 0.85em; color: #aaa; text-align: left; }
        h1.zine-title { font-size: 3rem; color: var(--accent-glow); margin-bottom: 5px; transition: all 0.4s ease-out; }
        h2.page-header { color: #444; font-size: 0.8rem; text-transform: uppercase; border-bottom: 1px solid #111; padding-bottom: 10px; margin-bottom: 30px; flex-shrink: 0; grid-column: 1 / -1; transition: all 0.4s ease-out; }
        
        pre { margin: 0; font-size: 0.7rem; line-height: 1.4; color: #555; white-space: pre-wrap; transition: all 0.4s ease-out; }
        .json-block { color: #88ff88; text-align: left; width: 100%; }
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; }
        .nav-controls button:hover { background: #111; border-color: #444; }

        .matrix-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; }
        .matrix-item { aspect-ratio: 1; background: #080808; border: 1px solid #111; position: relative; overflow: hidden; }
        .matrix-item img { width: 100%; height: 100%; object-fit: cover; object-position: center; display: block; }

        .yearbook-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; width: 100%; }
        .yearbook-entry { display: flex; flex-direction: column; align-items: center; }
        .yearbook-placeholder { width: 100%; aspect-ratio: 1; background: #0a0a0a; border: 1px dashed #333; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.6rem; overflow: hidden; }
        .yearbook-placeholder img { width: 100%; height: 100%; object-fit: cover; }
        .yearbook-label { margin-top: 5px; font-size: 0.55rem; color: #666; text-transform: uppercase; text-align: center; letter-spacing: 1px; }
        
        @keyframes scan { 0% { background-position: 0 0; } 100% { background-position: 0 4px; } }
        .scanlines { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.1) 50%, rgba(0,0,0,0.1)); background-size: 100% 4px; animation: scan 0.2s linear infinite; pointer-events: none; z-index: 50; opacity: 0.4; }

        @keyframes glitch-anim {
            0% { clip-path: polygon(0 2%, 100% 2%, 100% 5%, 0 5%); transform: translate(0, 0) skew(0); }
            20% { clip-path: polygon(0 15%, 100% 15%, 100% 15%, 0 15%); transform: translate(-25px, 2px) skew(40deg); }
            40% { clip-path: polygon(0 10%, 100% 10%, 100% 20%, 0 20%); transform: translate(25px, -2px) skew(-40deg); }
            60% { clip-path: polygon(0 1%, 100% 1%, 100% 2%, 0 2%); transform: translate(15px, 0) skew(15deg); }
            80% { clip-path: polygon(0 33%, 100% 33%, 100% 33%, 0 33%); transform: translate(-15px, 2px) skew(-10deg); }
            100% { clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%); transform: translate(0, 0) skew(0); }
        }

        body.glitch-mode .page-side { animation: glitch-anim 0.6s infinite steps(2); filter: invert(1); }
        body.glitch-mode .left-page { transform: translateX(20px) rotate(-1deg); }
        body.glitch-mode .right-page { transform: translateX(-20px) rotate(1deg); margin-left: -50px; }
        body.glitch-mode h1, body.glitch-mode h2 { animation: glitch-anim 4s infinite linear alternate-reverse; color: #ff0000; text-shadow: 2px 0 #00ff00; }
        body.glitch-mode pre { animation: glitch-anim 1s infinite; opacity: 0.5; }
        body.glitch-mode .binary-texture { animation: glitch-anim 0.2s infinite reverse; color: #00ff00; opacity: 0.2; }
    </style>
</head>
<body class="glitch-mode">
    <div class="zine-viewer">
        <div class="scanlines"></div>
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
                        <h2 class="page-header">01 // Table of Contents</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre style="color: #666; font-size: 1rem;">{{TOC_DATA}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">02 // System Pipeline Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre style="color: #666; font-size: 1rem;">{{PIPELINE_DATA}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-3">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">03 // The Machine That Forgets // I</h2>
                        <div class="abstract-flow">{{ABSTRACT_1}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">04 // The Machine That Forgets // II</h2>
                        <div class="abstract-flow">{{ABSTRACT_2}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-4">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">05 // The Machine That Forgets // III</h2>
                        <div class="abstract-flow">{{ABSTRACT_3}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">06 // The Machine That Forgets // IV</h2>
                        <div class="abstract-flow">{{ABSTRACT_4}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-5">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">07 // The Machine That Forgets // V</h2>
                        <div class="abstract-flow">{{ABSTRACT_5}}</div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">08 // The Machine That Forgets // VI</h2>
                        <div class="abstract-flow">{{ABSTRACT_6}}</div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-6">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">09 // Forensic Asset Catalog // A</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{YEARBOOK_1}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">10 // Forensic Asset Catalog // B</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{YEARBOOK_2}}
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-7">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">11 // Node: 1988_Trailer // Narrative</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            {{NARRATIVE_DATA}}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">12 // Memory Construct // Logic</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <pre class="json-block" style="font-size: 1.1rem;">{{JSON_DATA}}</pre>
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-8">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">13 // Binary Strata</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; justify-content: center; overflow-y: auto;">
                            <pre style="color: #666; font-size: 1.1rem; white-space: pre-wrap;">{{BINARY_DATA}}</pre>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">14 // Rendering Layer</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center; height: 100%; overflow: hidden;">
                            <img src="../archive/render_output/1988_trailer.png" style="max-width: 100%; max-height: 100%; object-fit: contain; border: 1px solid #222; transform: scale(1.75);">
                        </div>
                    </div>
                </div>
            </div>

            <div class="spread" id="spread-9">
                <div class="page-side left-page">
                    <div class="grid-layout">
                        <h2 class="page-header">15 // References</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1;">
                            <div class="abstract-flow">{{REFERENCES_DATA}}</div>
                        </div>
                    </div>
                </div>
                <div class="page-side right-page">
                    <div class="grid-layout">
                        <h2 class="page-header">16 // System Status</h2>
                        <div class="vessel vessel-span-12" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: center;">
                            <div style="color: #333; font-size: 0.8rem;">[ PROCESS TERMINATED ]</div>
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
        const totalSpreads = 9;
        const glitchInterval = setInterval(() => {
            const randomSpread = Math.floor(Math.random() * totalSpreads) + 1;
            showSpread(randomSpread, true);
        }, 200);

        setTimeout(() => {
            clearInterval(glitchInterval);
            document.body.classList.remove('glitch-mode');
            showSpread(1, true);
        }, 1875);

        let currentSpread = 1;
        function showSpread(n, suppressGlitch) {
            if (!suppressGlitch) {
                document.body.classList.add('glitch-mode');
                setTimeout(() => {
                    document.body.classList.remove('glitch-mode');
                }, 260);
            }
            document.querySelectorAll('.spread').forEach(s => s.classList.remove('active'));
            document.getElementById(`spread-${n}`).classList.add('active');
            const labels = ["I", "II // SYSTEM", "III // THEORY A", "IV // THEORY B", "V // THEORY C", "VI // CATALOG", "VII // NARRATIVE", "VIII // RENDER", "IX // REFERENCES"];
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

def compile_zine():
    print("\n--- Waking up the Memory Machine ---")
    
    system_data = get_data('system_manifest.txt')
    
    if "02 // SYSTEM PIPELINE LOGIC" in system_data:
        split_point = "02 // SYSTEM PIPELINE LOGIC"
    else:
        split_point = "SYSTEM PIPELINE LOGIC"

    if split_point in system_data:
        parts = system_data.split(split_point, 1)
        toc_data = parts[0].strip()
        pipeline_data = (split_point + parts[1]).strip()
    else:
        toc_data = system_data
        pipeline_data = ""
    abstract = get_data('thesis_abstract.txt')
    narrative = get_data('1988_trailer_parsed.txt')
    json_data = get_data('1988_trailer_logic.json')
    binary = get_data('1988_trailer_binary_strata.txt')
    references = get_data('references.txt')

    words = abstract.split()
    if len(words) > 0:
        chunk = len(words) // 6 + 1
        abs_1 = " ".join(words[:chunk])
        abs_2 = " ".join(words[chunk:chunk*2])
        abs_3 = " ".join(words[chunk*2:chunk*3])
        abs_4 = " ".join(words[chunk*3:chunk*4])
        abs_5 = " ".join(words[chunk*4:chunk*5])
        abs_6 = " ".join(words[chunk*5:])
    else:
        abs_1 = abs_2 = abs_3 = abs_4 = abs_5 = abs_6 = ""

    snippets = narrative.split('---')
    vignette_html = "".join([f'<div class="vignette">{s.strip()}</div>' for s in snippets if s.strip()])

    thumb_dir = os.path.join(BASE_DIR, 'archive', 'assets', 'thumbnails')
    yearbook_data = []
    if os.path.exists(thumb_dir):
        for f in sorted(os.listdir(thumb_dir)):
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                name = os.path.splitext(f)[0].replace('_', ' ').upper()
                img_tag = f'<img src="../archive/assets/thumbnails/{f}">'
                yearbook_data.append((name, img_tag))

    while len(yearbook_data) < 32:
        yearbook_data.append(("{PLACEHOLDER TEXT}", "PENDING"))

    def make_yearbook_grid(items):
        return '<div class="yearbook-grid">' + "".join([f'<div class="yearbook-entry"><div class="yearbook-placeholder">{content}</div><div class="yearbook-label">{name}</div></div>' for name, content in items]) + '</div>'

    yb_1 = make_yearbook_grid(yearbook_data[:16])
    yb_2 = make_yearbook_grid(yearbook_data[16:32])

    print("Injecting data into HTML matrix...")
    html = HTML_TEMPLATE.replace('{{ABSTRACT_1}}', abs_1)
    html = html.replace('{{ABSTRACT_2}}', abs_2)
    html = html.replace('{{ABSTRACT_3}}', abs_3)
    html = html.replace('{{ABSTRACT_4}}', abs_4)
    html = html.replace('{{ABSTRACT_5}}', abs_5)
    html = html.replace('{{ABSTRACT_6}}', abs_6)
    html = html.replace('{{TOC_DATA}}', toc_data)
    html = html.replace('{{PIPELINE_DATA}}', pipeline_data)
    html = html.replace('{{NARRATIVE_DATA}}', vignette_html)
    html = html.replace('{{JSON_DATA}}', json_data)
    html = html.replace('{{BINARY_DATA}}', binary)
    html = html.replace('{{YEARBOOK_1}}', yb_1)
    html = html.replace('{{YEARBOOK_2}}', yb_2)
    html = html.replace('{{REFERENCES_DATA}}', references)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ BUILD SUCCESSFUL: {OUTPUT_FILE} has been updated!\n")

if __name__ == "__main__":
    compile_zine()