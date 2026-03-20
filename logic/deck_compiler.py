import os
import json
import base64

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    print("⚠️ WARNING: python-dotenv is not installed. Please run: pip install python-dotenv")

try:
    import google.generativeai as genai
except ImportError:
    genai = None

DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_FILE = os.path.join(BASE_DIR, 'html', 'presentation_deck.html')
FIGMA_OUTPUT = os.path.join(DATA_DIR, 'figma_payload.json')

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

        h1.zine-title { font-size: 2.5rem; color: var(--accent-glow); margin-bottom: 20px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 10px; word-wrap: break-word;}
        h2.page-header { color: #888; font-size: 1rem; text-transform: uppercase; margin-bottom: 30px; letter-spacing: 2px; word-wrap: break-word;}
        
        .text-wrap { white-space: pre-wrap; font-size: 1.15rem; line-height: 1.8; color: #ccc; text-align: justify; word-wrap: break-word; padding-right: 20px;}
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; font-family: inherit; font-size: 1rem;}
        .nav-controls button:hover { background: #111; border-color: #666; color: #fff; }

        .grid-3x3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; width: 100%; }
        .grid-box { aspect-ratio: 1; border: 1px solid #333; background: #080808; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; overflow: hidden; }
        .grid-box.dashed { border: 1px dashed #444; }
        .grid-box img { width: 100%; height: 100%; object-fit: cover; }
        .grid-label { position: absolute; bottom: 5px; width: 90%; text-align: center; font-size: 0.65rem; color: #ddd; background: rgba(0,0,0,0.8); padding: 4px; border-radius: 3px; text-transform: uppercase; letter-spacing: 1px;}
    </style>
</head>
<body>
    <div class="zine-viewer">
        <div class="spread-container">
            <div class="spine"></div>
            {{SLIDES_HTML}}
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
        const totalSpreads = {{TOTAL_SPREADS}};
        function showSpread(n) {
            document.querySelectorAll('.spread').forEach(s => s.classList.remove('active'));
            const target = document.getElementById(`spread-${n}`);
            if (target) target.classList.add('active');
            document.getElementById('page-indicator').innerText = `SLIDE ${n} of ${totalSpreads}`;
            currentSpread = n;
        }
        function nextSpread() { if(currentSpread < totalSpreads) showSpread(currentSpread + 1); }
        function prevSpread() { if(currentSpread > 1) showSpread(currentSpread - 1); }
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') nextSpread();
            if (e.key === 'ArrowLeft') prevSpread();
        });
        document.getElementById('page-indicator').innerText = `SLIDE 1 of ${totalSpreads}`;
    </script>
</body>
</html>"""

def get_ai_summary(filename, topic):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return f"[ DATA MISSING FOR {topic} ]"
        
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()[:15000] # Safe limit to avoid token overload
        
    if not genai:
        return "[ GOOGLE-GENERATIVEAI NOT INSTALLED ]\nPlease run: pip install google-generativeai"
        
    api_key = os.environ.get("GEMINI_API_KEY") 
    if not api_key:
        return f"[ GEMINI API KEY MISSING ]\nPlease set the GEMINI_API_KEY environment variable or add it to a .env file."
        
    try:
        print(f"🧠 Asking Gemini to synthesize data for {topic}...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"You are an architectural theorist. Summarize the following spatial and historical data about {topic} into 2 short, punchy paragraphs suitable for a presentation slide. Focus on atmosphere, memory, and architecture. Do not use markdown formatting like asterisks or bolding, just plain text.\n\nDATA:\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[ API ERROR: {e} ]"

def build_payload():
    """Generates the content payload used by both HTML and Figma."""
    def make_grid(items):
        padded = []
        for i in range(9):
            if i < len(items):
                item = items[i]
                img_path = os.path.join(BASE_DIR, *item['image_path'].split('/'))
                base64_data = None
                if os.path.exists(img_path):
                    print(f"   [+] Loaded Image: {item['image_path']}")
                    with open(img_path, "rb") as img_file:
                        base64_data = base64.b64encode(img_file.read()).decode('utf-8')
                else:
                    print(f"   [-] Image Missing: {img_path}")
                padded.append({"label": item['label'], "image": base64_data})
            else:
                padded.append({"label": "[ PENDING // NO DATA ]", "image": None})
        return padded

    def get_image_items(relative_folder, label_prefix):
        full_path = os.path.join(BASE_DIR, *relative_folder.split('/'))
        items = []
        if os.path.exists(full_path):
            valid_exts = {'.jpg', '.jpeg', '.png', '.tif'}
            files = sorted([f for f in os.listdir(full_path) if os.path.splitext(f)[1].lower() in valid_exts])
            for idx, f in enumerate(files):
                rel_path = f"{relative_folder}/{f}"
                items.append({"label": f"{label_prefix} {idx+1:02d}", "image_path": rel_path})
        return items

    def split_items(items):
        return items[:9], items[9:18]

    precedents_items = get_image_items("archive/precedents", "PRECEDENT")
    precedents_left, precedents_right = split_items(precedents_items)

    bl_ext_items = get_image_items("archive/render_output/bottegaLouieExterior", "BL EXT")
    bl_ext_left, bl_ext_right = split_items(bl_ext_items)
    
    bl_int_items = get_image_items("archive/render_output/bottegaLouieInterior", "BL INT")
    bl_int_left, bl_int_right = split_items(bl_int_items)

    ot_ext_items = get_image_items("archive/render_output/OTjohnsonExterior", "OT EXT")
    ot_ext_left, ot_ext_right = split_items(ot_ext_items)

    bottega_summary = get_ai_summary('bottega_louie_reviews.txt', 'Bottega Louie')
    ot_summary = get_ai_summary('ot_johnson_data.txt', 'O.T. Johnson Building')

    payload = {
        "deck_title": "Memory Machine // Presentation Deck",
        "slides": [
            {
                "type": "title_slide",
                "title": "THE MACHINE THAT FORGETS",
                "subtitle": "Collective Memory & Architectural Hallucination"
            },
            {
                "type": "text_slide",
                "title": "01 // COLLECTIVE MEMORY",
                "body": "Memory is not a static archive, but an unstable process of encoding, retrieval, and decay; it shifts, collapses, and rewrites itself constantly. In the last decade or so, 'artificial intelligence' has been exposed as a reflection of how memory operates, and within this operation are its inherent biases, fractures, and capacity for curiosity and invention.\n\nArchitecture contains memory. Spaces contain memories, old walls are torn down, types of architectural witness marks are left, with tooling marks and bits of material leftovers. Many of these are hidden below the surface, covered by fresh gypsum and spackle, left to only be discovered by the next entity that tears down these walls.\n\nThese collisions of old and new produce moments of dissonance, where architectural time collapses into a single frame."
            },
            {
                "type": "grid_slide",
                "title": "02 // PRECEDENTS",
                "left_title": "ANALOGOUS ARCHITECTURE",
                "right_title": "PALIMPSEST & ERASURE",
                "left_grid": make_grid(precedents_left),
                "right_grid": make_grid(precedents_right)
            },
            {
                "type": "text_slide",
                "title": "03 // BOTTEGA LOUIE: SYNTHESIS",
                "body": bottega_summary
            },
            {
                "type": "grid_slide",
                "title": "04 // BOTTEGA LOUIE: EXTERIOR",
                "left_title": "GENERATED EXTERIOR I",
                "right_title": "GENERATED EXTERIOR II",
                "left_grid": make_grid(bl_ext_left),
                "right_grid": make_grid(bl_ext_right)
            },
            {
                "type": "grid_slide",
                "title": "05 // BOTTEGA LOUIE: INTERIOR",
                "left_title": "GENERATED INTERIOR I",
                "right_title": "GENERATED INTERIOR II",
                "left_grid": make_grid(bl_int_left),
                "right_grid": make_grid(bl_int_right)
            },
            {
                "type": "text_slide",
                "title": "06 // O.T. JOHNSON: SYNTHESIS",
                "body": ot_summary
            },
            {
                "type": "grid_slide",
                "title": "07 // O.T. JOHNSON: EXTERIOR",
                "left_title": "GENERATED EXTERIOR I",
                "right_title": "GENERATED EXTERIOR II",
                "left_grid": make_grid(ot_ext_left),
                "right_grid": make_grid(ot_ext_right)
            }
        ]
    }
    return payload

def compile_deck():
    print("\n--- Compiling Presentation Deck ---")
    
    payload = build_payload()
    
    # 1. Export JSON for Figma
    os.makedirs(os.path.dirname(FIGMA_OUTPUT), exist_ok=True)
    with open(FIGMA_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    print(f"✅ FIGMA PAYLOAD GENERATED: {FIGMA_OUTPUT}")
    
    # 2. Build HTML dynamically to perfectly match the Figma slides
    slides_html = ""
    for idx, slide in enumerate(payload["slides"]):
        active = "active" if idx == 0 else ""
        slides_html += f'<div class="spread {active}" id="spread-{idx+1}">\n'
        
        if slide["type"] == "title_slide":
            slides_html += f'''
                <div class="page-side left-page" style="justify-content: center;">
                    <h1 class="zine-title" style="font-size: 3.5rem;">{slide["title"]}</h1>
                    <h2 class="page-header" style="font-size: 1.2rem; border: none;">{slide["subtitle"]}</h2>
                </div>
                <div class="page-side right-page"></div>
            '''
        elif slide["type"] == "text_slide":
            slides_html += f'''
                <div class="page-side left-page">
                    <h1 class="zine-title" style="font-size: 2.2rem;">{slide["title"]}</h1>
                    <div class="text-wrap">{slide["body"]}</div>
                </div>
                <div class="page-side right-page"></div>
            '''
        elif slide["type"] == "grid_slide":
            left_boxes = ""
            for item in slide["left_grid"]:
                if item.get("image"):
                    img_tag = f'<img src="data:image/jpeg;base64,{item["image"]}">'
                    css = "grid-box"
                else:
                    img_tag = ""
                    css = "grid-box dashed"
                left_boxes += f'<div class="{css}">{img_tag}<div class="grid-label">{item["label"]}</div></div>'
            
            right_boxes = ""
            for item in slide["right_grid"]:
                if item.get("image"):
                    img_tag = f'<img src="data:image/jpeg;base64,{item["image"]}">'
                    css = "grid-box"
                else:
                    img_tag = ""
                    css = "grid-box dashed"
                right_boxes += f'<div class="{css}">{img_tag}<div class="grid-label">{item["label"]}</div></div>'

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["left_title"]}</h2>
                    <div class="grid-3x3">{left_boxes}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div class="grid-3x3">{right_boxes}</div>
                </div>
            '''
        slides_html += '</div>\n'

    html = HTML_TEMPLATE.replace('{{SLIDES_HTML}}', slides_html)
    html = html.replace('{{TOTAL_SPREADS}}', str(len(payload["slides"])))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ HTML DECK COMPILED SUCCESSFULLY: {OUTPUT_FILE}\n")

if __name__ == "__main__":
    compile_deck()