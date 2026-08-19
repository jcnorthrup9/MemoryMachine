"""
Single source of truth for the precedent-library park roster: the 52
parks already fetched (data/PershingMetabolizer/parkSVG/PrecedentSVG/*.svg,
mirrors data/park_rating_check.json's 50 entries plus 2 later additions --
Grand Park and Sydney Botanic Garden -- that were never backfilled into
that file), the 98 new international parks being added to reach exactly
150, and the tile->3-park grouping the slide deck's page-04 grid reads.

150 was chosen deliberately over a literal "+100" (52+98=150, not 152) so
the total divides evenly across the deck's existing 10x5 = 50-tile
wallpaper grid at exactly 3 parks/tile, no remainder.

Three of the 52 -- Schouwburgplein, Parc de la Villette, Zaryadye Park --
are flagged replace=True: they're the last hand-drawn (pre-OSM-pipeline)
SVGs left in the library (dated 2026-07-14, vs. the Aug-2026 auto-fetched
majority) and get force-refetched through the same OSM pipeline so every
precedent in the library shares one visual style. Pershing Square is
deliberately NOT flagged -- see ingest_diagram_svg.py's _load_precedent_svg
docstring: it's the scale/coordinate anchor for the live generation app,
not a comparison precedent, and a past incident there already documents
what happens if this file's boundary dimensions shift underneath it.

scripts/batch_fetch_precedents.py and scripts/build_precedent_grid_data.py
both import from this module rather than duplicating park data, so the
roster only ever needs editing in one place. (Lives in scripts/, not
data/ -- this repo's .gitignore blanket-excludes data/ for large/
regenerable content, which would silently drop this source module from
version control; see that file's own comment on the same issue for the
lora_datasets manifests.)
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fetch_park_precedent import safe_site_name  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# The 52 parks already in the library.
# ─────────────────────────────────────────────────────────────────────────
EXISTING_PARKS = [
    {"name": "Pershing Square", "city": "Los Angeles", "region": "namerica"},
    {"name": "Al-Azhar Park", "city": "Cairo", "region": "africa"},
    {"name": "Beihai Park", "city": "Beijing", "region": "eastasia"},
    {"name": "Chapultepec Park", "city": "Mexico City", "region": "namerica"},
    {"name": "Cheviot Hills Park", "city": "Los Angeles", "region": "namerica"},
    {"name": "Cornwall Park", "city": "Auckland", "region": "oceania"},
    {"name": "Cubbon Park", "city": "Bangalore", "region": "southasia"},
    {"name": "Frognerparken", "city": "Oslo", "region": "europe"},
    {"name": "Gardens by the Bay", "city": "Singapore", "region": "seasia"},
    {"name": "Golden Gate Park", "city": "San Francisco", "region": "namerica"},
    {"name": "Gulhane Park", "city": "Istanbul", "region": "europe"},
    {"name": "Hyde Park", "city": "London", "region": "europe"},
    {"name": "Ibirapuera Park", "city": "Sao Paulo", "region": "samerica"},
    {"name": "Kirstenbosch National Botanical Garden", "city": "Cape Town", "region": "africa"},
    {"name": "Lazienki Park", "city": "Warsaw", "region": "europe"},
    {"name": "Lumphini Park", "city": "Bangkok", "region": "seasia"},
    {"name": "Namsan Park", "city": "Seoul", "region": "eastasia"},
    {"name": "Parc de la Villette", "city": "Paris", "region": "europe", "replace": True},
    {"name": "Parque Centenario", "city": "Buenos Aires", "region": "samerica"},
    {"name": "Parque del Retiro", "city": "Madrid", "region": "europe"},
    {"name": "Phoenix Park", "city": "Dublin", "region": "europe"},
    {"name": "Prater", "city": "Vienna", "region": "europe"},
    {"name": "Prospect Park", "city": "New York", "region": "namerica"},
    {"name": "Royal Botanic Garden", "city": "Sydney", "region": "oceania"},
    {"name": "Schouwburgplein", "city": "Rotterdam", "region": "europe", "replace": True},
    {"name": "Stanley Park", "city": "Vancouver", "region": "namerica"},
    {"name": "Tao Dan Park", "city": "Ho Chi Minh City", "region": "seasia"},
    {"name": "Tiergarten", "city": "Berlin", "region": "europe"},
    {"name": "Ueno Park", "city": "Tokyo", "region": "eastasia"},
    {"name": "Uhuru Gardens", "city": "Nairobi", "region": "africa"},
    {"name": "Villa Borghese", "city": "Rome", "region": "europe"},
    {"name": "Vondelpark", "city": "Amsterdam", "region": "europe"},
    {"name": "Yoyogi Park", "city": "Tokyo", "region": "eastasia"},
    {"name": "Zaryadye Park", "city": "Moscow", "region": "europe", "replace": True},
    {"name": "Central Park", "city": "New York", "region": "namerica"},
    {"name": "Griffith Park", "city": "Los Angeles", "region": "namerica"},
    {"name": "Millennium Park", "city": "Chicago", "region": "namerica"},
    {"name": "Regent's Park", "city": "London", "region": "europe"},
    {"name": "Bois de Boulogne", "city": "Paris", "region": "europe"},
    {"name": "Englischer Garten", "city": "Munich", "region": "europe"},
    {"name": "Kadriorg Park", "city": "Tallinn", "region": "europe"},
    {"name": "Peterhof", "city": "Russia", "region": "europe"},
    {"name": "Nara Park", "city": "Nara", "region": "eastasia"},
    {"name": "Yuyuan Garden", "city": "Shanghai", "region": "eastasia"},
    {"name": "Lodhi Gardens", "city": "Delhi", "region": "southasia"},
    {"name": "Hibiya Park", "city": "Tokyo", "region": "eastasia"},
    {"name": "Kings Park", "city": "Perth", "region": "oceania"},
    {"name": "Fitzroy Gardens", "city": "Melbourne", "region": "oceania"},
    {"name": "Parque Tres de Febrero", "city": "Buenos Aires", "region": "samerica"},
    {"name": "High Line", "city": "New York", "region": "namerica"},
    {"name": "Grand Park", "city": "Los Angeles", "region": "namerica"},
    {"name": "Sydney Botanic Garden", "city": "Sydney", "region": "oceania"},
]

REPLACE_PARKS = [p for p in EXISTING_PARKS if p.get("replace")]

# ─────────────────────────────────────────────────────────────────────────
# 98 new international parks. Curated for breadth: every populated
# continent/region, mixing typologies (urban plazas, botanical gardens,
# waterfront parks, national-urban parks, palace/heritage gardens) rather
# than repeating one park archetype. Deduped against EXISTING_PARKS below
# by both (name, city) and safe_site_name() collision at import time.
# ─────────────────────────────────────────────────────────────────────────
NEW_PARKS = [
    # Europe
    {"name": "Parc de la Ciutadella", "city": "Barcelona", "region": "europe"},
    {"name": "Jardins du Luxembourg", "city": "Paris", "region": "europe"},
    {"name": "Giardino di Boboli", "city": "Florence", "region": "europe"},
    {"name": "Villa Pamphili", "city": "Rome", "region": "europe"},
    {"name": "Parco Sempione", "city": "Milan", "region": "europe"},
    {"name": "Jardim da Estrela", "city": "Lisbon", "region": "europe"},
    {"name": "Jardins do Palacio de Cristal", "city": "Porto", "region": "europe"},
    {"name": "National Garden", "city": "Athens", "region": "europe"},
    {"name": "Stadspark", "city": "Antwerp", "region": "europe"},
    {"name": "Bois de la Cambre", "city": "Brussels", "region": "europe"},
    {"name": "Amsterdamse Bos", "city": "Amsterdam", "region": "europe"},
    {"name": "Kungstradgarden", "city": "Stockholm", "region": "europe"},
    {"name": "Orstedsparken", "city": "Copenhagen", "region": "europe"},
    {"name": "Esplanadi Park", "city": "Helsinki", "region": "europe"},
    {"name": "Laugardalur", "city": "Reykjavik", "region": "europe"},
    {"name": "Stadtpark", "city": "Vienna", "region": "europe"},
    {"name": "Olympiapark", "city": "Munich", "region": "europe"},
    {"name": "Treptower Park", "city": "Berlin", "region": "europe"},
    {"name": "Letna Park", "city": "Prague", "region": "europe"},
    {"name": "Margaret Island", "city": "Budapest", "region": "europe"},
    {"name": "Cismigiu Gardens", "city": "Bucharest", "region": "europe"},
    {"name": "Borisova Gradina", "city": "Sofia", "region": "europe"},
    {"name": "Maksimir Park", "city": "Zagreb", "region": "europe"},
    {"name": "Tivoli Park", "city": "Ljubljana", "region": "europe"},
    {"name": "Ogrod Saski", "city": "Warsaw", "region": "europe"},
    {"name": "Gorky Park", "city": "Moscow", "region": "europe"},
    {"name": "Summer Garden", "city": "Saint Petersburg", "region": "europe"},
    {"name": "Genclik Parki", "city": "Ankara", "region": "europe"},
    {"name": "Emirgan Park", "city": "Istanbul", "region": "europe"},
    {"name": "Yarkon Park", "city": "Tel Aviv", "region": "mideast"},
    {"name": "Kelvingrove Park", "city": "Glasgow", "region": "europe"},
    {"name": "Princes Street Gardens", "city": "Edinburgh", "region": "europe"},
    {"name": "St Stephen's Green", "city": "Dublin", "region": "europe"},
    {"name": "Bute Park", "city": "Cardiff", "region": "europe"},
    {"name": "Botanic Gardens", "city": "Belfast", "region": "europe"},

    # North / Central America
    {"name": "Washington Square Park", "city": "New York", "region": "namerica"},
    {"name": "Dolores Park", "city": "San Francisco", "region": "namerica"},
    {"name": "Lincoln Park", "city": "Chicago", "region": "namerica"},
    {"name": "Discovery Park", "city": "Seattle", "region": "namerica"},
    {"name": "Forest Park", "city": "Portland", "region": "namerica"},
    {"name": "Boston Common", "city": "Boston", "region": "namerica"},
    {"name": "Rock Creek Park", "city": "Washington", "region": "namerica"},
    {"name": "Fairmount Park", "city": "Philadelphia", "region": "namerica"},
    {"name": "Zilker Park", "city": "Austin", "region": "namerica"},
    {"name": "City Park", "city": "Denver", "region": "namerica"},
    {"name": "South Pointe Park", "city": "Miami", "region": "namerica"},
    {"name": "High Park", "city": "Toronto", "region": "namerica"},
    {"name": "Mount Royal Park", "city": "Montreal", "region": "namerica"},
    {"name": "Queen Elizabeth Park", "city": "Vancouver", "region": "namerica"},
    {"name": "Parque Mexico", "city": "Mexico City", "region": "namerica"},
    {"name": "Parque Fundidora", "city": "Monterrey", "region": "namerica"},
    {"name": "Bosque Los Colomos", "city": "Guadalajara", "region": "namerica"},
    {"name": "Parque Almendares", "city": "Havana", "region": "namerica"},
    {"name": "Parque Omar", "city": "Panama City", "region": "namerica"},
    {"name": "Parque La Sabana", "city": "San Jose", "region": "namerica"},

    # South America
    {"name": "Parque do Flamengo", "city": "Rio de Janeiro", "region": "samerica"},
    {"name": "Parque El Ejido", "city": "Quito", "region": "samerica"},
    {"name": "Parque Kennedy", "city": "Lima", "region": "samerica"},
    {"name": "Parque Simon Bolivar", "city": "Bogota", "region": "samerica"},
    {"name": "Parque Forestal", "city": "Santiago", "region": "samerica"},
    {"name": "Parque Rodo", "city": "Montevideo", "region": "samerica"},
    {"name": "Parque del Este", "city": "Caracas", "region": "samerica"},

    # Africa
    {"name": "Karura Forest", "city": "Nairobi", "region": "africa"},
    {"name": "Company's Garden", "city": "Cape Town", "region": "africa"},
    {"name": "Zoo Lake", "city": "Johannesburg", "region": "africa"},
    {"name": "Menara Gardens", "city": "Marrakech", "region": "africa"},
    {"name": "Unity Park", "city": "Addis Ababa", "region": "africa"},
    {"name": "Parc du Belvedere", "city": "Tunis", "region": "africa"},
    {"name": "Parc de la Ligue Arabe", "city": "Casablanca", "region": "africa"},

    # Middle East
    {"name": "Zabeel Park", "city": "Dubai", "region": "mideast"},
    {"name": "Khalifa Park", "city": "Abu Dhabi", "region": "mideast"},
    {"name": "Aspire Park", "city": "Qatar", "region": "mideast"},
    {"name": "Salam Park", "city": "Riyadh", "region": "mideast"},
    {"name": "Horsh Beirut", "city": "Beirut", "region": "mideast"},
    {"name": "Riyam Park", "city": "Muscat", "region": "mideast"},

    # South Asia
    {"name": "Hanging Gardens", "city": "Mumbai", "region": "southasia"},
    {"name": "Maidan", "city": "Kolkata", "region": "southasia"},
    {"name": "Semmozhi Poonga", "city": "Chennai", "region": "southasia"},
    {"name": "Viharamahadevi Park", "city": "Colombo", "region": "southasia"},
    {"name": "Ramna Park", "city": "Dhaka", "region": "southasia"},

    # Southeast Asia
    {"name": "Perdana Botanical Garden", "city": "Kuala Lumpur", "region": "seasia"},
    {"name": "Taman Suropati", "city": "Jakarta", "region": "seasia"},
    {"name": "Rizal Park", "city": "Manila", "region": "seasia"},
    {"name": "Thong Nhat Park", "city": "Hanoi", "region": "seasia"},
    {"name": "Kandawgyi Park", "city": "Yangon", "region": "seasia"},

    # East Asia
    {"name": "Hong Kong Park", "city": "Hong Kong", "region": "eastasia"},
    {"name": "Da'an Forest Park", "city": "Taipei", "region": "eastasia"},
    {"name": "Osaka Castle Park", "city": "Osaka", "region": "eastasia"},
    {"name": "Maruyama Park", "city": "Kyoto", "region": "eastasia"},
    {"name": "Yongdusan Park", "city": "Busan", "region": "eastasia"},
    {"name": "People's Park", "city": "Chengdu", "region": "eastasia"},
    {"name": "Tang Paradise", "city": "Xi'an", "region": "eastasia"},
    {"name": "Yuexiu Park", "city": "Guangzhou", "region": "eastasia"},

    # Oceania
    {"name": "Wellington Botanic Garden", "city": "Wellington", "region": "oceania"},
    {"name": "New Farm Park", "city": "Brisbane", "region": "oceania"},
    {"name": "Rymill Park", "city": "Adelaide", "region": "oceania"},
    {"name": "Commonwealth Park", "city": "Canberra", "region": "oceania"},
    {"name": "Royal Tasmanian Botanical Gardens", "city": "Hobart", "region": "oceania"},
]

assert len(NEW_PARKS) == 98, f"expected 98 new parks, got {len(NEW_PARKS)}"

ALL_PARKS = EXISTING_PARKS + NEW_PARKS
assert len(ALL_PARKS) == 150, f"expected 150 total parks, got {len(ALL_PARKS)}"


def _dedupe_check():
    """Real de-duplication, not just 'tried to avoid': collide on both the
    literal (name, city) pair and on safe_site_name() output (two
    differently-punctuated names can still collapse onto the same on-disk
    filename, e.g. an apostrophe or diacritic difference)."""
    seen_pairs = {}
    seen_safe = {}
    for entry in ALL_PARKS:
        pair = (entry["name"].strip().lower(), entry["city"].strip().lower())
        safe = safe_site_name(entry["name"]).lower()
        if pair in seen_pairs:
            raise ValueError(f"duplicate (name, city): {entry} collides with {seen_pairs[pair]}")
        if safe in seen_safe:
            raise ValueError(
                f"safe_site_name collision: {entry!r} -> {safe!r}, "
                f"already used by {seen_safe[safe]!r}"
            )
        seen_pairs[pair] = entry
        seen_safe[safe] = entry


_dedupe_check()


# ─────────────────────────────────────────────────────────────────────────
# Tile grouping: 50 tiles x 3 parks, region-diversity-aware. Deterministic
# given ALL_PARKS' fixed order and this algorithm -- no randomness here, so
# re-importing this module never reshuffles which parks share a tile.
# ─────────────────────────────────────────────────────────────────────────
NUM_TILES = 50
PARKS_PER_TILE = 3

# Deck-grid-only exclusion: 2026-08-19, the user asked (in a parallel
# session -- see HANDOFF_08192026_PERSHING_REMOVED_FROM_PRECEDENT_GRID.md)
# for Pershing Square to stay in the roster/pipeline everywhere else but be
# dropped from the page-04 tiled grid specifically -- it's the site being
# designed FOR, not a comparison precedent (same reasoning as it never
# getting replace=True above). That session hand-patched the deck's
# embedded JSON as a one-off since a full rebuild would've collided with
# this module's own in-flight edits; making the exclusion a first-class
# part of tile-group computation means any future
# scripts/build_precedent_grid_data.py run keeps honoring it instead of
# silently reintroducing Pershing Square on the next regen. Balboa Park
# (San Diego) already exists on disk (SVG + thumbnail, fetched by that
# same session) as its grid-only substitute, keeping the grid at exactly
# 150 entries / 50 tiles x 3. EXISTING_PARKS/ALL_PARKS/NEW_PARKS are
# untouched by this -- Pershing Square is still entry #1 there, still used
# by everything else that reads this module.
GRID_EXCLUDE_NAMES = {"Pershing Square"}
GRID_SUBSTITUTE_PARKS = [
    {"name": "Balboa Park", "city": "San Diego", "region": "namerica"},
]


def _compute_tile_groups():
    """Buckets the grid's park list (ALL_PARKS with GRID_EXCLUDE_NAMES
    swapped out for GRID_SUBSTITUTE_PARKS) by region, then round-robins
    across region buckets filling tiles left-to-right -- so each tile's 3
    parks are pulled from different points in the region rotation
    (adjacent picks in the same bucket land in different tiles), which in
    practice keeps any one tile from being 3 same-region parks unless a
    region bucket is large enough to wrap back around within one tile's 3
    slots."""
    grid_parks = [p for p in ALL_PARKS if p["name"] not in GRID_EXCLUDE_NAMES] + GRID_SUBSTITUTE_PARKS
    assert len(grid_parks) == len(ALL_PARKS), (
        f"grid park count drifted from ALL_PARKS: {len(grid_parks)} vs {len(ALL_PARKS)} "
        f"-- GRID_EXCLUDE_NAMES/GRID_SUBSTITUTE_PARKS must stay 1:1"
    )

    by_region = {}
    for entry in grid_parks:
        by_region.setdefault(entry["region"], []).append(entry)

    regions = sorted(by_region.keys())
    cursors = {r: 0 for r in regions}
    remaining = sum(len(v) for v in by_region.values())

    groups = [[] for _ in range(NUM_TILES)]
    tile_idx = 0
    region_idx = 0
    while remaining > 0:
        region = regions[region_idx % len(regions)]
        region_idx += 1
        bucket = by_region[region]
        cur = cursors[region]
        if cur < len(bucket):
            groups[tile_idx % NUM_TILES].append(bucket[cur])
            cursors[region] += 1
            tile_idx += 1
            remaining -= 1

    for i, g in enumerate(groups):
        assert len(g) == PARKS_PER_TILE, f"tile {i} has {len(g)} parks, expected {PARKS_PER_TILE}: {g}"
    return groups


TILE_GROUPS = _compute_tile_groups()


def safe_name(entry):
    """Thin wrapper so every downstream script (batch runner, thumbnail
    generator, deck-data builder) derives SVG/thumbnail filenames the same
    way, via the one canonical implementation in fetch_park_precedent.py."""
    return safe_site_name(entry["name"])


if __name__ == "__main__":
    print(f"{len(EXISTING_PARKS)} existing + {len(NEW_PARKS)} new = {len(ALL_PARKS)} total parks")
    print(f"{len(REPLACE_PARKS)} flagged for hand-built replacement: "
          f"{[p['name'] for p in REPLACE_PARKS]}")
    print(f"{len(TILE_GROUPS)} tiles x {PARKS_PER_TILE} parks/tile")
