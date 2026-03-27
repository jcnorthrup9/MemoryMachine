"""
Qualitative Cross-Pollination Engine
Memory Machine // Digital Palimpsest

Takes a natural language qualitative description of a desired space, searches the
scraped review archive for real-world spaces matching those atmospheric qualities,
extracts their spatial logic, and generates a structured Memory Node for deployment
in Rhino 3D — plus a Mermaid diagram and architectural narrative.

Usage:
    python qualitative_search.py
    python qualitative_search.py "I want a space with shade and shallow wading pools"
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime

try:
    from dotenv import load_dotenv
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MANIFEST_PATH = os.path.join(DATA_DIR, 'memory_manifest.json')
OUTPUT_DIR = os.path.join(DATA_DIR, 'cross_pollination')

# All available local review/data files, keyed by place name
REVIEW_FILES = {
    "Bottega Louie":          os.path.join(DATA_DIR, "bottega_louie_reviews.txt"),
    "Bottega Louie (Yelp)":   os.path.join(DATA_DIR, "anonymized_bottega_louie_reviews.json"),
    "Nakagin Capsule Tower":  os.path.join(DATA_DIR, "nakagin.txt"),
    "Zaryadye Park":          os.path.join(DATA_DIR, "zaryadye_park_reviews.txt"),
    "Queens Gardens Bridge":  os.path.join(DATA_DIR, "queens_gardens_bridge_reviews.txt"),
    "Pershing Square":        os.path.join(DATA_DIR, "pershing_square_reviews.txt"),
    "EXIT()":                 os.path.join(DATA_DIR, "exit_reviews.txt"),
    "O.T. Johnson Building":  os.path.join(DATA_DIR, "ot_johnson_data.txt"),
}


# ─── CORPUS LOADING ───────────────────────────────────────────────────────────

def load_review_corpus():
    """Load all available review text from local data files into a dict."""
    corpus = {}
    for place, path in REVIEW_FILES.items():
        if not os.path.exists(path):
            continue
        try:
            if path.endswith('.json'):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    raw = json.load(f)
                texts = []
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict):
                            t = item.get('text', {})
                            if isinstance(t, dict):
                                texts.append(t.get('full', ''))
                            elif isinstance(t, str):
                                texts.append(t)
                # Cap token load: first 200 reviews
                corpus[place] = ' '.join(texts[:200])
            else:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    corpus[place] = f.read()
        except Exception as e:
            print(f"    [WARN] Could not load {place}: {e}")
    return corpus


# ─── AI STEPS ─────────────────────────────────────────────────────────────────

def extract_keywords_with_ai(prompt, model):
    """Use Gemini to extract qualitative spatial keywords and attributes from the prompt."""
    sys_prompt = (
        'You are an architectural analyst. Extract qualitative spatial keywords from '
        'this description of a desired space.\n\n'
        'Return ONLY a valid JSON object in this exact format:\n'
        '{\n'
        '  "qualities": ["shade", "water", "acoustic"],\n'
        '  "spatial_elements": ["canopy", "wading pool", "fountain"],\n'
        '  "sensory_keywords": ["cool", "humid", "gentle sound", "dappled light"],\n'
        '  "mood": "tranquil and restorative"\n'
        '}\n\n'
        f'User description: "{prompt}"'
    )
    response = model.generate_content(sys_prompt)
    clean = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(clean)


def search_corpus_for_matches(keywords_data, corpus):
    """Score each review source by how many qualitative keywords appear in its text."""
    all_keywords = (
        keywords_data.get("qualities", []) +
        keywords_data.get("spatial_elements", []) +
        keywords_data.get("sensory_keywords", [])
    )

    matches = []
    for place, text in corpus.items():
        text_lower = text.lower()
        score = 0
        matched_terms = []
        relevant_excerpts = []

        for kw in all_keywords:
            if kw.lower() in text_lower:
                score += 1
                matched_terms.append(kw)
                idx = text_lower.find(kw.lower())
                start = max(0, idx - 100)
                end = min(len(text), idx + 220)
                excerpt = text[start:end].strip().replace('\n', ' ')
                relevant_excerpts.append(excerpt)

        if score > 0:
            matches.append({
                "place": place,
                "match_score": score,
                "matched_terms": matched_terms,
                "excerpts": relevant_excerpts[:3],
            })

    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches[:3]


def synthesize_spatial_parameters(prompt, matches, keywords_data, model):
    """Ask Gemini to produce precise 3D-ready spatial parameters from matched memories."""
    excerpts_text = ""
    for m in matches:
        excerpts_text += f"\n\nSource: {m['place']}\n"
        excerpts_text += "\n".join(m["excerpts"][:2])

    sys_prompt = (
        'You are an architect translating qualitative spatial descriptions into precise '
        'building parameters for a 3D model.\n\n'
        f'The user wants: "{prompt}"\n\n'
        f'Qualitative keywords extracted: {json.dumps(keywords_data)}\n\n'
        'Real-world spaces that match these qualities (from scraped visitor reviews):'
        f'{excerpts_text}\n\n'
        'Based on this, generate precise spatial parameters for a new architectural '
        'intervention at Pershing Square, Downtown Los Angeles (a 5-acre urban plaza, '
        'approx. 165m x 183m).\n\n'
        'Return ONLY a valid JSON object in this exact format:\n'
        '{\n'
        '  "footprint_m": {"width": 20, "depth": 20},\n'
        '  "height_m": 8.0,\n'
        '  "canopy_overhang_m": 2.5,\n'
        '  "pool_depth_m": 0.3,\n'
        '  "pool_width_m": 12.0,\n'
        '  "column_count": 8,\n'
        '  "column_height_m": 6.0,\n'
        '  "column_radius_m": 0.3,\n'
        '  "materials": ["concrete", "water", "weathered_steel"],\n'
        '  "geometry_type": "pavilion_with_water",\n'
        '  "acoustic_elements": ["recirculating_water_jets", "textured_ceiling"],\n'
        '  "shade_coverage_pct": 80,\n'
        '  "sentiment_score": 0.88\n'
        '}\n\n'
        'geometry_type must be one of: '
        '"pavilion_with_water", "shade_canopy", "water_garden", '
        '"acoustic_screen", "memory_tower", "landscape_mound"'
    )
    response = model.generate_content(sys_prompt)
    clean = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(clean)


def generate_narrative(prompt, matches, spatial_params, keywords_data, model):
    """Generate a poetic architectural narrative for the intervention."""
    source_names = [m["place"] for m in matches]
    sys_prompt = (
        'You are a poetic architectural theorist writing for a design thesis about '
        'memory, decay, and urban space.\n\n'
        'Write a short (3-4 paragraph) architectural narrative for a new intervention '
        'being placed in Pershing Square, Downtown Los Angeles.\n\n'
        f'The intervention was requested by: "{prompt}"\n'
        f'It was cross-pollinated from the atmospheric memory of: {", ".join(source_names)}\n'
        f'Its physical parameters are: {json.dumps(spatial_params, indent=2)}\n\n'
        'The narrative should:\n'
        '1. Describe what the space FEELS like (sensory, atmospheric)\n'
        '2. Identify the "witness marks" it carries from its source spaces\n'
        '3. Explain how it COLLIDES with and enriches the existing Pershing Square palimpsest\n'
        '4. Use architectural language but remain evocative and slightly melancholic\n\n'
        'Write in present tense, third person. Do not use bullet points.'
    )
    response = model.generate_content(sys_prompt)
    return response.text.strip()


# ─── DIAGRAM ──────────────────────────────────────────────────────────────────

def generate_mermaid_diagram(prompt, keywords_data, matches, spatial_params):
    """Build a Mermaid.js flowchart mapping: Qualitative Input → Memory Source → Output."""

    def mmd(s):
        """Strip characters that break Mermaid node labels."""
        return re.sub(r'["\[\]{}()/\\]', '', str(s))

    qualities = keywords_data.get("qualities", [])[:3]
    elements  = keywords_data.get("spatial_elements", [])[:2]
    geo_type  = spatial_params.get("geometry_type", "intervention")

    lines = ["flowchart TD"]
    lines.append(f'    INPUT[/"User Query: {mmd(prompt[:55])}..."/]')
    lines.append('    AI["AI Keyword Extraction"]')
    lines.append("    INPUT --> AI")

    # Qualities
    for i, q in enumerate(qualities):
        lines.append(f'    Q{i}["{mmd(q)}"]')
        lines.append(f"    AI --> Q{i}")

    # Spatial elements
    for i, e in enumerate(elements):
        lines.append(f'    E{i}["{mmd(e)}"]')
        lines.append(f"    AI --> E{i}")

    # Memory sources
    for i, m in enumerate(matches):
        lines.append(f'    SRC{i}("{mmd(m["place"])}")')
        for j, q in enumerate(qualities):
            if q in m.get("matched_terms", []):
                lines.append(f"    Q{j} --> SRC{i}")
        for j, e in enumerate(elements):
            if e in m.get("matched_terms", []):
                lines.append(f"    E{j} --> SRC{i}")

    # Synthesis
    lines.append('    SYNTH["Spatial Synthesis"]')
    for i in range(len(matches)):
        lines.append(f"    SRC{i} --> SYNTH")

    # Output nodes
    lines.append(f'    GTYPE["Geometry: {mmd(geo_type)}"]')
    lines.append(f'    HGHT["Height: {spatial_params.get("height_m", "?")} m"]')
    mat_str = mmd(", ".join(spatial_params.get("materials", [])))
    lines.append(f'    MAT["Materials: {mat_str}"]')
    lines.append("    SYNTH --> GTYPE")
    lines.append("    SYNTH --> HGHT")
    lines.append("    SYNTH --> MAT")

    # Deploy
    lines.append('    DEPLOY[["Deploy to Pershing Square"]]')
    lines.append("    GTYPE --> DEPLOY")
    lines.append("    HGHT --> DEPLOY")
    lines.append("    MAT --> DEPLOY")

    return "\n".join(lines)


# ─── HTML OUTPUT ──────────────────────────────────────────────────────────────

def generate_html_output(node, output_path):
    """Write a self-contained dark-theme HTML page with narrative, params, and Mermaid diagram."""
    mermaid_diagram = node.get("mermaid_diagram", "")
    narrative       = node.get("narrative", "")
    spatial_params  = node.get("spatial_parameters", {})
    sources         = node.get("memory_sources", [])

    # Build source cards
    sources_html = ""
    for s in sources:
        terms = ", ".join(s.get("matched_terms", []))
        excerpt = s.get("excerpts", [""])[0] if s.get("excerpts") else ""
        sources_html += (
            f'<div class="source-card">'
            f'<h3>{s["place"]}</h3>'
            f'<p class="matched-terms">Matched qualities: {terms}</p>'
            f'<blockquote>{excerpt}</blockquote>'
            f'</div>\n'
        )

    # Build params table (skip geometry_type — shown separately)
    params_html = f'<tr><td>Geometry Type</td><td>{spatial_params.get("geometry_type", "—")}</td></tr>\n'
    for k, v in spatial_params.items():
        if k == "geometry_type":
            continue
        display_key = k.replace("_", " ").title()
        if isinstance(v, dict):
            v = ", ".join(f"{dk}: {dv}" for dk, dv in v.items())
        elif isinstance(v, list):
            v = ", ".join(str(i) for i in v)
        params_html += f"<tr><td>{display_key}</td><td>{v}</td></tr>\n"

    # Narrative paragraphs
    narrative_html = "".join(
        f"<p>{para.strip()}</p>\n"
        for para in narrative.split("\n\n") if para.strip()
    )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cross-Pollination // {node['name']}</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
<style>
  :root {{
    --bg:      #050505;
    --surface: #0f0f0f;
    --accent:  #fff4ca;
    --text:    #c8c8c0;
    --muted:   #555;
    --border:  #1e1e1e;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Courier New', monospace;
    padding: 2.5rem 3rem;
    line-height: 1.75;
    max-width: 1100px;
    margin: 0 auto;
  }}
  h1 {{
    color: var(--accent);
    font-size: 1.1rem;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
  }}
  h2 {{
    color: var(--accent);
    font-size: 0.8rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.4rem;
    margin: 2.5rem 0 1rem;
  }}
  h3 {{ color: var(--accent); font-size: 0.8rem; margin-bottom: 0.4rem; }}
  .subtitle {{
    color: var(--muted);
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 2rem;
  }}
  .intervention-title {{
    font-size: 1.3rem;
    color: var(--accent);
    margin: 0.5rem 0 1rem;
  }}
  .geo-badge {{
    display: inline-block;
    background: var(--accent);
    color: var(--bg);
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 0.2rem 0.7rem;
    margin-bottom: 0.6rem;
  }}
  .query-box {{
    border: 1px solid var(--border);
    padding: 1rem 1.5rem;
    margin: 1rem 0;
    font-style: italic;
    color: var(--accent);
    opacity: 0.75;
    font-size: 0.9rem;
  }}
  .narrative p {{
    margin-bottom: 1.1rem;
    font-size: 0.88rem;
  }}
  .sources-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
  }}
  .source-card {{
    border: 1px solid var(--border);
    padding: 1rem 1.2rem;
    background: var(--surface);
  }}
  .matched-terms {{
    font-size: 0.68rem;
    color: var(--muted);
    margin: 0.25rem 0 0.6rem;
  }}
  blockquote {{
    border-left: 2px solid var(--accent);
    padding-left: 0.75rem;
    font-size: 0.78rem;
    color: var(--muted);
    font-style: italic;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8rem;
  }}
  td {{
    padding: 0.4rem 0.8rem;
    border-bottom: 1px solid var(--border);
  }}
  td:first-child {{ color: var(--muted); width: 38%; }}
  .mermaid-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 1.5rem;
    overflow-x: auto;
  }}
  footer {{
    margin-top: 3rem;
    color: var(--muted);
    font-size: 0.65rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    border-top: 1px solid var(--border);
    padding-top: 1rem;
  }}
</style>
</head>
<body>

<h1>Memory Machine // Cross-Pollination Engine</h1>
<div class="subtitle">Qualitative Input → Architectural Intervention // Pershing Square, DTLA</div>

<h2>Source Query</h2>
<div class="query-box">"{node.get('source_query', '')}"</div>

<h2>Generated Intervention</h2>
<div class="geo-badge">{spatial_params.get('geometry_type', 'intervention').replace('_', ' ')}</div>
<div class="intervention-title">{node['name']}</div>

<h2>Architectural Narrative</h2>
<div class="narrative">
{narrative_html}
</div>

<h2>Memory Sources</h2>
<div class="sources-grid">
{sources_html}
</div>

<h2>Spatial Parameters</h2>
<table>
{params_html}
</table>

<h2>Cross-Pollination Logic</h2>
<div class="mermaid-wrap">
<div class="mermaid">
{mermaid_diagram}
</div>
</div>

<footer>Memory Machine // Digital Palimpsest // Node {node.get('node_id', '')} // Generated {generated}</footer>

<script>
  mermaid.initialize({{
    startOnLoad: true,
    theme: 'dark',
    flowchart: {{ curve: 'basis' }}
  }});
</script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ─── MAIN ENGINE ──────────────────────────────────────────────────────────────

def run_cross_pollination(prompt, verbose=True):
    """
    Full pipeline: natural language prompt → Memory Node JSON + HTML output.
    Returns the generated node dict, or None on failure.
    """
    if verbose:
        print("\n" + "=" * 62)
        print("  QUALITATIVE CROSS-POLLINATION ENGINE // ONLINE")
        print("=" * 62)

    load_dotenv(os.path.join(BASE_DIR, '.env'))
    api_key = os.environ.get("GEMINI_API_KEY")

    if not GENAI_AVAILABLE or not api_key:
        print("ERROR: Gemini API unavailable. Add GEMINI_API_KEY to .env")
        return None

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # ── Step 1: Keyword Extraction ────────────────────────────────────────────
    if verbose:
        print("\n[1/5] Extracting qualitative keywords from prompt...")
    keywords_data = extract_keywords_with_ai(prompt, model)
    if verbose:
        print(f"      Qualities:  {keywords_data.get('qualities', [])}")
        print(f"      Elements:   {keywords_data.get('spatial_elements', [])}")
        print(f"      Sensory:    {keywords_data.get('sensory_keywords', [])}")

    # ── Step 2: Corpus Search ─────────────────────────────────────────────────
    if verbose:
        print("\n[2/5] Searching memory archive for matching spaces...")
    corpus  = load_review_corpus()
    matches = search_corpus_for_matches(keywords_data, corpus)
    if verbose:
        if matches:
            for m in matches:
                print(f"      MATCH [{m['match_score']}]: {m['place']}  →  {m['matched_terms'][:4]}")
        else:
            print("      No direct matches found; AI will infer from keywords alone.")

    # ── Step 3: Spatial Parameter Synthesis ───────────────────────────────────
    if verbose:
        print("\n[3/5] Synthesizing spatial parameters from matched memories...")
    spatial_params = synthesize_spatial_parameters(prompt, matches, keywords_data, model)
    if verbose:
        print(f"      Geometry:  {spatial_params.get('geometry_type')}")
        print(f"      Height:    {spatial_params.get('height_m')} m")
        print(f"      Footprint: {spatial_params.get('footprint_m')}")
        print(f"      Materials: {spatial_params.get('materials')}")

    # ── Step 4: Narrative ─────────────────────────────────────────────────────
    if verbose:
        print("\n[4/5] Generating architectural narrative...")
    narrative = generate_narrative(prompt, matches, spatial_params, keywords_data, model)

    # ── Step 5: Mermaid Diagram ───────────────────────────────────────────────
    if verbose:
        print("\n[5/5] Generating cross-pollination logic diagram...")
    mermaid_diagram = generate_mermaid_diagram(prompt, keywords_data, matches, spatial_params)

    # ── Assemble Memory Node ──────────────────────────────────────────────────
    node_id = "CP_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    geo_label = spatial_params.get("geometry_type", "intervention").replace("_", " ").title()
    source_label = " + ".join(m["place"] for m in matches[:2]) if matches else "Inferred"
    intervention_name = f"{geo_label} [{source_label}]"

    node = {
        "name": intervention_name,
        "intervention_type": "cross_pollination",
        "source_query": prompt,
        "memory_sources": [
            {
                "place":         m["place"],
                "matched_terms": m["matched_terms"],
                "excerpts":      m["excerpts"],
            }
            for m in matches
        ],
        "sentiment_score":   float(spatial_params.get("sentiment_score", 0.88)),
        "raw_text":          narrative,
        "spatial_parameters": spatial_params,
        "node_id":           node_id,
        "witness_marks":     keywords_data.get("sensory_keywords", []),
        "narrative":         narrative,
        "mermaid_diagram":   mermaid_diagram,
        "generated_at":      datetime.now().isoformat(),
    }

    # ── Write Outputs ─────────────────────────────────────────────────────────
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    json_path = os.path.join(OUTPUT_DIR, f"{node_id}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(node, f, indent=2, ensure_ascii=False)

    html_path = os.path.join(OUTPUT_DIR, f"{node_id}.html")
    generate_html_output(node, html_path)

    # ── Inject into memory_manifest.json for Rhino ────────────────────────────
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    else:
        manifest = []

    manifest.append({
        "name":               intervention_name,
        "sentiment_score":    node["sentiment_score"],
        "raw_text":           narrative[:500],
        "node_id":            node_id,
        "intervention_type":  "cross_pollination",
        "spatial_parameters": spatial_params,
    })

    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)

    if verbose:
        print(f"\n{'=' * 62}")
        print("  CROSS-POLLINATION COMPLETE")
        print(f"  JSON  →  {json_path}")
        print(f"  HTML  →  {html_path}")
        print(f"  Node '{node_id}' injected into memory_manifest.json")
        print("  Open Rhino and run intervention_engine.py to deploy.")
        print(f"{'=' * 62}\n")

    return node


# ─── CLI ENTRY POINT ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Qualitative Cross-Pollination Engine // Memory Machine"
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Natural language description of desired spatial qualities",
    )
    args = parser.parse_args()

    print(r"""
  ╔══════════════════════════════════════════════════════════╗
  ║   CROSS-POLLINATION ENGINE // MEMORY MACHINE             ║
  ║   Qualitative Input → Memory Search → Spatial Output     ║
  ╚══════════════════════════════════════════════════════════╝""")

    if args.prompt:
        prompt = args.prompt
    else:
        print('\nDescribe the qualitative spatial experience you want to generate.')
        print('Example: "I want a space with lots of shade, shallow wading pools,')
        print('         and water features that create a pleasant acoustic hum."\n')
        prompt = input(">>> ").strip()

    if not prompt:
        print("No prompt provided. Exiting.")
        return

    run_cross_pollination(prompt)


if __name__ == "__main__":
    main()
