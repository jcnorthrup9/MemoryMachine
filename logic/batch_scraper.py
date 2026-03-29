"""
batch_scraper.py
----------------
Autonomous data harvester for the 11 Memory Machine precedent sites.

For each site it runs three DuckDuckGo searches and one Wikipedia fetch,
then appends the results to the site's reviews text file in data/.

Run:
    .venv/Scripts/python.exe logic/batch_scraper.py
    .venv/Scripts/python.exe logic/batch_scraper.py --site schouwburgplein
    .venv/Scripts/python.exe logic/batch_scraper.py --force   # re-harvest even if already done
"""

import os, sys, time, random, textwrap, json, argparse, urllib.request, urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ── Site registry ─────────────────────────────────────────────────────────────
SITES = [
    {
        "id":           "pershing_square",
        "name":         "Pershing Square",
        "search_alias": "Pershing Square Los Angeles",
        "wiki_title":   "Pershing Square (Los Angeles)",
        "reviews_file": "pershing_square_reviews.txt",
        # relevance_terms: at least one must appear in a DDG result body (lowercase)
        "relevance":    ["pershing", "dtla", "legorreta", "olive street", "los angeles plaza"],
        "queries": [
            "\"Pershing Square\" Los Angeles park landscape design history",
            "\"Pershing Square\" DTLA public space redesign architecture",
            "\"Pershing Square\" Los Angeles visitor review experience",
        ],
    },
    {
        "id":           "schouwburgplein",
        "name":         "Schouwburgplein",
        "search_alias": "Schouwburgplein Rotterdam",
        "wiki_title":   "Schouwburgplein",
        "reviews_file": "schouwburgplein_reviews.txt",
        "relevance":    ["schouwburg", "rotterdam", "west 8", "light mast", "plaza"],
        "queries": [
            "Schouwburgplein Rotterdam public plaza West 8 landscape",
            "Schouwburgplein Rotterdam light masts architecture review",
            "Schouwburgplein Rotterdam urban square visitor experience",
        ],
    },
    {
        "id":           "grand_park_la",
        "name":         "Grand Park Los Angeles",
        "search_alias": "Grand Park Los Angeles downtown",
        "wiki_title":   "Grand Park (Los Angeles)",
        "reviews_file": "grand_park_la_reviews.txt",
        "relevance":    ["grand park", "downtown la", "dtla", "city hall", "splash pad", "grand avenue"],
        "queries": [
            "\"Grand Park\" \"Los Angeles\" downtown civic park landscape design",
            "\"Grand Park\" Los Angeles splash pad Crown Fountain review",
            "\"Grand Park\" DTLA visitor experience public space",
        ],
    },
    {
        "id":           "tanner_springs",
        "name":         "Tanner Springs Park",
        "search_alias": "Tanner Springs Park Portland Oregon",
        "wiki_title":   "Tanner Springs Park",
        "reviews_file": "tanner_springs_reviews.txt",
        "relevance":    ["tanner", "portland", "pearl district", "wetland", "stormwater", "railway"],
        "queries": [
            "\"Tanner Springs\" Portland Oregon wetland park landscape design",
            "\"Tanner Springs Park\" Pearl District review experience",
            "Tanner Springs Portland stormwater park railway tracks art",
        ],
    },
    {
        "id":           "gardens_by_the_bay",
        "name":         "Gardens by the Bay Supertree Grove",
        "search_alias": "Gardens by the Bay Singapore",
        "wiki_title":   "Gardens by the Bay",
        "reviews_file": "gardens_by_the_bay_reviews.txt",
        "relevance":    ["gardens by the bay", "supertree", "singapore", "marina bay", "grove"],
        "queries": [
            "\"Gardens by the Bay\" Singapore Supertree Grove landscape architecture",
            "\"Gardens by the Bay\" Singapore visitor review experience supertrees",
            "\"Supertree Grove\" Singapore vertical garden design analysis",
        ],
    },
    {
        "id":           "superkilen",
        "name":         "Superkilen Copenhagen",
        "search_alias": "Superkilen Copenhagen Norrebro",
        "wiki_title":   "Superkilen",
        "reviews_file": "superkilen_reviews.txt",
        "relevance":    ["superkilen", "copenhagen", "norrebro", "big architects", "topotek"],
        "queries": [
            "Superkilen Copenhagen Norrebro park BIG Topotek1 landscape design",
            "Superkilen park review visitor experience Copenhagen",
            "Superkilen linear park red black green zones architecture",
        ],
    },
    {
        "id":           "paley_park",
        "name":         "Paley Park New York",
        "search_alias": "Paley Park New York",
        "wiki_title":   "Paley Park",
        "reviews_file": "paley_park_reviews.txt",
        "relevance":    ["paley park", "53rd street", "waterfall", "vest-pocket", "manhattan", "water wall"],
        "queries": [
            "\"Paley Park\" New York vest-pocket park waterfall design",
            "\"Paley Park\" NYC visitor review experience urban oasis",
            "\"Paley Park\" Manhattan acoustic water wall landscape architecture",
        ],
    },
    {
        "id":           "klyde_warren_park",
        "name":         "Klyde Warren Park Dallas",
        "search_alias": "Klyde Warren Park Dallas Texas",
        "wiki_title":   "Klyde Warren Park",
        "reviews_file": "klyde_warren_park_reviews.txt",
        "relevance":    ["klyde warren", "dallas", "woodall rodgers", "freeway deck", "texas"],
        "queries": [
            "\"Klyde Warren Park\" Dallas Texas deck park freeway landscape",
            "\"Klyde Warren Park\" visitor review experience food trucks",
            "\"Klyde Warren Park\" Dallas design analysis urban park",
        ],
    },
    {
        "id":           "millennium_park",
        "name":         "Millennium Park Chicago",
        "search_alias": "Millennium Park Chicago",
        "wiki_title":   "Millennium Park",
        "reviews_file": "millennium_park_reviews.txt",
        "relevance":    ["millennium park", "chicago", "crown fountain", "cloud gate", "bean", "randolph"],
        "queries": [
            "\"Millennium Park\" Chicago \"Crown Fountain\" \"Cloud Gate\" landscape design",
            "\"Millennium Park\" Chicago visitor review experience Grant Park",
            "\"Millennium Park\" Chicago architecture Anish Kapoor Jaume Plensa",
        ],
    },
    {
        "id":           "parc_de_la_villette",
        "name":         "Parc de la Villette Paris",
        "search_alias": "Parc de la Villette Paris",
        "wiki_title":   "Parc de la Villette",
        "reviews_file": "parc_de_la_villette_reviews.txt",
        "relevance":    ["villette", "tschumi", "paris", "follies", "canal", "19th arrondissement"],
        "queries": [
            "\"Parc de la Villette\" Paris Tschumi follies landscape architecture",
            "\"Parc de la Villette\" Paris visitor review experience",
            "\"Parc de la Villette\" deconstructivist park design analysis",
        ],
    },
    {
        "id":           "zaryadye_park",
        "name":         "Zaryadye Park Moscow",
        "search_alias": "Zaryadye Park Moscow",
        "wiki_title":   "Zaryadye Park",
        "reviews_file": "zaryadye_park_reviews.txt",
        "relevance":    ["zaryadye", "moscow", "red square", "biome", "diller scofidio", "russia"],
        "queries": [
            "\"Zaryadye Park\" Moscow Russia Red Square landscape design",
            "\"Zaryadye Park\" Moscow visitor review experience biome",
            "Zaryadye Park Moscow Diller Scofidio floating bridge architecture",
        ],
    },
]

