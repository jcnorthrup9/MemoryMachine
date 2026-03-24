import os
import json
import base64
import webbrowser

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
        
        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; padding: 60px; overflow: hidden;}

        h1.zine-title { font-size: 2.5rem; color: var(--accent-glow); margin-bottom: 20px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 10px; word-wrap: break-word; flex-shrink: 0;}
        h2.page-header { color: #888; font-size: 1rem; text-transform: uppercase; margin-bottom: 30px; letter-spacing: 2px; word-wrap: break-word; flex-shrink: 0;}
        
        .text-wrap { white-space: pre-wrap; font-size: clamp(0.9rem, 2vh, 1.15rem); line-height: 1.6; color: #ccc; text-align: justify; word-wrap: break-word; padding-right: 20px; overflow: hidden;}
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; font-family: inherit; font-size: 1rem;}
        .nav-controls button:hover { background: #111; border-color: #666; color: #fff; }

        .img-stack { display: flex; flex-direction: column; gap: 20px; width: 100%; flex: 1; min-height: 0; justify-content: center; margin-top: 10px; }
        .img-box { position: relative; width: 100%; border: 1px solid #333; background: #080808; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; flex: 1; min-height: 0; }
        .img-box.dashed { border: 1px dashed #444; }
        .img-box img { width: 100%; height: 100%; object-fit: cover; }
        .img-label { text-align: center; font-size: 0.8rem; color: #888; padding-top: 10px; text-transform: uppercase; letter-spacing: 1px; white-space: nowrap;}
    </style>
</head>
<body>
    <div class="zine-viewer">
        <div class="spread-container">
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
    summary_path = os.path.join(DATA_DIR, f"{os.path.splitext(filename)[0]}_summary.txt")
    
    # 1. Check if we already have a cached summary saved
    if os.path.exists(summary_path):
        with open(summary_path, 'r', encoding='utf-8') as f:
            return f.read()
            
    if not os.path.exists(path):
        return f"[ DATA MISSING FOR {topic} ]"
        
    api_key = os.environ.get("GEMINI_API_KEY") 
    
    # 2. If we have the API key, generate the summary and save it
    if genai and api_key:
        try:
            print(f"🧠 Asking Gemini to synthesize data for {topic}...")
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()[:15000]
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            prompt = f"You are an architectural theorist. Extract the key spatial parameters, atmospheric qualities, and historical data about {topic} from the provided text. Present this as a concise, structured list of 'Parsed Data' (bullet points, short phrases) suitable for a presentation slide. Do not write a paragraph blurb. Use plain text formatting with dashes for bullets, no markdown asterisks or bolding.\n\nDATA:\n{text}"
            response = model.generate_content(prompt)
            summary = response.text.strip()
            
            # Cache the result so we don't need the API next time
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary)
            return summary
        except Exception as e:
            print(f"⚠️ API Error: {e}")

    # 3. If no API key and no cache, use high-quality fallbacks
    print(f"⚠️ No API key or cache found for {topic}. Using fallback data.")
    fallbacks = {
        'Bottega Louie': "- High, vaulted ceilings producing reverberating acoustics\n- Bright, Parisian-inspired white and gold aesthetic\n- Symmetrical displays of vibrant macarons\n- Active, open-kitchen wood-fired pizza ovens",
        'O.T. Johnson Building': "- Seven-story Romanesque Revival structural logic\n- Iron and glass ground floor with expansive visibility\n- Glazed pressed-brick facade\n- Hidden archways obscured by subsequent architectural interventions",
        'Nakagin Capsule Tower': "- 140 modular capsules attached to two central concrete cores\n- 1.3m iconic circular windows acting as primary viewing apertures\n- Metabolism architectural ideology focused on organic growth\n- Rigid dimensional constraints: 2.5m x 4.0m x 2.5m capsules",
        'Pershing Square': "- 5-acre urban public square in Downtown Los Angeles\n- Radical 1992 postmodern redesign by Ricardo Legorreta\n- Bold geometric stucco massings in pink, purple, and yellow\n- Extensively documented spatial interventions and subsequent erasures"
    }
    
    return fallbacks.get(topic, f"[ AI SUMMARY PENDING FOR {topic} ]")

def build_payload():
    """Generates the content payload used by both HTML and Figma."""
    def get_single_image(rel_path):
        img_path = os.path.join(BASE_DIR, *rel_path.split('/'))
        
        if not os.path.exists(img_path):
            for ext in ['.png', '.webp', '.jpg', '.jpeg', '.tif']:
                if os.path.exists(img_path + ext):
                    img_path = img_path + ext
                    break
            if not os.path.exists(img_path):
                base_p = os.path.splitext(img_path)[0]
                for ext in ['.png', '.webp', '.jpg', '.jpeg', '.tif']:
                    if os.path.exists(base_p + ext):
                        img_path = base_p + ext
                        break
                    
        if os.path.exists(img_path):
            print(f"   [+] Loaded Hero Image: {rel_path}")
            with open(img_path, "rb") as img_file:
                b64 = base64.b64encode(img_file.read()).decode('utf-8')
            ext = os.path.splitext(img_path)[1].lower()
            mime = "image/png" if ext == '.png' else "image/webp" if ext == '.webp' else "image/jpeg"
            return {"image": b64, "mime_type": mime}
        print(f"   [-] Hero Image Missing: {img_path}")
        return None

    def make_grid(items, count=2):
        padded = []
        for i in range(count):
            if i < len(items):
                item = items[i]
                img_path = os.path.join(BASE_DIR, *item['image_path'].split('/')) if item.get('image_path') else ""
                
                if img_path and not os.path.exists(img_path):
                    base_p = os.path.splitext(img_path)[0]
                    for ext in ['.png', '.webp', '.jpg', '.jpeg', '.tif']:
                        if os.path.exists(base_p + ext):
                            img_path = base_p + ext
                            break
                            
                base64_data = None
                mime_type = "image/jpeg"
                if img_path and os.path.isfile(img_path):
                    print(f"   [+] Loaded Image: {item['image_path']}")
                    with open(img_path, "rb") as img_file:
                        base64_data = base64.b64encode(img_file.read()).decode('utf-8')
                    ext = os.path.splitext(img_path)[1].lower()
                    if ext == '.png': mime_type = "image/png"
                    elif ext == '.webp': mime_type = "image/webp"
                else:
                    print(f"   [-] Image Missing: {item.get('image_path') or 'Empty Path'}")
                padded.append({"label": item['label'], "image": base64_data, "mime_type": mime_type, "object_position": item.get('object_position', 'center')})
            else:
                padded.append({"label": "[ PENDING // NO DATA ]", "image": None})
        return padded

    def get_image_items(relative_folder, label_prefix):
        full_path = os.path.join(BASE_DIR, *relative_folder.split('/'))
        items = []
        if os.path.exists(full_path):
            valid_exts = {'.jpg', '.jpeg', '.png', '.tif', '.webp'}
            files = sorted([f for f in os.listdir(full_path) if os.path.splitext(f)[1].lower() in valid_exts])
            for idx, f in enumerate(files):
                rel_path = f"{relative_folder}/{f}"
                items.append({"label": f"{label_prefix} {idx+1:02d}", "image_path": rel_path})
        return items

    def split_items(items):
        return items[:2], items[2:4]

    def get_first_item(items, fallback_label):
        return items[0] if items else {"label": fallback_label, "image_path": ""}

    # Bottega Louie Comparison Setup
    bl_ext_items = get_image_items("archive/render_output/bottegaLouieExterior", "GEN EXT")
    bl_int_items = get_image_items("archive/render_output/bottegaLouieInterior", "GEN INT")
    bl_actual_items = get_image_items("archive/reference_images/BottegaLouie", "ACTUAL")
    
    bl_left = [
        {"label": "ACTUAL 01", "image_path": "archive/reference_images/BottegaLouie/Boutique.jpg"},
        {"label": "ACTUAL 02", "image_path": "archive/reference_images/BottegaLouie/InteriorPano.jpg"}
    ]
    bl_right = [
        {"label": "GEN EXT 01", "image_path": "archive/render_output/bottegaLouieInterior/flux2_klein_00077_.png"}, 
        get_first_item(bl_int_items, "GEN INT")
    ]

    ot_ext_items = get_image_items("archive/render_output/OTjohnsonExterior", "OT EXT")
    ot_ext_left, ot_ext_right = split_items(ot_ext_items)

    nakagin_ext_items = get_image_items("archive/render_output/nakaginExterior", "NAKAGIN EXT")
    nakagin_ext_left, nakagin_ext_right = split_items(nakagin_ext_items)

    ps_actual_items = get_image_items("archive/reference_images/PershingSquare", "ACTUAL")
    ps_gen_items = get_image_items("archive/render_output/pershingSquare", "GEN")
    
    ps_left = [
        {"label": "CV ANALYSIS", "image_path": "data/pershing_satellite_analyzed.jpg"},
        {"label": "GENERATED MASTERPLAN", "image_path": "archive/render_output/intervention_masterplan_capture.png"}
    ]
    ps_right = [
        get_first_item(ps_gen_items, "GEN 01"),
        get_first_item(ps_gen_items[1:] if len(ps_gen_items) > 1 else [], "GEN 02")
    ]

    bottega_summary = get_ai_summary('bottega_louie_reviews.txt', 'Bottega Louie')
    ot_summary = get_ai_summary('ot_johnson_data.txt', 'O.T. Johnson Building')
    nakagin_summary = get_ai_summary('nakagin.txt', 'Nakagin Capsule Tower')
    pershing_summary = get_ai_summary('pershing_square.txt', 'Pershing Square')

    payload = {
        "deck_title": "Memory Machine // Presentation Deck",
        "slides": [
            {
                "type": "title_slide",
                "title": "THE MACHINE THAT FORGETS",
                "subtitle": "Collective Memory & Architectural Hallucination",
                "hero_image": get_single_image("archive/render_output/front_cover.jpg")
            },
            {
                "type": "workflow_slide",
                "title": "01 // THE MACHINE WORKFLOW",
                "steps": [
                    {"title": "DATA HARVEST", "desc": "Scraping historical archives, visitor reviews, and spatial coordinates."},
                    {"title": "SPATIAL PARSING", "desc": "Extracting hard dimensional limits and atmospheric memory fragments."},
                    {"title": "GENERATION", "desc": "Procedurally rebuilding the structural massing via scripts."},
                    {"title": "HALLUCINATION", "desc": "Applying memory decay and material inference via AI visual workflows."},
                    {"title": "SYNTHESIS", "desc": "Compiling the forensic architectural dossier."}
                ]
            },
            {
                "type": "text_slide",
                "title": "02 // COLLECTIVE MEMORY",
                "body": "Memory is not a static archive, but an unstable process of encoding, retrieval, and decay; it shifts, collapses, and rewrites itself constantly. In the last decade or so, 'artificial intelligence' has been exposed as a reflection of how memory operates, and within this operation are its inherent biases, fractures, and capacity for curiosity and invention.\n\nArchitecture contains memory. Spaces contain memories, old walls are torn down, types of architectural witness marks are left, with tooling marks and bits of material leftovers. Many of these are hidden below the surface, covered by fresh gypsum and spackle, left to only be discovered by the next entity that tears down these walls.\n\nThese collisions of old and new produce moments of dissonance, where architectural time collapses into a single frame."
            },
            {
                "type": "text_and_image_slide",
                "title": "03 // BOTTEGA LOUIE: PARSED DATA",
                "body": bottega_summary,
                "right_title": "BOTTEGA LOUIE INTERIOR",
                "right_grid": make_grid(bl_int_items, count=2)
            },
            {
                "type": "grid_slide",
                "title": "04 // BOTTEGA LOUIE: VISUAL PALIMPSEST",
                "left_title": "PRECEDENT ARCHIVE",
                "right_title": "GENERATED GEOMETRY",
                "left_grid": make_grid(bl_left),
                "right_grid": make_grid(bl_right)
            },
            {
                "type": "text_slide",
                "title": "05 // O.T. JOHNSON: PARSED DATA",
                "body": ot_summary
            },
            {
                "type": "grid_slide",
                "title": "06 // O.T. JOHNSON: EXTERIOR",
                "left_title": "GENERATED EXTERIOR I",
                "right_title": "GENERATED EXTERIOR II",
                "left_grid": make_grid(ot_ext_left),
                "right_grid": make_grid(ot_ext_right)
            },
            {
                "type": "text_and_image_slide",
                "title": "07 // NAKAGIN CAPSULE TOWER: PARSED DATA",
                "body": nakagin_summary,
                "right_title": "GENERATED GEOMETRY",
                "right_grid": make_grid([
                    {"label": "NAKAGIN TOWER", "image_path": "archive/reference_images/nakaginCapsuleTower/2362d526d98b4e9d982ec03b92f753db.f5fb7444.jpg"}
                ], count=1)
            },
            {
                "type": "grid_slide",
                "title": "08 // NAKAGIN CAPSULE TOWER: EXTERIOR",
                "left_title": "GENERATED EXTERIOR I",
                "right_title": "GENERATED EXTERIOR II",
                "left_grid": make_grid(nakagin_ext_left),
                "right_grid": make_grid(nakagin_ext_right)
            },
            {
                "type": "text_and_image_slide",
                "title": "09 // PERSHING SQUARE: PARSED DATA",
                "body": pershing_summary,
                "right_title": "SITE & PRECEDENT",
                "right_grid": make_grid([
                    {"label": "SATELLITE CAPTURE", "image_path": "data/pershing_satellite.jpg"},
                    {"label": "LEGORRETA 07", "image_path": "archive/reference_images/PershingSquare/_Pershing_Square_Lourdes_Legorreta_07_.jpg"}
                ], count=2)
            },
            {
                "type": "grid_slide",
                "title": "10 // PERSHING SQUARE: VISUAL PALIMPSEST",
                "left_title": "SITE MASTERPLAN",
                "right_title": "GENERATED SECTIONS",
                "left_grid": make_grid(ps_left),
                "right_grid": make_grid(ps_right)
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
            hero_html = ""
            if slide.get("hero_image") and slide["hero_image"].get("image"):
                hero = slide["hero_image"]
                hero_html = f'<img src="data:{hero["mime_type"]};base64,{hero["image"]}" style="width: 100%; height: 100%; object-fit: cover;">'

            slides_html += f'''
                <div class="page-side left-page" style="justify-content: center;">
                    <h1 class="zine-title" style="font-size: 3.5rem;">{slide["title"]}</h1>
                    <h2 class="page-header" style="font-size: 1.2rem; border: none;">{slide["subtitle"]}</h2>
                </div>
                <div class="page-side right-page" style="padding: 0;">{hero_html}</div>
            '''
        elif slide["type"] == "text_slide":
            slides_html += f'''
                <div class="page-side left-page">
                    <h1 class="zine-title" style="font-size: 2.2rem;">{slide["title"]}</h1>
                    <div class="text-wrap">{slide["body"]}</div>
                </div>
                <div class="page-side right-page"></div>
            '''
        elif slide["type"] == "workflow_slide":
            steps_html = ""
            for i, step in enumerate(slide["steps"]):
                arrow = '<div style="display: flex; align-items: center; justify-content: center; padding: 0 15px; color: #666; font-size: 2rem;">&rarr;</div>' if i < len(slide["steps"]) - 1 else ''
                steps_html += f'''
                    <div style="flex: 1; border: 1px solid #333; background: #0a0a0a; padding: 20px; display: flex; flex-direction: column;">
                        <h3 style="color: var(--accent-glow); margin-top: 0; font-size: 1rem; border-bottom: 1px solid #222; padding-bottom: 10px;">{step['title']}</h3>
                        <p style="color: #aaa; font-size: 0.9rem; line-height: 1.4; margin: 0;">{step['desc']}</p>
                    </div>
                    {arrow}
                '''
            slides_html += f'''
                <div class="page-side left-page" style="width: 100%; padding-right: 60px;">
                    <h1 class="zine-title" style="font-size: 2.2rem;">{slide["title"]}</h1>
                    <div style="display: flex; flex-direction: row; margin-top: 40px; align-items: stretch; height: 250px;">
                        {steps_html}
                    </div>
                </div>
                <div class="page-side right-page" style="display:none;"></div>
            '''
        elif slide["type"] == "text_and_image_slide":
            right_boxes = ""
            for item in slide.get("right_grid", []):
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                right_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div><div class="img-label">{item["label"]}</div></div>'

            slides_html += f'''
                <div class="page-side left-page">
                    <h1 class="zine-title" style="font-size: 2.2rem;">{slide["title"]}</h1>
                    <div class="text-wrap">{slide["body"]}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div class="img-stack">{right_boxes}</div>
                </div>
            '''
        elif slide["type"] == "grid_slide":
            left_boxes = ""
            for item in slide["left_grid"]:
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                left_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div><div class="img-label">{item["label"]}</div></div>'
            
            right_boxes = ""
            for item in slide["right_grid"]:
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                right_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div><div class="img-label">{item["label"]}</div></div>'

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["left_title"]}</h2>
                    <div class="img-stack">{left_boxes}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div class="img-stack">{right_boxes}</div>
                </div>
            '''
        slides_html += '</div>\n'

    html = HTML_TEMPLATE.replace('{{SLIDES_HTML}}', slides_html)
    html = html.replace('{{TOTAL_SPREADS}}', str(len(payload["slides"])))

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
        
    print(f"✅ HTML DECK COMPILED SUCCESSFULLY: {OUTPUT_FILE}\n")

    # 3. Automatically open the file in the default web browser
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    compile_deck()