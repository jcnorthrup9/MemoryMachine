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
        
        .page-side { width: 50%; height: 100%; display: flex; flex-direction: column; position: relative; z-index: 5; padding: 60px; overflow: visible;}

        h1.zine-title { font-size: 2.5rem; color: var(--accent-glow); margin-bottom: 20px; text-transform: uppercase; border-bottom: 1px solid #333; padding-bottom: 10px; white-space: nowrap; flex-shrink: 0; position: relative; z-index: 20;}
        h2.page-header { color: #888; font-size: 1rem; text-transform: uppercase; margin-bottom: 30px; letter-spacing: 2px; word-wrap: break-word; flex-shrink: 0;}
        
        .text-wrap { white-space: pre-wrap; font-size: 0.9rem; line-height: 1.4; color: #ccc; text-align: justify; word-wrap: break-word; padding-right: 20px; overflow: hidden;}
        
        .spread { display: none; width: 100%; height: 100%; position: absolute; top: 0; left: 0; }
        .spread.active { display: flex; }
        
        .zine-footer { padding: 15px 30px; border-top: 1px solid var(--border-dim); display: flex; justify-content: space-between; align-items: center; font-size: 0.8em; color: #444; background: #000; z-index: 100; position: relative; }
        .nav-controls button { background: none; border: 1px solid #222; color: var(--text-color); padding: 5px 20px; cursor: pointer; font-family: inherit; font-size: 1rem;}
        .nav-controls button:hover { background: #111; border-color: #666; color: #fff; }

        .img-stack { display: flex; flex-direction: column; gap: 20px; width: 100%; flex: 1; min-height: 0; justify-content: center; margin-top: 10px; }
        .img-box { position: relative; width: 100%; border: 1px solid #333; background: #080808; display: flex; flex-direction: column; align-items: center; justify-content: center; overflow: hidden; flex: 1; min-height: 0; }
        .img-box.dashed { border: 1px dashed #444; }
        .img-box img { width: 100%; height: 100%; object-fit: cover; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            themeVariables: {
                background: 'transparent',
                primaryColor: '#080808',
                primaryBorderColor: '#333',
                primaryTextColor: '#ccc',
                lineColor: '#666',
                fontFamily: 'Courier New',
                fontSize: '14px'
            }
        });
    </script>
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
        function nextSpread() { currentSpread < totalSpreads ? showSpread(currentSpread + 1) : showSpread(1); }
        function prevSpread() { currentSpread > 1 ? showSpread(currentSpread - 1) : showSpread(totalSpreads); }
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
        'Nakagin Capsule Tower': "- 140 modular capsules attached to two central concrete cores\n- 1.3m iconic circular windows acting as primary viewing apertures\n- Metabolism architectural ideology focused on organic growth\n- Rigid dimensional constraints: 2.5m x 4.0m x 2.5m capsules"
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
                padded.append({"label": item['label'], "image": base64_data, "mime_type": mime_type, "object_position": item.get('object_position', 'center'), "object_fit": item.get('object_fit', 'cover')})
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
    
    bl_left = [
        {"label": "ACTUAL 01", "image_path": "archive/reference_images/BottegaLouie/bottega_louie_ref_10.jpg"},
        {"label": "ACTUAL 01", "image_path": "archive/reference_images/BottegaLouie/bottega_louie_ref_4.jpg"}
    ]
    bl_right = bl_int_items[:2] if len(bl_int_items) >= 2 else [
        {"label": "GEN INT 01", "image_path": "archive/render_output/bottegaLouieInterior/bottegaInterior01.jpg"}, 
        {"label": "GEN INT 02", "image_path": "archive/render_output/bottegaLouieInterior/BottegaInterior02.png"}
    ]

    nakagin_ext_items = get_image_items("archive/render_output/nakaginExterior", "NAKAGIN EXT")
    nakagin_ext_left, nakagin_ext_right = split_items(nakagin_ext_items)

    bottega_qual_samples = [
        "Its high ceilings, beautiful white walls, and fresh flour decorations are luxurious and old world gorgeous.",
        "Even the cacophony of voices that echo off the large ceilings add to the luxurious, Italian glow.",
        "The interior is open and airy and very spacious for a downtown joint.",
        "A beautiful pastries section right when you walk in with all the artful creation in the glass display.",
        "The space is elegant, open, and very aesthetically pleasing.",
        "The high vaulted ceilings and the incredible amount of natural light this restaurant receives completely enhances the dining experience.",
        "Beautiful interior with vaulted ceilings and some patterned texture on the ceiling.",
        "The high ceilings and marble flooring makes the entire restaurant into a reverberating chamber of noise.",
        "The layout is open concept so you can see all the chefs hard at work.",
        "Rows of colorful macarons all line up right when you walk in."
    ]
    
    nakagin_qual_samples = [
        "140 modular capsules attached to two central concrete cores.",
        "1.3m iconic circular windows acting as primary viewing apertures.",
        "Rigid dimensional constraints: 2.5m x 4.0m x 2.5m capsules.",
        "A vision of organic growth and replaceable cells.",
        "Asymmetrical staggering of residential pods.",
        "Built-in reel-to-reel tape decks and circular bathroom pods.",
        "Deteriorating concrete and rusted steel structural bolts.",
        "A metabolist ideology suspended in time.",
        "A narrow spiral staircase enclosed in the central spine.",
        "Each unit completely self-contained and factory assembled."
    ]

    pershing_qual_samples = [
        "5-acre urban public square in Downtown Los Angeles.",
        "Radical 1992 postmodern redesign by Ricardo Legorreta.",
        "Bold geometric stucco massings in pink, purple, and yellow.",
        "A purple 10-story campanile tower overlooking the plaza.",
        "A continuous water feature meant to emulate an aqueduct.",
        "Hardscape dominating the central gathering spaces.",
        "Bright yellow cylindrical structures serving as pavilions.",
        "Extensively documented spatial interventions and subsequent erasures.",
        "Divided by low walls and fragmented elevation changes.",
        "Underground parking garage creating an elevated ground plane."
    ]

    def get_review_quotes(filename, fallback):
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                blocks = f.read().split('\n\n')
                quotes = []
                for b in blocks:
                    lines = b.strip().split('\n')
                    if len(lines) >= 4:
                        body = " ".join(lines[3:])
                        if len(body) > 250: body = body[:247] + "..."
                        quotes.append(body)
                if quotes:
                    return quotes[:10]
        return fallback

    pershing_review_samples = get_review_quotes('pershing_square_reviews.txt', [
        "The concrete walls make it feel like a fortress, completely cut off from the surrounding streets.",
        "A vibrant pop of purple and yellow geometries that feel like a post-modern playground.",
        "There's absolutely no shade, just a massive expanse of hardscape baking in the downtown sun.",
        "The aqueduct water feature is beautiful when running, dividing the space with a pleasant acoustic hum.",
        "It's an urban island elevated above a parking garage, making it completely uninviting to pedestrians.",
        "The 10-story purple campanile tower acts as a distinct, unmissable landmark amidst the glass skyscrapers.",
        "Too much pavement and not enough green space; it feels more like a transit plaza than a public park.",
        "Bright, bold stucco forms create interesting shadows and photo opportunities throughout the day.",
        "Segmented by weird low walls and confusing elevation changes that break up the flow of the park.",
        "An architectural time capsule of 1990s Los Angeles, but practically dysfunctional for community gathering."
    ])

    def format_qual_samples(samples):
        return "\n\n".join([f"> \"{s}\"" for s in samples])

    bottega_qual = format_qual_samples(bottega_qual_samples)
    nakagin_qual = format_qual_samples(nakagin_qual_samples)
    pershing_qual = format_qual_samples(pershing_qual_samples)
    pershing_reviews_formatted = format_qual_samples(pershing_review_samples)
    
    def get_text_data(filepath, fallback):
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()[:2000]
        return fallback

    system_prompt = get_text_data(os.path.join(BASE_DIR, 'logic', 'prompt.txt'), "[ AGENT PROMPT PENDING ]")
    workflow_body = f"--- SYSTEM DIRECTIVE ---\n{system_prompt}"
    pipeline_body = (
        "A visual mapping of the autonomous generative pipeline.\n\n"
        "The architecture is divided into four distinct phases:\n"
        "1. Data Harvest\n2. Processing & Extraction\n3. The Rhino 3D Canvas\n4. Archival & Synthesis"
    )

    bottega_quant = get_text_data(os.path.join(DATA_DIR, 'bottega_massing.csv'), "Element,Instances,DimX,DimY,DimZ,Layer\nLobby,1,40,30,15,01_INTERIOR\nDesk,5,5,3,3,03_FIXTURES")

    nakagin_quant = get_text_data(os.path.join(BASE_DIR, 'logic', 'nakagin_generator.py'), "capsule_w = 2.5\ncapsule_l = 4.0\ncapsule_h = 2.5\nwindow_dia = 1.3\ncores = 2\ncapsules = 140")

    pershing_quant = get_text_data(os.path.join(DATA_DIR, 'extracted_trees.csv'), "X,Y,Radius\n150.0,200.0,20.0\n180.0,240.0,25.0\n100.0,300.0,18.0\n400.0,800.0,30.0")

    mermaid_chart = """graph TD
    User((User / Architect)) -->|Prompt| OS[machine_os.py]
    User -->|Query| Auto[autonomous_discovery.py]
    
    subgraph Phase1 [Phase 1: Data Harvest]
    Auto -->|Targets| OS
    OS -->|Text Search| Scraper[free_scraper.py]
    OS -->|Image Search| SatScraper[satellite_scraper.py]
    OS -->|Map Query| OSM[osm_scraper.py]
    end

    subgraph Phase2 [Phase 2: Processing & Extraction]
    Scraper -->|Raw Text| Extractor[spatial_extractor.py]
    Extractor -->|Keywords| Mapper[spatial_mapper.py]
    Mapper -->|Outputs| MassingCSV[(target_massing.csv)]
    
    SatScraper -->|Google Maps JPG| CV[opencv_site_mapper.py]
    CV -->|Coords| TreeCSV[(extracted_trees.csv)]

    Scraper -->|Sentiment/Data| Parser[parser.py]
    Parser -->|Compiles| Manifest[(memory_manifest.json)]
    
    OSM -->|GIS Data| MapJSON[(pershing_osm.json)]
    end

    subgraph Phase3 [Phase 3: The Rhino 3D Canvas]
    MassingCSV -.->|Beamed via F4| Uni[rhino_universal.py]
    TreeCSV -.->|Beamed via F4| Site[site_reconstruction.py]
    MapJSON -.->|Beamed via F4| SiteOSM[rhino_osm_builder.py]
    Manifest -.->|Beamed via F4| Engine[intervention_engine.py]
    
    Site --> Masterplan[3D Masterplan]
    SiteOSM --> Masterplan
    Engine --> Masterplan
    end

    subgraph Phase4 [Phase 4: Archival & Synthesis]
    Masterplan -->|Auto-Screenshot| Renders[render_output]
    Renders --> Compiler[deck_compiler.py]
    Compiler --> FinalDeck[presentation_deck.html]
    end"""

    bottega_summary = (
        "Bottega Louie is a high-end patisserie and restaurant situated in the historic Brockman Building in Downtown Los Angeles.\n\n"
        "It was chosen as a primary case study because its cavernous, marble-clad interior acts as an acoustic and visual echo chamber. "
        "The space relies heavily on sensory excess—from vibrant macarons to reverberating noise—to construct its identity.\n\n"
        "This makes it an ideal testing ground for extracting atmospheric, qualitative memories and translating them into rigid, quantitative architectural geometry."
    )
    
    nakagin_summary = (
        "The Nakagin Capsule Tower in Tokyo, designed by Kisho Kurokawa, is a rare built example of the Japanese Metabolism movement.\n\n"
        "It was intended to be a living, organic structure with interchangeable cellular pods, but instead fell into a state of permanent decay and eventual demolition.\n\n"
        "It is relevant to the Memory Machine because its strict, algorithmic modularity directly mirrors computational architecture. "
        "The tower serves as a physical palimpsest, capturing the tension between utopian technological ideals and the reality of urban entropy."
    )

    pershing_summary = (
        "Pershing Square is a historic five-acre public park in the heart of Downtown Los Angeles that has undergone constant demolition and redesign over the last century.\n\n"
        "Most recently defined by Ricardo Legorreta’s bold, postmodern geometric interventions in 1992, the site is currently being erased once again.\n\n"
        "It was selected as the final masterplan site because it represents the ultimate urban palimpsest. "
        "The site’s continuous overwriting of physical form perfectly embodies the unstable, shifting nature of both human and machine memory."
    )

    abstract_text = get_text_data(os.path.join(DATA_DIR, 'project_summary.txt'), "A computational design project exploring the intersection of human memory decay, artificial intelligence, and architectural reconstruction. This repository contains the logic for procedurally reconstructing memories, harvesting digital artifacts, and compiling the forensic findings into both a digital palimpsest and a physical space.")

    payload = {
        "deck_title": "Memory Machine // Digital Palimpsest",
        "slides": [
            {
                "type": "title_slide",
                "title": "MEMORY MACHINE // DIGITAL PALIMPSEST",
                "subtitle": "The Machine That Forgets",
                "body": abstract_text,
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
                "type": "text_and_mermaid_slide",
                "title": "02 // SYSTEM PIPELINE",
                "body": pipeline_body,
                "right_title": "WORKFLOW DIAGRAM",
                "mermaid_code": mermaid_chart
            },
            {
                "type": "text_and_image_slide",
                "title": "03 // COLLECTIVE MEMORY",
                "body": "Memory is not a static archive, but an unstable process of encoding, retrieval, and decay; it shifts, collapses, and rewrites itself constantly. In the last decade or so, 'artificial intelligence' (LoRAs/Hallucinations) has been exposed as a reflection of how memory operates, and within this operation are its inherent biases, fractures, and capacity for curiosity and invention.\n\nArchitecture contains memory. Spaces contain memories, old walls are torn down, types of architectural witness marks are left, with tooling marks and bits of material leftovers. Many of these are hidden below the surface, covered by fresh gypsum and spackle, left to only be discovered by the next entity that tears down these walls.\n\nThese collisions of old and new produce moments of dissonance, where architectural time collapses into a single frame.",
                "right_title": "ARCHITECTURAL PALIMPSEST",
                "right_grid": make_grid([
                    {"label": "WITNESS MARKS", "image_path": "archive/render_output/front_cover.jpg"}
                ], count=1)
            },
            {
                "type": "text_and_image_slide",
                "title": "04 // BOTTEGA LOUIE",
                "body": bottega_summary,
                "right_title": "",
                "right_grid": make_grid(bl_int_items, count=1)
            },
            {
                "type": "dual_text_slide",
                "title": "05 // BOTTEGA LOUIE",
                "left_title": "QUALITATIVE DATA [ REDACTED ]",
                "left_body": bottega_qual,
                "right_title": "QUANTITATIVE DATA [ BINARY STRATA ]",
                "right_body": bottega_quant
            },
            {
                "type": "grid_slide",
                "title": "06 // BOTTEGA LOUIE",
                "left_title": "",
                "right_title": "",
                "left_grid": make_grid(bl_left),
                "right_grid": make_grid(bl_right)
            },
            {
                "type": "text_and_image_slide",
                "title": "07 // NAKAGIN CAPSULE TOWER",
                "body": nakagin_summary,
                "right_title": "",
                "right_grid": make_grid([
                    {"label": "GENERATED EXTERIOR", "image_path": "archive/render_output/Nakagin/flux2_klein_00122_.png"}
                ], count=1)
            },
            {
                "type": "dual_text_slide",
                "title": "08 // NAKAGIN CAPSULE TOWER",
                "left_title": "QUALITATIVE DATA [ REDACTED ]",
                "left_body": nakagin_qual,
                "right_title": "QUANTITATIVE DATA [ BINARY STRATA ]",
                "right_body": nakagin_quant
            },
            {
                "type": "grid_slide",
                "title": "09 // NAKAGIN CAPSULE TOWER",
                "left_title": "",
                "right_title": "",
                "left_grid": make_grid([
                    {"label": "NAKAGIN TOWER", "image_path": "archive/reference_images/nakaginCapsuleTower/2362d526d98b4e9d982ec03b92f753db.f5fb7444.jpg"}
                ], count=1),
                "right_grid": make_grid([
                    {"label": "GENERATED EXTERIOR", "image_path": "archive/render_output/Nakagin/flux2_klein_00123_.png"}
                ], count=1)
            },
            {
                "type": "text_and_image_slide",
                "title": "10 // PERSHING SQUARE",
                "body": pershing_summary,
                "right_title": "",
                "right_grid": make_grid([
                    {"label": "HERO IMAGE", "image_path": "archive/reference_images/PershingSquare/pershing_square_hero_resized.webp"}
                ], count=1)
            },
            {
                "type": "dual_text_slide",
                "title": "11 // PERSHING SQUARE",
                "left_title": "QUALITATIVE DATA [ REDACTED ]",
                "left_body": pershing_qual,
                "right_title": "QUANTITATIVE DATA [ BINARY STRATA ]",
                "right_body": pershing_quant,
                "right_image": get_single_image("archive/reference_images/PershingSquare/pershingMap.jpg")
            },
            {
                "type": "text_and_image_slide",
                "title": "12 // PERSHING SQUARE",
                "body": pershing_reviews_formatted,
                "right_title": "",
                "right_grid": make_grid([
                    {"label": "LEGORRETA 07", "image_path": "archive/reference_images/PershingSquare/_Pershing_Square_Lourdes_Legorreta_07_.jpg"}
                ], count=1)
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

            abstract_html = f'<div class="text-wrap" style="margin-top: 115px;">{slide["body"]}</div>' if slide.get("body") else ""

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px; position: relative; z-index: 20;">{slide["subtitle"]}</h2>
                    {abstract_html}
                </div>
                <div class="page-side right-page" style="padding: 0;">{hero_html}</div>
            '''
        elif slide["type"] == "text_slide":
            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <div class="text-wrap" style="margin-top: 150px;">{slide["body"]}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;"></div>
            '''
        elif slide["type"] == "workflow_slide":
            steps_html = ""
            for i, step in enumerate(slide["steps"]):
                arrow = '<div style="display: flex; align-items: center; justify-content: center; padding: 0 15px; color: #666; font-size: 2rem;">&rarr;</div>' if i < len(slide["steps"]) - 1 else ''
                steps_html += f'''
                    <div style="flex: 1; border: 1px solid #333; background: #0a0a0a; padding: 20px; display: flex; flex-direction: column;">
                        <h3 style="color: var(--accent-glow); margin-top: 0; font-size: 1.2rem; border-bottom: 1px solid #222; padding-bottom: 10px;">{step['title']}</h3>
                        <p style="color: #aaa; font-size: 1rem; line-height: 1.4; margin: 0;">{step['desc']}</p>
                    </div>
                    {arrow}
                '''
            slides_html += f'''
                <div class="page-side left-page" style="width: 100%; padding-right: 60px; padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <div style="flex: 1; display: flex; flex-direction: column; justify-content: center;">
                        <div style="display: flex; flex-direction: row; margin-top: 20px; align-items: stretch; height: 350px;">
                            {steps_html}
                        </div>
                    </div>
                </div>
                <div class="page-side right-page" style="display:none;"></div>
            '''
        elif slide["type"] == "text_and_mermaid_slide":
            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <div class="text-wrap" style="margin-top: 150px;">{slide["body"]}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div style="margin-top: 115px; flex: 1; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid #333; background: #080808; padding: 20px;">
                        <div class="mermaid" style="width: 100%; height: 100%; display: flex; justify-content: center;">
{slide["mermaid_code"]}
                        </div>
                    </div>
                </div>
            '''
        elif slide["type"] == "text_and_image_slide":
            right_boxes = ""
            for item in slide.get("right_grid", []):
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    obj_fit = item.get("object_fit", "cover")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos}; object-fit: {obj_fit};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                right_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div></div>'

            stack_margin = slide.get("stack_margin", "115px")

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <div class="text-wrap" style="margin-top: 150px;">{slide["body"]}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div class="img-stack" style="margin-top: {stack_margin};">{right_boxes}</div>
                </div>
            '''
        elif slide["type"] == "dual_text_slide":
            right_img_html = ""
            text_container_style = "margin-top: 115px; flex: 1; overflow: hidden; display: flex; align-items: flex-start;"
            
            if slide.get("right_image") and slide["right_image"].get("image"):
                img_data = slide["right_image"]
                right_img_html = f'<div class="img-stack" style="margin-top: 20px;"><div class="img-box"><img src="data:{img_data["mime_type"]};base64,{img_data["image"]}" style="width: 100%; height: 100%; object-fit: cover;"></div></div>'
                text_container_style = "margin-top: 115px; height: 150px; flex-shrink: 0; overflow: hidden; display: flex; align-items: flex-start;"

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["left_title"]}</h2>
                    <div class="text-wrap" style="margin-top: 115px; overflow: hidden; flex: 1;">{slide["left_body"]}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div style="{text_container_style}">
                        <div class="text-wrap" style="font-family: monospace; color: #00ff66; overflow: hidden; flex: 1; word-break: break-all; white-space: pre-wrap;">{slide["right_body"]}</div>
                    </div>
                    {right_img_html}
                </div>
            '''
        elif slide["type"] == "grid_slide":
            left_boxes = ""
            for item in slide["left_grid"]:
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    obj_fit = item.get("object_fit", "cover")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos}; object-fit: {obj_fit};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                left_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div></div>'
            
            right_boxes = ""
            for item in slide["right_grid"]:
                if item.get("image"):
                    obj_pos = item.get("object_position", "center")
                    obj_fit = item.get("object_fit", "cover")
                    img_tag = f'<img src="data:{item.get("mime_type", "image/jpeg")};base64,{item["image"]}" style="object-position: {obj_pos}; object-fit: {obj_fit};">'
                    css = "img-box"
                else:
                    img_tag = ""
                    css = "img-box dashed"
                right_boxes += f'<div style="display: flex; flex-direction: column; flex: 1; min-height: 0;"><div class="{css}">{img_tag}</div></div>'

            slides_html += f'''
                <div class="page-side left-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">{slide["title"]}</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["left_title"]}</h2>
                    <div class="img-stack" style="margin-top: 115px;">{left_boxes}</div>
                </div>
                <div class="page-side right-page" style="padding-top: 20px; padding-bottom: 20px;">
                    <h1 class="zine-title" style="font-size: 1.8rem; visibility: hidden; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 10px;">Spacer</h1>
                    <h2 class="page-header" style="margin-bottom: 10px; margin-top: 0px;">{slide["right_title"]}</h2>
                    <div class="img-stack" style="margin-top: 115px;">{right_boxes}</div>
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