# ── DuckDuckGo search ─────────────────────────────────────────────────────────
def ddg_search(query, max_results=8):
    """Return a list of {title, body, href} dicts from DuckDuckGo text search."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        print(f"    [WARN] DDG search failed for '{query}': {e}")
        return []


def filter_relevant(results, relevance_terms):
    """Drop results whose body doesn't contain at least one relevance keyword."""
    if not relevance_terms:
        return results
    kept = []
    for r in results:
        combined = (r.get("title", "") + " " + r.get("body", "")).lower()
        if any(term.lower() in combined for term in relevance_terms):
            kept.append(r)
    return kept


def format_ddg_results(results, query):
    """Turn raw DDG result dicts into a readable text block."""
    if not results:
        return ""
    lines = [f"Search: \"{query}\""]
    for r in results:
        title = r.get("title", "").strip()
        body  = r.get("body",  "").strip()
        href  = r.get("href",  "").strip()
        if body:
            lines.append(f"\n  [{title}]")
            for para in textwrap.wrap(body, width=100):
                lines.append(f"  {para}")
            if href:
                lines.append(f"  Source: {href}")
    return "\n".join(lines)


# ── Wikipedia ─────────────────────────────────────────────────────────────────
def fetch_wikipedia(title):
    """Return the full plain-text extract for a Wikipedia article title."""
    params = urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "extracts",
        "exintro": False, "explaintext": True,
        "redirects": 1, "titles": title,
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "MemoryMachine/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pages = data.get("query", {}).get("pages", {})
        page  = next(iter(pages.values()))
        text  = page.get("extract", "").strip()
        return text if len(text) > 100 else ""
    except Exception as e:
        print(f"    [WARN] Wikipedia fetch failed for '{title}': {e}")
        return ""


