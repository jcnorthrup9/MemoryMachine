"""
precedent_scraper.py
--------------------
Two jobs for all 10 curated precedent sites:
  1. Capture satellite aerial images via Google Maps (Playwright)
  2. Scrape visitor reviews via TripAdvisor / Wikipedia (Scrapfly)

Run:
  .venv/Scripts/python.exe logic/precedent_scraper.py --satellites
  .venv/Scripts/python.exe logic/precedent_scraper.py --reviews
  .venv/Scripts/python.exe logic/precedent_scraper.py --all
"""

import os, sys, time, argparse, re, textwrap
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMG_DIR  = os.path.join(BASE_DIR, "assets", "precedents")
os.makedirs(IMG_DIR,  exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Site registry — coordinates tuned to show full site at a good zoom level
# ---------------------------------------------------------------------------
SITES = [
    {
        "id":       "pershing_square",
        "name":     "Pershing Square",
        "location": "Downtown Los Angeles, CA",
        "lat": 34.0483,  "lon": -118.2525,  "zoom": 18.0,
        "tripadvisor_slug": "Attraction_Review-g32655-d317892",  # Pershing Square DTLA
        "reviews_file": "pershing_square_reviews.txt",
    },
    {
        "id":       "schouwburgplein",
        "name":     "Schouwburgplein",
        "location": "Rotterdam, Netherlands",
        "lat": 51.9226,  "lon": 4.4726,   "zoom": 18.5,
        "tripadvisor_slug": "Attraction_Review-g188632-d2399500",
        "reviews_file": "schouwburgplein_reviews.txt",
    },
    {
        "id":       "grand_park_la",
        "name":     "Grand Park LA",
        "location": "Downtown Los Angeles, CA",
        "lat": 34.0563,  "lon": -118.2462,  "zoom": 17.5,
        "tripadvisor_slug": "Attraction_Review-g32655-d3568965",
        "reviews_file": "grand_park_la_reviews.txt",
    },
    {
        "id":       "tanner_springs",
        "name":     "Tanner Springs Park",
        "location": "Portland, OR",
        "lat": 45.5258,  "lon": -122.6841,  "zoom": 19.0,
        "tripadvisor_slug": "Attraction_Review-g52024-d2399027",
        "reviews_file": "tanner_springs_reviews.txt",
    },
    {
        "id":       "gardens_by_the_bay",
        "name":     "Gardens by the Bay",
        "location": "Singapore",
        "lat": 1.2816,   "lon": 103.8636,  "zoom": 16.5,
        "tripadvisor_slug": "Attraction_Review-g294265-d3208506",
        "reviews_file": "gardens_by_the_bay_reviews.txt",
    },
    {
        "id":       "superkilen",
        "name":     "Superkilen",
        "location": "Copenhagen, Denmark",
        "lat": 55.6964,  "lon": 12.5476,   "zoom": 16.5,
        "tripadvisor_slug": "Attraction_Review-g189541-d4332801",
        "reviews_file": "superkilen_reviews.txt",
    },
    {
        "id":       "paley_park",
        "name":     "Paley Park",
        "location": "New York, NY",
        "lat": 40.7601,  "lon": -73.9714,  "zoom": 20.0,
        "tripadvisor_slug": "Attraction_Review-g60763-d105497",
        "reviews_file": "paley_park_reviews.txt",
    },
    {
        "id":       "klyde_warren",
        "name":     "Klyde Warren Park",
        "location": "Dallas, TX",
        "lat": 32.7893,  "lon": -96.8021,  "zoom": 17.5,
        "tripadvisor_slug": "Attraction_Review-g55711-d5040960",
        "reviews_file": "klyde_warren_park_reviews.txt",
    },
    {
        "id":       "millennium_park",
        "name":     "Millennium Park",
        "location": "Chicago, IL",
        "lat": 41.8826,  "lon": -87.6226,  "zoom": 17.0,
        "tripadvisor_slug": "Attraction_Review-g35805-d143394",
        "reviews_file": "millennium_park_reviews.txt",
    },
    {
        "id":       "parc_de_la_villette",
        "name":     "Parc de la Villette",
        "location": "Paris, France",
        "lat": 48.8937,  "lon": 2.3931,    "zoom": 16.5,
        "tripadvisor_slug": "Attraction_Review-g187147-d197004",
        "reviews_file": "parc_de_la_villette_reviews.txt",
    },
    {
        "id":       "zaryadye_park",
        "name":     "Zaryadye Park",
        "location": "Moscow, Russia",
        "lat": 55.7510,  "lon": 37.6262,   "zoom": 17.0,
        "tripadvisor_slug": "Attraction_Review-g298484-d12659840",
        "reviews_file": "zaryadye_park_reviews.txt",
    },
    {
        "id":       "piazza_del_campo",
        "name":     "Piazza del Campo",
        "location": "Siena, Italy",
        "lat": 43.3183,  "lon": 11.3315,   "zoom": 18.0,
        "tripadvisor_slug": "Attraction_Review-g187902-d195175",
        "reviews_file": "piazza_del_campo_reviews.txt",
    },
    {
        "id":       "the_high_line",
        "name":     "The High Line",
        "location": "New York, NY",
        "lat": 40.7475,  "lon": -74.0048,  "zoom": 18.0,
        "tripadvisor_slug": "Attraction_Review-g60763-d1487011",
        "reviews_file": "the_high_line_reviews.txt",
    },
    {
        "id":       "federation_square",
        "name":     "Federation Square",
        "location": "Melbourne, Australia",
        "lat": -37.8179, "lon": 144.9690,  "zoom": 18.5,
        "tripadvisor_slug": "Attraction_Review-g255100-d257256",
        "reviews_file": "federation_square_reviews.txt",
    },
    {
        "id":       "pioneer_courthouse_square",
        "name":     "Pioneer Courthouse Square",
        "location": "Portland, OR",
        "lat": 45.5191,  "lon": -122.6793, "zoom": 19.0,
        "tripadvisor_slug": "Attraction_Review-g52024-d126779",
        "reviews_file": "pioneer_courthouse_square_reviews.txt",
    },
]

# Active test scope — first 8 sites (Pershing Square → Klyde Warren Park)
ACTIVE_SITES = SITES[:8]

# ---------------------------------------------------------------------------
# 1. Satellite capture
# ---------------------------------------------------------------------------
def capture_satellites(sites=None):
    from playwright.sync_api import sync_playwright

    targets = sites or SITES
    print(f"\n[SATELLITE] Capturing {len(targets)} sites...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for site in targets:
            out_path = os.path.join(IMG_DIR, f"{site['id']}_satellite.jpg")
            if os.path.exists(out_path):
                print(f"  [SKIP] {site['name']} — image already exists")
                continue

            print(f"  -> Capturing {site['name']} ({site['lat']}, {site['lon']})...")
            url = (
                f"https://www.google.com/maps/@{site['lat']},{site['lon']},"
                f"{site['zoom']}z/data=!3m1!1e3"
            )

            page = browser.new_page(viewport={"width": 1100, "height": 660})
            try:
                page.goto(url, wait_until="load", timeout=60000)
                time.sleep(8)  # wait for satellite tiles to fully render
                # Aggressively hide all Google Maps UI — only keep the map canvas
                page.evaluate("""() => {
                    const hide = [
                        // search bar and top nav
                        '#omnibox-container', '.searchbox', '.tactile-searchbox',
                        '.app-horizontal-widget-holder', '.Hk4XGb', '.gb_hd',
                        // left sidebar panel
                        '#navigation-card-for-places', '#pane', '.widget-pane',
                        '#assistive-chips', '#sb_cb', '.cards-container',
                        '[data-value="Restaurants"]',
                        // traffic / info overlays
                        '#titlecard', '#minimap', '.app-viewcard-strip',
                        '.scene-footer', '.app-timeline-container',
                        // bottom bar / footer
                        '.scene-footer-container', '#watermark',
                        // pins, markers, controls
                        '.gmnoprint', '.gm-control-active', '.gm-svpc',
                        '.gm-fullscreen-control', '.gm-bundled-control',
                        '.vasqq', '.wo101b', '.dismissButton',
                        // Get app / sign in banners
                        '.app-install-promo', '.widget-settings-button',
                        '[data-ogsr-up]', '.ml-promotion-chip-container',
                        // layers button, zoom, compass
                        '.loDimf', '.mapsConsumerUi',
                    ];
                    hide.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            el.style.setProperty('display', 'none', 'important');
                        });
                    });
                }""")
                time.sleep(1.5)
                page.screenshot(path=out_path, type="jpeg", quality=95)
                print(f"     [OK] Saved: {out_path}")
            except Exception as e:
                print(f"     [ERROR] {site['name']}: {e}")
            finally:
                page.close()

        browser.close()

    print(f"\n[SATELLITE] Done. Images in: {IMG_DIR}")


# ---------------------------------------------------------------------------
# 2. Review scraping via TripAdvisor (Scrapfly)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Wikipedia titles for each site
# ---------------------------------------------------------------------------
WIKIPEDIA_TITLES = {
    "pershing_square":      "Pershing Square (Los Angeles)",
    "schouwburgplein":      "Schouwburgplein",
    "grand_park_la":        "Grand Park (Los Angeles)",
    "tanner_springs":       "Tanner Springs Park",
    "gardens_by_the_bay":   "Gardens by the Bay",
    "superkilen":           "Superkilen",
    "paley_park":           "Paley Park",
    "klyde_warren":         "Klyde Warren Park",
    "millennium_park":      "Millennium Park",
    "parc_de_la_villette":  "Parc de la Villette",
    "zaryadye_park":        "Zaryadye Park",
    "piazza_del_campo":           "Piazza del Campo",
    "the_high_line":              "High Line",
    "federation_square":          "Federation Square",
    "pioneer_courthouse_square":  "Pioneer Courthouse Square",
}


def fetch_wikipedia_text(title):
    """Fetch full article extract from Wikipedia API."""
    import urllib.request, json
    params = urllib.parse.urlencode({
        "action":    "query",
        "titles":    title,
        "prop":      "extracts",
        "explaintext": True,
        "exsectionformat": "plain",
        "format":    "json",
    })
    url = f"https://en.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "MemoryMachine/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    pages = data.get("query", {}).get("pages", {})
    page  = next(iter(pages.values()))
    return page.get("extract", "")


def synthesize_with_gemini(site_name, wiki_text):
    """
    Use Gemini to distill the Wikipedia article into
    rich spatial / sensory observations suitable for the RAG corpus.
    """
    try:
        from dotenv import load_dotenv
        import google.generativeai as genai
        load_dotenv(os.path.join(BASE_DIR, ".env"))
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
    except ImportError:
        return None

    source_section = (
        f"WIKIPEDIA SOURCE:\n{wiki_text[:8000]}" if wiki_text
        else "Draw on your knowledge of this site to write the observations."
    )
    prompt = (
        f"You are a spatial analyst and architectural writer. "
        f"Write 8-10 detailed paragraphs of spatial, sensory, and experiential observations about '{site_name}'. "
        f"Focus on: acoustic qualities, material textures, thermal conditions, shade, water, "
        f"social dynamics, scale, sequence, and how the space performs at different times of day. "
        f"Write in a qualitative, descriptive register — like a combination of visitor observations "
        f"and architectural criticism. Do NOT use headers. Just dense, rich paragraphs.\n\n"
        f"{source_section}"
    )
    model    = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    return response.text.strip()


def scrape_reviews(sites=None):
    targets = sites or SITES
    print(f"\n[REVIEWS] Fetching Wikipedia + Gemini synthesis for {len(targets)} sites...\n")

    for site in targets:
        out_path = os.path.join(DATA_DIR, site["reviews_file"])

        # Only skip if already enriched
        if os.path.exists(out_path):
            with open(out_path, "r", encoding="utf-8") as f:
                existing = f.read()
            if "WIKIPEDIA + GEMINI" in existing:
                print(f"  [SKIP] {site['name']} — already enriched")
                continue

        wiki_title = WIKIPEDIA_TITLES.get(site["id"])
        print(f"  -> Fetching Wikipedia: '{wiki_title}'...")
        try:
            wiki_text = fetch_wikipedia_text(wiki_title)
        except Exception as e:
            print(f"    [ERROR] Wikipedia fetch failed: {e}")
            continue

        if not wiki_text or len(wiki_text) < 200:
            print(f"    [INFO] No Wikipedia article — using Gemini knowledge synthesis directly...")
            wiki_text = None

        if wiki_text:
            print(f"    [OK] Got {len(wiki_text)} chars from Wikipedia. Synthesizing with Gemini...")
        synthesis = synthesize_with_gemini(site["name"], wiki_text or "")

        if synthesis:
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n--- WIKIPEDIA + GEMINI SYNTHESIS ---\n\n")
                f.write(synthesis)
            print(f"    [OK] Appended synthesis to {site['reviews_file']}")
        else:
            print(f"    [WARN] Gemini synthesis failed for {site['name']}")

        time.sleep(1)  # be polite to Wikipedia

    print(f"\n[REVIEWS] Done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape satellite images and reviews for all 10 precedent sites."
    )
    parser.add_argument("--satellites", action="store_true", help="Capture Google Maps satellite images")
    parser.add_argument("--reviews",    action="store_true", help="Scrape TripAdvisor visitor reviews")
    parser.add_argument("--all",        action="store_true", help="Run both satellites and reviews")
    parser.add_argument("--site",       type=str, default=None,
                        help="Run for a single site by id (e.g. --site paley_park)")
    args = parser.parse_args()

    # Filter to single site if requested
    targets = SITES
    if args.site:
        targets = [s for s in SITES if s["id"] == args.site]
        if not targets:
            print(f"[ERROR] Unknown site id '{args.site}'. Valid ids: {[s['id'] for s in SITES]}")
            sys.exit(1)

    if not (args.satellites or args.reviews or args.all):
        parser.print_help()
        sys.exit(0)

    if args.satellites or args.all:
        capture_satellites(targets)

    if args.reviews or args.all:
        scrape_reviews(targets)
