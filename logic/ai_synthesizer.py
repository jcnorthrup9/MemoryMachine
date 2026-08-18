import os
import re
import json
import time
import random
import urllib.request
import urllib.error
from logic.urban_engine import guideline_manager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIAGRAMS_DIR = os.path.join(BASE_DIR, 'archive', 'diagrams')

def check_aabb_overlap(box1: dict, box2: dict) -> bool:
    """
    Axis-Aligned Bounding Box (AABB) overlap detection.
    Expects dictionaries with 'x', 'y', 'width', and 'height'.
    Returns True if the boxes overlap, False otherwise.
    """
    return not (
        box1['x'] + box1['width'] <= box2['x'] or
        box2['x'] + box2['width'] <= box1['x'] or
        box1['y'] + box1['height'] <= box2['y'] or
        box2['y'] + box2['height'] <= box1['y']
    )

def fetch_osm_map(lat: float, lon: float, site_name: str):
    """Fetches a static map from OpenStreetMap and saves it to assets/precedents."""
    try:
        safe_name = "".join([c for c in site_name if c.isalnum() or c in (' ', '-', '_')]).strip().replace(" ", "_")
        if not safe_name: return
        
        assets_dir = os.path.join(BASE_DIR, 'assets', 'precedents')
        os.makedirs(assets_dir, exist_ok=True)
        filepath = os.path.join(assets_dir, f"{safe_name}_OSM.png")
        
        url = f"https://staticmap.openstreetmap.de/staticmap.php?center={lat},{lon}&zoom=17&size=800x800&maptype=mapnik"
        req = urllib.request.Request(url, headers={'User-Agent': 'MemoryMachine/1.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            with open(filepath, 'wb') as f:
                f.write(response.read())
        print(f"      -> [OSM] Successfully downloaded static map for '{site_name}' to precedents folder.")
    except Exception as e:
        print(f"      -> [OSM ERROR] Could not fetch map for {site_name}: {e}")

def query_ai(system_prompt: str, user_prompt: str) -> str:
    """Calls local Ollama. (2026-07-17: Gemini path removed -- the deployed
    Python env never had google-genai installed, so every call was silently
    eating an exception and falling through to Ollama anyway; this was
    always the only AI path actually running.)"""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "llama3",
        "system": system_prompt,
        "prompt": user_prompt,
        "format": "json",
        "stream": False,
        # Bumped 0.7 -> 1.0 (2026-07-17): user reported remixes looking the
        # same across repeated pulls. Higher temperature widens sampling
        # variety for this constrained JSON-layout task.
        "options": {"temperature": 1.0}
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            return res.get("response", "")
    except Exception as e:
        print(f"      -> [OLLAMA ERROR] Could not connect to local AI: {e}")
        return ""

# 2026-08-13: loose natural-language recognition for explicit site/element
# requests (e.g. "give me something from Gardens by the Bay", "more
# blacktop", "it's too hot") -- see extract_prompt_hints()'s own docstring
# for why relying on the LLM alone to honor these isn't reliable enough.
SITE_NAME_ALIASES = {
    "PershingSquare":   ["pershing square", "pershing"],
    "ParcVillette":      ["parc villette", "parc de la villette", "la villette", "villette"],
    "ZaryadyePark":      ["zaryadye park", "zaryadye"],
    "Schouwburgplein":   ["schouwburgplein", "schouwburg"],
    "GardensBytheBay":   ["gardens by the bay", "gardens bythe bay", "gardensbythebay"],
}

# Canonical layer id -> loose synonyms a user might actually type. "hot"/
# "sunny"/etc are deliberately mapped to SHADE (not a separate "weather"
# concept) -- the user's own example ("if someone says something is too hot
# then it pulls more shade into the design") is exactly this: sentiment
# about heat should resolve to requesting the SHADE layer, not require its
# own special-cased pipeline.
LAYER_NAME_ALIASES = {
    "HARDSCAPE":        ["hardscape", "blacktop", "concrete", "pavement", "paving", "paved", "plaza", "asphalt"],
    "GREEN_SPACE":       ["green space", "greenscape", "grass", "lawn", "turf", "meadow", "greenery", "lawns"],
    "SHADE":             ["shade", "shady", "shaded", "canopy", "tree cover", "trees", "too hot", "overheated",
                           "sunny", "sun exposure", "cooler", "more cool", "cool it down"],
    "WATER_FEATURES":    ["water feature", "water", "pond", "fountain", "pool", "stream", "lake"],
    "PEDESTRIAN_PATH":   ["pedestrian path", "walkway", "footpath", "sidewalk", "walking path"],
    "PARKING":           ["parking lot", "parking", "garage"],
    "STREET_FURNITURE":  ["street furniture", "benches", "seating"],
    "MAJOR_ATTRACTORS":  ["major attractor", "centerpiece", "landmark"],
    "MINOR_ATTRACTORS":  ["minor attractor"],
    "UNIQUE_ELEMENTS":   ["unique element", "sculpture", "art installation", "installation"],
}


def _decamel(name):
    """'GoldenGatePark' -> 'golden gate park' -- inverse of
    fetch_park_precedent.safe_site_name()'s title-case-and-concatenate,
    used to derive a matchable loose alias for an auto-fetched precedent
    without needing a hand-written SITE_NAME_ALIASES entry for it."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()


def _dynamic_site_aliases():
    """Site aliases for any precedent SVG beyond the hardcoded
    SITE_NAME_ALIASES 5 -- e.g. one fetch_park_precedent.py wrote earlier
    this session (see generate_spatial_seed()'s auto-trigger). Lets a
    SECOND mention of an already-fetched park (a different audience
    member, a follow-up message) get recognized as an explicit hint too,
    not left purely to the LLM noticing it's already available."""
    svg_dir = os.path.join(BASE_DIR, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")
    if not os.path.isdir(svg_dir):
        return {}
    known = {name.lower() for name in SITE_NAME_ALIASES}
    aliases = {}
    for f in os.listdir(svg_dir):
        if not f.lower().endswith(".svg"):
            continue
        name = f[:-4]
        if name.lower() in known:
            continue
        aliases[name] = [_decamel(name)]
    return aliases


def extract_prompt_hints(prompt):
    """Loose, deterministic keyword/alias matching over free-text prompt
    text, so an explicit site or element request reliably maps to this
    app's canonical site/layer vocabulary -- NOT dependent on the LLM
    correctly inferring intent from prose. This matters because
    generate_spatial_seed()'s own system prompt has a built-in tension: its
    CRITICAL RULE 5 tells the model to actively AVOID repeating the same
    site, which directly fights an explicit "use park X" request, and
    there's no code-level fallback if the LLM just doesn't comply (or
    Ollama is unavailable and the request falls through to the
    non-prompt-aware random_spatial_seed() safety net entirely). See
    _ensure_hints_present() below for how these hints get GUARANTEED into
    the final seed_items, not just suggested to the LLM.

    Case-insensitive substring match; longest alias first within each
    canonical key so e.g. "gardens by the bay" matches before any shorter
    accidental substring would. Returns {"sites": [...], "layers": [...]},
    each de-duplicated, in first-seen order (prompt reading order)."""
    if not prompt:
        return {"sites": [], "layers": []}
    text = prompt.lower()

    sites = []
    all_site_aliases = {**SITE_NAME_ALIASES, **_dynamic_site_aliases()}
    for canonical, aliases in all_site_aliases.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in text:
                if canonical not in sites:
                    sites.append(canonical)
                break

    layers = []
    for canonical, aliases in LAYER_NAME_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in text:
                if canonical not in layers:
                    layers.append(canonical)
                break

    return {"sites": sites, "layers": layers}


def _ensure_hints_present(seed_items, hints, available_sites):
    """Deterministically guarantees every explicitly-requested site/layer
    (from extract_prompt_hints) actually appears in seed_items -- the real
    reliability guarantee, not just a best-effort LLM instruction.

    Pairing logic (2026-08-13, revised after live testing surfaced a real
    gap: a prompt mentioning one site and multiple layers, e.g. "Zaryadye's
    water feature, and it's too hot" -> layers=[SHADE, WATER_FEATURES],
    was pairing the site with only the FIRST layer positionally, leaving
    WATER_FEATURES un-anchored to Zaryadye at all):
      - Exactly one hinted site + one or more hinted layers: that ONE site
        is used for EVERY hinted layer (the common "give me X's stuff"
        case) -- not just positionally paired with the first.
      - Multiple hinted sites: falls back to positional pairing between
        sites and layers (no reliable way to know which site goes with
        which layer from keyword matching alone).
      - A layer or site mentioned with no site/layer partner respectively
        gets its own pick with the other field left for remix_layers()'
        own resolution (random valid site for a layer-only hint,
        GREEN_SPACE default for a site-only hint).

    PREPENDED, not appended -- remix_layers() caps seed_items at 5, so an
    explicit request must survive that cap ahead of the free-form/AI picks,
    not risk being sliced off the end. Marks each forced item
    "_explicit_hint": True so remix_layers()'s automatic category-coverage
    anchor (_best_area_anchor) can skip adding a competing pick for a
    category the user already explicitly addressed (see that function's
    own docstring)."""
    hinted_sites = (hints or {}).get("sites") or []
    hinted_layers = (hints or {}).get("layers") or []
    if not hinted_sites and not hinted_layers:
        return seed_items or []

    seed_items = list(seed_items or [])
    locations = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West", "Center"]

    if len(hinted_sites) == 1 and hinted_layers:
        pairs = [(hinted_sites[0], layer) for layer in hinted_layers]
    elif hinted_layers:
        pairs = [(hinted_sites[i] if i < len(hinted_sites) else None, layer)
                 for i, layer in enumerate(hinted_layers)]
        pairs += [(site, None) for site in hinted_sites[len(hinted_layers):]]
    else:
        pairs = [(site, None) for site in hinted_sites]

    forced = []
    for site, layer in pairs:
        already = any(
            (site is None or it.get("site") == site) and (layer is None or it.get("layer") == layer)
            for it in seed_items
        )
        if already:
            continue
        forced.append({
            "site": site or random.choice(available_sites),
            "layer": layer or "GREEN_SPACE",
            "location": random.choice(locations),
            "width": 20, "height": 20,
            "_explicit_hint": True,
        })

    return forced + seed_items


def _weighted_choice(items, weights):
    """Weighted random choice without a numpy dependency. weights need not
    sum to 1; falls back to uniform choice if every weight is 0/negative."""
    total = sum(w for w in weights if w > 0)
    if total <= 0:
        return random.choice(items)
    r = random.uniform(0, total)
    upto = 0
    for item, w in zip(items, weights):
        if w <= 0:
            continue
        upto += w
        if upto >= r:
            return item
    return items[-1]


def apply_deficit_weighting(seed_items, zonal_metadata, deficit_weights):
    """
    Post-processes generate_spatial_seed()'s AI-curated picks (or its
    algorithmic-fallback picks) so PROG-category items (zonal_metadata["PROG"]
    -- MAJOR_ATTRACTORS/MINOR_ATTRACTORS/UNIQUE_ELEMENTS) land at a
    deficit-weighted location instead of whatever the LLM/fallback picked,
    reusing the same _weighted_choice() random_spatial_seed() already uses
    for its own PROG placement bias.

    Mirrors remix_precedent()'s existing empty-prompt deficit-weighting
    (logic/pershing_api.py's _deficit_weighted_location_weights() feeding
    random_spatial_seed()'s location_weights param) but applied to EVERY
    generate_spatial_seed() call, prompted or not -- so the 2D diagram's
    amenity placement is always grounded in the same real deficit-hotspot
    signal the 3D side already uses, not just for the no-prompt random path.

    Only overrides PROG picks; SOFT/HARD/BLUE locations are left exactly as
    the AI/fallback chose them.
    """
    if not seed_items or not deficit_weights:
        return seed_items

    prog_layers = set(zonal_metadata.get("PROG", []))
    if not prog_layers:
        return seed_items

    locations = list(deficit_weights.keys())
    weights = list(deficit_weights.values())

    for item in seed_items:
        if item.get("layer") in prog_layers:
            item["location"] = _weighted_choice(locations, weights)

    return seed_items


def random_spatial_seed(zonal_metadata, available_sites, guidelines, location_weights=None):
    """
    Non-AI, algorithmic layer picker -- the old "Algorithmic Safety Net"
    body, extracted 2026-07-17 so it's directly callable for an explicit
    "random remix" (empty-prompt Generate in the Precedent Remixer), not
    just as generate_spatial_seed()'s silent AI-failure fallback.

    Category selection is weighted by each category's Recreation & Parks
    guideline target-percentage midpoint (guidelines[cat]["min"/"max"],
    from urban_design_guidelines.md), not uniform -- a random layout should
    still trend toward the real target mix (more SOFT/HARD picks than BLUE,
    matching the guideline table's ranges) instead of treating all 4
    categories as equally likely regardless of their actual target size.

    location_weights (optional): {location_name: weight} to bias WHERE a
    PROG_01 (amenity/attractor) pick lands -- e.g. toward real deficit
    hotspots from the 3D side's amenity-deficit scoring (see
    logic/pershing_api.py's remix_precedent()). Only applied to PROG_01
    picks; SOFT/HARD/BLUE picks always use uniform location choice, since
    deficit scoring is specifically an amenity-placement signal, not a
    general landscaping one.
    """
    seed_items = []
    if not zonal_metadata:
        return seed_items

    categories = list(zonal_metadata.keys())
    locations = ["North", "North-East", "East", "South-East", "South", "South-West", "West", "North-West", "Center"]
    cat_weights = [
        (guidelines.get(cat, {}).get("min", 0) + guidelines.get(cat, {}).get("max", 0)) / 2
        for cat in categories
    ]

    for _ in range(5):
        cat = _weighted_choice(categories, cat_weights)
        if not zonal_metadata[cat]:
            continue

        if cat == "PROG" and location_weights:
            location = _weighted_choice(list(location_weights.keys()), list(location_weights.values()))
        else:
            location = random.choice(locations)

        seed_items.append({
            "site": random.choice(available_sites),
            "layer": random.choice(zonal_metadata[cat]),
            "location": location,
            "width": 20,
            "height": 20
        })

    return seed_items


def generate_spatial_seed(prompt: str, matches: list = None) -> tuple:
    """
    Uses Retrieval-Augmented Generation (RAG) with local Llama 3.
    Injects real scraped reviews from ChromaDB into the prompt, asks Llama 3
    to select programmatic layers, and falls back to mathematical safety nets if it fails.
    """
    try:
        gm_data = guideline_manager.parse()
        zonal_metadata = gm_data.get("metadata", {})
        guidelines = gm_data.get("guidelines", {})
    except Exception as e:
        print(f"      -> [GUIDELINE ERROR] {e}")
        zonal_metadata = {}
        guidelines = {}

    # 2026-07-17: repointed at the current canonical precedent SVG dir --
    # data/ParkSVG was the OLD, stale source (multi-MB dupes/.svgbak/
    # sync-conflict files, superseded 2026-07-14). Feeding the AI a site
    # list from ParkSVG while remix_layers() below validates against
    # PrecedentSVG meant almost every AI pick failed validation and
    # silently collapsed to PershingSquare/GREEN_SPACE.
    SVG_DIR = os.path.join(BASE_DIR, 'data', 'PershingMetabolizer', 'parkSVG', 'PrecedentSVG')
    available_sites = []
    if os.path.exists(SVG_DIR):
        available_sites = [f[:-4].replace("_", "").replace(" ", "") for f in os.listdir(SVG_DIR) if f.lower().endswith(".svg")]
    if not available_sites: available_sites = ["PershingSquare", "ParcVillette", "ZaryadyePark", "Schouwburgplein", "GardensBytheBay"]

    available_layers = []
    if zonal_metadata:
        available_layers = [l for cat in zonal_metadata.values() for l in cat]

    # 2026-07-17: shuffle both lists each call -- local LLMs tend to anchor
    # on early list items, which was another quiet contributor to picks
    # looking the same run after run.
    random.shuffle(available_sites)
    random.shuffle(available_layers)

    # 2026-08-13: see extract_prompt_hints()'s own docstring -- detected
    # BEFORE the LLM call so the system prompt can ask for them explicitly,
    # and enforced AFTER (via _ensure_hints_present, at every return point
    # below) so honoring them doesn't depend on the LLM actually complying.
    hints = extract_prompt_hints(prompt)
    hint_instruction = ""
    if hints["sites"] or hints["layers"]:
        parts = []
        if hints["sites"]:
            parts.append(f"site(s) {', '.join(hints['sites'])}")
        if hints["layers"]:
            parts.append(f"layer(s) {', '.join(hints['layers'])}")
        hint_instruction = (
            f"\nCRITICAL RULE 7 (Explicit Request Override): The user's prompt explicitly names "
            f"{' and '.join(parts)}. You MUST include at least one pick using each of these, even if "
            f"it means repeating a site or ignoring CRITICAL RULE 5's variety preference -- an explicit "
            f"request always outranks variety.\n"
        )

    # 1. Build Semantic Context from ChromaDB
    context_text = ""
    if matches:
        for i, m in enumerate(matches[:3]): # Top 3 reviews
            context_text += f"Review {i+1}: {m.get('document', '')}\n\n"

    # Recreation & Parks target-percentage text, built live from
    # urban_design_guidelines.md via guideline_manager rather than
    # hardcoded, so an edit to the doc is reflected here too.
    guideline_text = ", ".join(
        f"{guidelines.get(cat, {}).get('label', cat)} {guidelines.get(cat, {}).get('min', '?')}-{guidelines.get(cat, {}).get('max', '?')}%"
        for cat in ["SOFT", "HARD", "PROG", "BLUE"]
        if cat in guidelines
    )

    sys_prompt = (
        "You are an expert architectural curator. Your task is to select exactly 5 spatial layers "
        "from the available list that best match the atmospheric vibe of the user's prompt and the provided historical reviews.\n"
        "IMPORTANT: You must prioritize drawing inspiration from the 'Available Sites' provided below. "
        "Only if the available sites do not meet the atmospheric conditions should you seek out a new, real-world park (which must have a 4.5+ star public review rating).\n"
        "CRITICAL RULE 1: You are FORBIDDEN from using Lurie Garden, Millennium Park, or Tanner Springs as your inspiration_park. Your inspiration_park MUST be chosen strictly from the Available Sites list provided below.\n"
        "CRITICAL RULE 2 (Water Logic): If you select a BLUE_01 (Water) layer, it MUST be assigned the exact same 'location' as a SOFT_01 (Green Space) layer so they are adjacent.\n"
        "CRITICAL RULE 3 (Edge Rule): Do NOT assign PROG_01 (Active Program) layers to the extreme corners (North-West, North-East, South-West, South-East) to maintain edge clearances.\n"
        "CRITICAL RULE 4: PROG_01 layers are 'UNIQUE_ELEMENTS' (available at PershingSquare/Schouwburgplein), 'MAJOR_ATTRACTORS' (available at ParcVillette/Schouwburgplein/ZaryadyePark), and 'MINOR_ATTRACTORS' (available at GardensBytheBay/ParcVillette/Schouwburgplein) -- pick whichever is real for the site you're drawing that layer from.\n"
        "CRITICAL RULE 5 (Variety): Do not default to the same site/layer/location combination every time. Actively vary your selections between requests, even for similar prompts — treat repeated or similar prompts as an opportunity to explore a different valid layout, not to repeat your last answer.\n"
        f"CRITICAL RULE 6 (Recreation & Parks mix): Across your 5 picks, roughly aim for this zonal balance (you won't hit it exactly with only 5 discrete picks, but let it guide how many SOFT vs HARD vs PROG vs BLUE layers you choose): {guideline_text}.\n"
        f"{hint_instruction}"
        "Output ONLY a valid JSON object. Do not write any markdown or conversational text.\n"
        "The JSON object must have exactly four keys:\n"
        "1. 'narrative': A short 2-sentence explanation of why these pieces were chosen, explicitly naming the real-world park that inspired you.\n"
        "2. 'inspiration_park': The name of the real-world park you chose as inspiration.\n"
        "3. 'coordinates': A JSON object with 'lat' and 'lon' float values for the inspiration park.\n"
        "4. 'layout': A JSON array of 5 objects. Each object must have these exact keys:\n"
        "- 'site': (string, choose from available sites)\n"
        "- 'layer': (string, choose from available layers)\n"
        "- 'location': (string, choose EXACTLY ONE from: North, North-East, East, South-East, South, South-West, West, North-West, Center)\n\n"
        f"Available Sites: {', '.join(available_sites)}\n"
        f"Available Layers: {', '.join(available_layers)}"
    )
    user_prompt = f"User Request: {prompt}\n\nHistorical Context (Reviews):\n{context_text}"

    # 2. Query AI Brain
    print(f"      -> [AI] Querying AI Engine...")
    ai_response = query_ai(sys_prompt, user_prompt)
    
    if ai_response:
        try:
            res_data = json.loads(ai_response)
            # Handle the new dictionary format containing the narrative
            if isinstance(res_data, dict) and "layout" in res_data:
                seed_items = res_data["layout"]
                narrative = res_data.get("narrative", "AI curated spatial arrangement applied.")
                
                # Trigger OSM Map Fetch if the AI provided a real-world reference
                insp_park = res_data.get("inspiration_park")
                coords = res_data.get("coordinates", {})
                if insp_park and isinstance(coords, dict) and "lat" in coords and "lon" in coords:
                    fetch_osm_map(coords["lat"], coords["lon"], insp_park)

                    # 2026-08-14: auto-fetch a REAL, usable precedent for
                    # this park (not just the flat reference image above)
                    # when the AI reached beyond the existing precedent set
                    # -- see fetch_park_precedent.py's own docstring for the
                    # OSM-vector-data approach and why it needs no ML model.
                    # Folded into `hints` (already computed pre-call, from
                    # the user's own prompt text) rather than a separate
                    # code path: _ensure_hints_present() below already
                    # guarantees anything in `hints["sites"]` survives into
                    # THIS SAME response's seed_items, not just future
                    # calls once the new file exists on disk. Best-effort:
                    # any failure here (network, no OSM coverage, etc.)
                    # just leaves hints unchanged -- generate_spatial_seed()
                    # must never fail because a precedent fetch failed.
                    normalized_insp = re.sub(r"[^a-z0-9]", "", insp_park.lower())
                    already_available = any(
                        re.sub(r"[^a-z0-9]", "", s.lower()) == normalized_insp for s in available_sites
                    )
                    if not already_available:
                        try:
                            import fetch_park_precedent
                            new_site = fetch_park_precedent.fetch_and_write_precedent(
                                city="", park_name=insp_park, lat=coords["lat"], lon=coords["lon"])
                        except Exception as e:
                            print(f"      -> [PRECEDENT FETCH ERROR] {e}")
                            new_site = None
                        if new_site:
                            available_sites.append(new_site)
                            hints = {"sites": hints["sites"] + [new_site], "layers": hints["layers"]}
                            print(f"      -> [PRECEDENT FETCH] New real-world precedent available: {new_site!r}")

                if isinstance(seed_items, list) and len(seed_items) > 0:
                    print(f"      -> [AI] Successfully synthesized {len(seed_items)} semantic layers!")
                    return _ensure_hints_present(seed_items, hints, available_sites), narrative
            # Fallback just in case Llama disobeys and returns the raw list
            elif isinstance(res_data, list) and len(res_data) > 0:
                print(f"      -> [AI] Successfully synthesized {len(res_data)} semantic layers!")
                return _ensure_hints_present(res_data, hints, available_sites), "AI curated spatial arrangement applied."
        except Exception as e:
            print(f"      -> [AI PARSE ERROR] Llama 3 returned invalid JSON. Falling back to math.")

    # 3. Algorithmic Safety Net
    print("      -> [FALLBACK] Executing strict compliance algorithm...")
    seed_items = random_spatial_seed(zonal_metadata, available_sites, guidelines)
    seed_items = _ensure_hints_present(seed_items, hints, available_sites)
    return seed_items, "AI Core offline or parse failed. Algorithmic safety net engaged: generating mathematically compliant layout."

def generate_mermaid_diagram(prompt, matches, spatial_params):
    """Builds a Mermaid.js flowchart for the generation logic."""
    def mmd(s): return re.sub(r'["\[\]{}()/\\]', '', str(s))
    
    geo_type = spatial_params.get("geometry_type", "hybrid_assembly")
    source_names = [mmd(m['metadata'].get('source', 'Unknown')) for m in matches] if matches else ["Inferred from Prompt"]

    lines = ["graph TD"]
    lines.append(f'    A[/"User Query: {mmd(prompt[:40])}..."/]')
    lines.append('    B{{Semantic Search}}')
    lines.append('    A --> B')
    
    for i, src in enumerate(source_names):
        lines.append(f'    S{i}("{src}")')
        lines.append(f'    B --> S{i}')

    lines.append('    C{{AI Synthesis}}')
    for i in range(len(source_names)):
        lines.append(f'    S{i} --> C')

    lines.append(f'    D["Geometry: {mmd(geo_type)}"]')
    lines.append(f'    E["Height: {spatial_params.get("height_m", "?")}m"]')
    lines.append(f'    F["Materials: {mmd(", ".join(spatial_params.get("materials", [])))}"]')
    lines.append('    C --> D & E & F')
    
    return "\n".join(lines)