# ── Per-site harvest ──────────────────────────────────────────────────────────
SECTION_MARKER = "--- DUCKDUCKGO + WIKIPEDIA HARVEST ---"

def harvest_site(site, force=False):
    out_path = os.path.join(DATA_DIR, site["reviews_file"])
    name     = site["name"]

    # Skip if already harvested (unless --force)
    if not force and os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            existing = f.read()
        if SECTION_MARKER in existing:
            print(f"  [SKIP] {name} — already harvested (use --force to re-run)")
            return

    print(f"\n  -- {name} --")

    # 1. Wikipedia
    print(f"    [1/4] Wikipedia: '{site['wiki_title']}'...")
    wiki_text = fetch_wikipedia(site["wiki_title"])
    if wiki_text:
        print(f"    [OK]  {len(wiki_text):,} chars")
    else:
        print(f"    [INFO] No Wikipedia article found")
    time.sleep(random.uniform(0.8, 1.8))

    # 2. DuckDuckGo searches (per-site curated queries)
    queries      = site.get("queries", [])
    relevance    = site.get("relevance", [])
    ddg_blocks   = []
    total        = len(queries)
    for i, q in enumerate(queries):
        print(f"    [{i+2}/{total+1}] DDG: '{q[:72]}'")
        raw     = ddg_search(q, max_results=8)
        results = filter_relevant(raw, relevance)
        if results:
            block = format_ddg_results(results, q)
            ddg_blocks.append(block)
            print(f"    [OK]  {len(results)}/{len(raw)} relevant results")
        else:
            print(f"    [WARN] 0 relevant results ({len(raw)} raw)")
        delay = random.uniform(2.5, 5.5)
        print(f"    [WAIT] {delay:.1f}s...")
        time.sleep(delay)

    # 3. Assemble output section
    section_parts = [
        f"\n\n{SECTION_MARKER}",
        f"Site: {name}",
        f"Harvested: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
        "=" * 72,
    ]

    if wiki_text:
        section_parts.append("\n[WIKIPEDIA]\n")
        # Include up to 6000 chars of Wikipedia text (enough for RAG)
        excerpt = wiki_text[:6000]
        if len(wiki_text) > 6000:
            excerpt += "\n[... truncated ...]"
        section_parts.append(excerpt)

    if ddg_blocks:
        section_parts.append("\n[DUCKDUCKGO SEARCH RESULTS]\n")
        section_parts.append("\n\n".join(ddg_blocks))

    section_text = "\n".join(section_parts)

    # 4. Write to file — strip any previous harvest section first (idempotent)
    base_content = ""
    if os.path.exists(out_path):
        with open(out_path, "r", encoding="utf-8") as f:
            raw = f.read()
        # Remove all previous DUCKDUCKGO harvest sections
        marker_idx = raw.find(f"\n\n{SECTION_MARKER}")
        if marker_idx == -1:
            marker_idx = raw.find(SECTION_MARKER)
        base_content = raw[:marker_idx].rstrip() if marker_idx != -1 else raw

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(base_content)
        f.write(section_text)

    print(f"    [OK]  Written {len(section_text):,} chars to {site['reviews_file']}")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Batch scraper for Memory Machine precedent sites")
    parser.add_argument("--site",  help="Run for a single site ID (e.g. schouwburgplein)")
    parser.add_argument("--force", action="store_true", help="Re-harvest even if already done")
    parser.add_argument("--list",  action="store_true", help="Print available site IDs and exit")
    args = parser.parse_args()

    if args.list:
        for s in SITES:
            print(f"  {s['id']:30s}  ->  {s['reviews_file']}")
        return

    targets = SITES
    if args.site:
        targets = [s for s in SITES if s["id"] == args.site]
        if not targets:
            print(f"[ERROR] Unknown site id '{args.site}'. Use --list to see options.")
            sys.exit(1)

    print(f"\n[BATCH SCRAPER] Harvesting {len(targets)} site(s)...\n")
    for site in targets:
        harvest_site(site, force=args.force)
        # inter-site delay
        if site is not targets[-1]:
            gap = random.uniform(3.0, 7.0)
            print(f"\n  [GAP] Waiting {gap:.1f}s before next site...")
            time.sleep(gap)

    print(f"\n[DONE] All {len(targets)} site(s) processed.")
    print(f"       Files are in: {DATA_DIR}")


if __name__ == "__main__":
    main()
