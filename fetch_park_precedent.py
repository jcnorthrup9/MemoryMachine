"""
Fetches a real-world park's geometry from OpenStreetMap (geocoded via
Nominatim, tagged features via the Overpass API -- both free, no API key)
and writes it as a new precedent SVG matching the exact schema
ingest_diagram_svg.py already parses for the 5 hand-built precedent sites
(data/PershingMetabolizer/parkSVG/PrecedentSVG/*.svg): <g id="CATEGORY">
groups of filled <path>/<circle> elements, plus a BOUNDARY group.

Vector OSM tags instead of a scraped satellite image + CV segmentation --
OSM already tags real parks with exactly the categories this app uses
(leisure=park -> GREEN_SPACE, natural=water -> WATER_FEATURES, etc.), so
no ML model is needed.

Once written, the new file needs ZERO changes anywhere else -- remix_layers()/
random_spatial_seed()'s available_sites is already built by listing this
same directory at runtime (see logic/ai_synthesizer.py,
logic/urban_engine.py), so the new site becomes usable immediately. See
logic/ai_synthesizer.py's generate_spatial_seed() for how this gets
triggered AUTOMATICALLY when the AI names a real-world park outside the
existing precedent set, not just via this file's manual CLI.

The core entry point is fetch_and_write_precedent() -- callable from other
code, never raises for an ordinary "couldn't find/fetch this park" outcome
(returns None instead), so a caller can fall back gracefully rather than
crash a live generation. main() below is a thin CLI wrapper around it.

Usage: python fetch_park_precedent.py "<city>" "<park name>" [--force]
Output: data/PershingMetabolizer/parkSVG/PrecedentSVG/{SafeName}.svg
"""
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

import requests
from shapely.geometry import LineString, Polygon
from shapely.validation import make_valid


def _log(msg):
    """print(), but survives non-Latin place names on a Windows console
    stuck on a narrow codepage (e.g. cp1252) -- confirmed live: geocoding
    "Yoyogi Park" returned a display_name containing Japanese characters,
    which crashed a plain print() with UnicodeEncodeError. Encodes to
    whatever the console actually supports, substituting anything it can't
    represent, rather than reconfiguring sys.stdout globally (this module
    can be imported into a long-running server process via
    generate_spatial_seed()'s auto-trigger -- changing process-wide stdout
    encoding as an import side effect would be surprising)."""
    enc = sys.stdout.encoding or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
PRECEDENT_DIR = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")

USER_AGENT = "MemoryMachine-PershingMetabolizer/1.0 (thesis project; contact via repo)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

CONTEXT_PAD_M = 60.0   # how far beyond the park's own bbox to pull surrounding streets -- tightened
                        # 2026-08-14 (was 150.0): a smaller pad keeps the park's own
                        # detail dominant in the frame instead of diluted by excess
                        # surrounding street context ("closer range" per live feedback)
PX_PER_METER = 3.0       # local pixel scale -- roughly matches the existing precedent SVGs' scale
METERS_PER_DEG = 111320.0
MAX_DISPLAY_DIM = 1400.0  # cap on the SVG's displayed width/height (pt) -- see build_svg()'s own comment
RING_STITCH_TOLERANCE_DEG = 1e-6  # ~0.1m at typical latitudes -- endpoint-matching tolerance for multipolygon ring assembly

# OSM tag (key, value-regex) -> (canonical layer id, geometry kind, real-world
# width in meters for "line" kinds). First match wins, checked in this
# order -- e.g. a way tagged both leisure=park and highway=footway
# (shouldn't happen in practice, but) would resolve to GREEN_SPACE first.
#
# 2026-08-14: geometry kind matters and was missing before -- OSM's
# highway=*/waterway=* tags are inherently LINEAR (a walking path or stream
# is a line, not a closed area), but the original version force-closed
# every feature into a "filled" polygon regardless. A closed near-zero-area
# line fills to basically nothing -- confirmed live: exactly why pathways
# and waterway-tagged water features weren't visibly rendering. Fixing this
# by switching to `stroke` instead of `fill` would look right in a browser
# but silently break the app's own pipeline: ingest_diagram_svg.py's
# _has_real_fill()/_group_polygons() require `fill != none` to recognize a
# shape as real geometry at all, so a stroke-only line would just vanish
# from the actual generated 3D design's masks, not merely look wrong when
# previewed. Instead, "line" kind features get shapely-buffered into a
# thin filled ribbon polygon (real width, real area) before ever becoming
# an SVG path -- visible AND functionally real fill, one mechanism, no
# special-casing needed downstream. width_m is the buffer's real-world
# width (a real pedestrian path/street/stream, not the diagram world).
TAG_RULES = [
    (("leisure", r"^(park|garden)$"), "GREEN_SPACE", "area", None),
    (("landuse", r"^(grass|meadow|forest)$"), "GREEN_SPACE", "area", None),
    (("natural", r"^wood$"), "GREEN_SPACE", "area", None),
    (("natural", r"^water$"), "WATER_FEATURES", "area", None),
    (("waterway", r".*"), "WATER_FEATURES", "line", 3.0),
    (("highway", r"^(footway|path|pedestrian|cycleway)$"), "PEDESTRIAN_PATH", "line", 2.5),
    (("landuse", r"^paved$"), "HARDSCAPE", "area", None),
    (("amenity", r"^plaza$"), "HARDSCAPE", "area", None),
    (("place", r"^square$"), "HARDSCAPE", "area", None),
    (("amenity", r"^parking$"), "PARKING", "area", None),
    (("amenity", r"^theatre$"), "AMPHITHEATRE", "area", None),
    (("leisure", r"^amphitheatre$"), "AMPHITHEATRE", "area", None),
    (("highway", r"^(primary|secondary|tertiary|residential)$"), "STREET", "line", 8.0),
]

CATEGORY_COLORS = {
    "GREEN_SPACE": "#4CAF50", "WATER_FEATURES": "#03A9F4", "PEDESTRIAN_PATH": "#9E9E9E",
    "HARDSCAPE": "#B0B0B0", "PARKING": "#757575", "AMPHITHEATRE": "#9C27B0", "STREET": "#616161",
}


def safe_site_name(park_name):
    words = re.findall(r"[A-Za-z0-9]+", park_name)
    return "".join(w.capitalize() for w in words) or "UnknownPark"


def _existing_precedent_names(target_dir=None):
    """lowercase safe-name (no extension) -> actual on-disk filename (no
    extension), for case-insensitive collision/cache checks -- Windows
    filesystems are case-insensitive (confirmed live: an earlier version of
    this script clobbered an existing precedent that differed only by
    capitalization), so every lookup against a precedent directory must go
    through this, never a bare case-sensitive comparison."""
    target_dir = target_dir or PRECEDENT_DIR
    if not os.path.isdir(target_dir):
        return {}
    return {f[:-4].lower(): f[:-4] for f in os.listdir(target_dir) if f.lower().endswith(".svg")}


def geocode(city, park_name, lat=None, lon=None):
    query = f"{park_name}, {city}" if city else park_name
    params = {"q": query, "format": "json", "limit": 1, "polygon_geojson": 1}
    if lat is not None and lon is not None:
        # Bias (not restrict) toward already-known coordinates -- e.g. the
        # AI path already has a lat/lon guess from the LLM. A generous ~1
        # degree box disambiguates a same-named park in multiple cities
        # without risking zero results if the LLM's coords are a bit off.
        d = 0.5
        params["viewbox"] = f"{lon - d},{lat + d},{lon + d},{lat - d}"
        params["bounded"] = 0
    resp = requests.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    results = resp.json()
    if not results:
        return None
    r = results[0]
    result_lat, result_lon = float(r["lat"]), float(r["lon"])
    bbox = r.get("boundingbox")  # [south, north, west, east] as strings
    return {"lat": result_lat, "lon": result_lon, "bbox": [float(x) for x in bbox] if bbox else None,
            "boundary_geojson": r.get("geojson"), "display_name": r.get("display_name", query)}


def _padded_bbox(geo):
    lat, lon = geo["lat"], geo["lon"]
    if geo["bbox"]:
        south, north, west, east = geo["bbox"]
    else:
        # No bbox from Nominatim (point-only result) -- synthesize a small
        # default footprint around the point instead of failing outright.
        d = 200.0 / METERS_PER_DEG
        south, north, west, east = lat - d, lat + d, lon - d, lon + d
    pad_deg_lat = CONTEXT_PAD_M / METERS_PER_DEG
    pad_deg_lon = CONTEXT_PAD_M / (METERS_PER_DEG * math.cos(math.radians(lat)) or 1e-9)
    return south - pad_deg_lat, north + pad_deg_lat, west - pad_deg_lon, east + pad_deg_lon


OVERPASS_SERVER_TIMEOUT_S = 60
OVERPASS_CLIENT_TIMEOUT_S = 90
OVERPASS_MAX_ATTEMPTS = 2


def query_overpass(bbox):
    """Querying both way[] and relation[] clauses for every tag rule
    roughly doubles server-side query cost versus ways alone -- combined
    with a large, padded-context bbox (e.g. a big famous park like Golden
    Gate Park), this can genuinely exceed a short timeout on the free
    public Overpass instance (confirmed live: a 30s server-side / 45s
    client-side budget 504'd twice in a row on exactly that case). One
    retry with a longer budget the second time absorbs ordinary
    server-load variance; a caller still sees a clean RequestException (via
    fetch_and_write_precedent's own try/except) if both attempts fail."""
    south, north, west, east = bbox
    way_clauses = "\n  ".join(f'way["{key}"~"{pattern}"];' for (key, pattern), *_rest in TAG_RULES)
    rel_clauses = "\n  ".join(
        f'relation["{key}"~"{pattern}"]["type"="multipolygon"];' for (key, pattern), *_rest in TAG_RULES
    )
    query = f"""
[out:json][timeout:{OVERPASS_SERVER_TIMEOUT_S}][bbox:{south},{west},{north},{east}];
(
  {way_clauses}
  {rel_clauses}
);
out geom;
""".strip()

    last_error = None
    for attempt in range(1, OVERPASS_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query},
                                  headers={"User-Agent": USER_AGENT}, timeout=OVERPASS_CLIENT_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except requests.RequestException as e:
            last_error = e
            _log(f"[fetch_park_precedent] Overpass attempt {attempt}/{OVERPASS_MAX_ATTEMPTS} failed: {e}")
    raise last_error


def classify(tags):
    """Returns (category, geom_kind, width_m) for the first matching rule,
    or None if nothing matches. See TAG_RULES' own comment for why
    geom_kind/width_m exist."""
    for (key, pattern), category, geom_kind, width_m in TAG_RULES:
        value = tags.get(key)
        if value and re.match(pattern, value):
            return category, geom_kind, width_m
    return None


def project(lat, lon, center_lat, center_lon):
    """Local tangent-plane projection (meters), then scaled to pixels.
    Accurate enough at park scale -- no need for a real UTM projection.
    Negative-y-for-north so north reads "up" in the written SVG."""
    x_m = (lon - center_lon) * METERS_PER_DEG * math.cos(math.radians(center_lat))
    y_m = (lat - center_lat) * METERS_PER_DEG
    return x_m * PX_PER_METER, -y_m * PX_PER_METER


def _stitch_rings(segments):
    """Greedy assembly of way-member line segments (each a list of (lat,
    lon) tuples) into closed rings, for OSM multipolygon relations whose
    outer/inner boundary is split across several way members that share
    endpoints. Real-world data is rarely perfectly clean -- this is a
    best-effort stitcher (matches endpoints within RING_STITCH_TOLERANCE_DEG,
    force-closes anything left over rather than dropping it), not a
    topologically rigorous assembler; good enough for a coarse design-tool
    precedent, not surveying-grade. Returns a list of closed point-loops."""
    remaining = [list(seg) for seg in segments if len(seg) >= 2]
    rings = []

    def close_enough(a, b):
        return abs(a[0] - b[0]) < RING_STITCH_TOLERANCE_DEG and abs(a[1] - b[1]) < RING_STITCH_TOLERANCE_DEG

    while remaining:
        chain = remaining.pop(0)
        extended = True
        while extended and not close_enough(chain[0], chain[-1]):
            extended = False
            for i, seg in enumerate(remaining):
                if close_enough(chain[-1], seg[0]):
                    chain.extend(seg[1:])
                elif close_enough(chain[-1], seg[-1]):
                    chain.extend(list(reversed(seg))[1:])
                elif close_enough(chain[0], seg[-1]):
                    chain = seg[:-1] + chain
                elif close_enough(chain[0], seg[0]):
                    chain = list(reversed(seg))[:-1] + chain
                else:
                    continue
                remaining.pop(i)
                extended = True
                break
        if not close_enough(chain[0], chain[-1]):
            chain.append(chain[0])  # force-close leftover fragments rather than dropping them
        rings.append(chain)
    return rings


def _relation_polygons(element, project_fn):
    """Reconstructs closed pixel-space rings from one Overpass relation
    element's "outer"-role members (each a way's lat/lon geometry). A
    relation can have multiple disjoint outer rings (e.g. a park split by a
    road) -- each becomes its own ring/polygon.

    2026-08-14: "inner" (hole) rings are deliberately NOT subtracted, even
    though shapely can build a real Polygon-with-holes -- confirmed live
    that this pipeline's actual SVG consumer (ingest_diagram_svg.py's
    _extract_vertices()) has no concept of multi-subpath/hole paths at all:
    it flattens every number in a path's `d` string into one flat
    coordinate list regardless of M/Z command boundaries, so an
    exterior+hole path emitted as one compound path would parse into a
    single corrupted, self-crossing polygon (confirmed: produced ~42
    million unit coordinates from a real park's water body during testing
    -- a second, independent bug in the original attempt, since fixed:
    projecting lat/lon to pixels BEFORE building shapely geometry, rather
    than passing bare (lat, lon) tuples through shapely and unpacking them
    positionally afterward, which is what actually produced that specific
    blowup). In practice this pipeline's own overlapping-layers convention
    (see rasterize_precedent_layers()'s own docstring: "a cell CAN be True
    in multiple roles if their layers overlap") already covers most
    real-world "hole" cases anyway -- a plaza carved out of a lawn is
    normally ALSO its own separately-tagged OSM feature, which resolves to
    its own HARDSCAPE polygon layered on top, not a true geometric
    subtraction. What ring-stitching (_stitch_rings) still buys regardless
    of holes: many relations' outer boundary is split across several way
    segments that only join up when reassembled -- something a plain `way`
    query can't do at all.

    project_fn maps (lat, lon) -> (x, y) pixel coords -- applied to every
    point BEFORE shapely ever sees it, so there's no positional (lat, lon)
    vs (lon, lat) tuple to mix up later.
    """
    outer_segs = [[project_fn(m["lat"], m["lon"]) for m in mem["geometry"]]
                  for mem in element.get("members", []) if mem.get("role") == "outer" and mem.get("geometry")]
    outer_rings = _stitch_rings(outer_segs)

    polygons = []
    for ring in outer_rings:
        if len(ring) < 4:
            continue
        try:
            poly = make_valid(Polygon(ring))
        except Exception:
            continue
        if poly.geom_type == "Polygon" and not poly.is_empty:
            polygons.append(poly)
        elif poly.geom_type == "MultiPolygon":
            polygons.extend(g for g in poly.geoms if not g.is_empty)
    return polygons


def _shapely_exterior_to_svg_d(polygon):
    """Renders a shapely Polygon's EXTERIOR ring only (see
    _relation_polygons' docstring for why holes are dropped) as one simple
    SVG path `d` string -- same single-ring convention _path_d() already
    uses for plain `way` features. Coordinates are already pixel-space
    (projected before the Polygon was built), so this is pure formatting,
    no further transform."""
    pts = list(polygon.exterior.coords)
    return f"M{pts[0][0]:.2f},{pts[0][1]:.2f} " + " ".join(f"L{x:.2f},{y:.2f}" for x, y in pts[1:]) + " Z"


def _path_d(points):
    if not points:
        return None
    d = f"M{points[0][0]:.2f},{points[0][1]:.2f} " + " ".join(
        f"L{x:.2f},{y:.2f}" for x, y in points[1:]
    )
    return d + " Z"


def _buffer_line_to_svg_d(points, width_m):
    """Converts a LINEAR feature (a walking path, street, or stream -- an
    OSM way with no meaningful enclosed area) into a thin FILLED ribbon
    polygon of its real-world width, rather than naively closing the raw
    point sequence into a degenerate near-zero-area shape. See TAG_RULES'
    own comment for why this (not a stroke) is the fix: the app's own
    _has_real_fill()/_group_polygons() require real fill area to recognize
    a shape at all, so this needs to stay fill-based to actually show up
    in the generated 3D design, not just look right in a raw SVG preview.
    Returns None if the line is too short/degenerate to buffer."""
    if len(points) < 2:
        return None
    try:
        line = LineString(points)
        if line.length < 1e-6:
            return None
        buffered = line.buffer(width_m * PX_PER_METER / 2, cap_style="round")
        buffered = make_valid(buffered)
    except Exception:
        return None
    if buffered.is_empty:
        return None
    if buffered.geom_type == "MultiPolygon":
        buffered = max(buffered.geoms, key=lambda g: g.area)
    if buffered.geom_type != "Polygon":
        return None
    return _shapely_exterior_to_svg_d(buffered)


def build_svg(geo, elements):
    center_lat, center_lon = geo["lat"], geo["lon"]

    def proj(lat, lon):
        return project(lat, lon, center_lat, center_lon)

    by_category = {}  # category -> list of d_strings (all pixel-space, unshifted)
    for el in elements:
        tags = el.get("tags") or {}
        classified = classify(tags)
        if classified is None:
            continue
        category, geom_kind, width_m = classified

        if el.get("type") == "relation":
            # Relations are always area-type in practice (multipolygon
            # relations exist specifically to represent complex closed
            # areas) -- no line-buffering needed here.
            for poly in _relation_polygons(el, proj):
                d = _shapely_exterior_to_svg_d(poly)
                by_category.setdefault(category, []).append(d)
        else:
            geom = el.get("geometry")
            if not geom or len(geom) < 2:
                continue
            points = [proj(pt["lat"], pt["lon"]) for pt in geom]
            d = _buffer_line_to_svg_d(points, width_m) if geom_kind == "line" else _path_d(points)
            if d:
                by_category.setdefault(category, []).append(d)

    south, north, west, east = _padded_bbox(geo)
    corners = [(west, south), (east, south), (east, north), (west, north)]
    boundary_points = [proj(lat, lon) for lon, lat in corners]
    if geo["boundary_geojson"] and geo["boundary_geojson"].get("type") in ("Polygon", "MultiPolygon"):
        coords = geo["boundary_geojson"]["coordinates"]
        ring = coords[0] if geo["boundary_geojson"]["type"] == "Polygon" else coords[0][0]
        boundary_points = [proj(lat, lon) for lon, lat in ring]

    all_x, all_y = [], []
    for pts in by_category.values():
        for d in pts:
            for match in re.finditer(r"([\d.\-]+),([\d.\-]+)", d):
                all_x.append(float(match.group(1)))
                all_y.append(float(match.group(2)))
    all_x += [x for x, _y in boundary_points]
    all_y += [y for _x, y in boundary_points]
    margin = 40
    min_x, max_x = min(all_x) - margin, max(all_x) + margin
    min_y, max_y = min(all_y) - margin, max(all_y) + margin
    width, height = max_x - min_x, max_y - min_y

    def shift_d(d):
        return re.sub(
            r"([\d.\-]+),([\d.\-]+)",
            lambda m: f"{float(m.group(1)) - min_x:.2f},{float(m.group(2)) - min_y:.2f}",
            d,
        )

    # `viewBox` stays at the real content scale (needed for correct
    # proportions -- nothing in this app's own parsing, e.g.
    # ingest_diagram_svg.py's _extract_vertices/_boundary_bbox_center_and_size,
    # reads `width`/`height`/`viewBox` at all; they operate purely on raw
    # path coordinate numbers). `width`/`height` are a separate DISPLAY
    # size, capped here so a large real park (e.g. Golden Gate Park, several
    # thousand pt across at this module's PX_PER_METER scale) still opens
    # at a sane size directly in a browser instead of rendering at its
    # literal real-world-scaled pixel dimensions.
    display_scale = min(1.0, MAX_DISPLAY_DIM / max(width, height))
    svg = ET.Element("svg", {
        "version": "1.1", "xmlns": "http://www.w3.org/2000/svg",
        "width": f"{width * display_scale:.0f}pt", "height": f"{height * display_scale:.0f}pt",
        "viewBox": f"0 0 {width:.0f} {height:.0f}",
    })
    ET.SubElement(svg, "defs")

    boundary_g = ET.SubElement(svg, "g", {"id": "BOUNDARY"})
    boundary_d = _path_d([(x - min_x, y - min_y) for x, y in boundary_points])
    ET.SubElement(boundary_g, "path", {"d": boundary_d, "fill": "none", "stroke": "#ffffff", "stroke-width": "1"})

    for category, d_list in by_category.items():
        g = ET.SubElement(svg, "g", {"id": category})
        color = CATEGORY_COLORS.get(category, "#999999")
        for d in d_list:
            ET.SubElement(g, "path", {"d": shift_d(d), "fill": color})

    attractor_g = ET.SubElement(svg, "g", {"id": "MAJOR_ATTRACTORS"})
    cx, cy = proj(center_lat, center_lon)
    cx, cy = cx - min_x, cy - min_y
    ET.SubElement(attractor_g, "circle", {"cx": f"{cx:.2f}", "cy": f"{cy:.2f}", "r": "15", "fill": "#FF9800"})

    return svg


def fetch_and_write_precedent(city, park_name, lat=None, lon=None, force=False, out_dir=None):
    """The real entry point -- callable from other code (see
    logic/ai_synthesizer.py's generate_spatial_seed(), which calls this
    automatically when the AI names a real-world park outside the existing
    precedent set). Returns the canonical site name on success, None for
    any ordinary "couldn't do it" outcome (ambiguous/ignore-able, not
    raised) -- geocode failure, zero usable OSM features. Callers should
    treat None as "fall back to an existing precedent," not a crash.

    Caches by name: if a precedent already exists (case-insensitively) for
    this park's safe name, returns it immediately without any network
    calls, unless force=True.

    out_dir (default None -> PRECEDENT_DIR, the live app's precedent
    folder): write here instead -- e.g. a scratch comparison folder when
    fetching an OSM-derived version of a park that ALREADY has a
    hand-built precedent, so the two can sit side by side without the
    collision guard below refusing to write (or force=True clobbering the
    hand-built original, which this is specifically for avoiding).
    """
    target_dir = out_dir or PRECEDENT_DIR
    out_name = safe_site_name(park_name)
    existing = _existing_precedent_names(target_dir)
    if not force and out_name.lower() in existing:
        real_name = existing[out_name.lower()]
        _log(f"[fetch_park_precedent] {real_name!r} already cached in {target_dir} -- skipping fetch.")
        return real_name

    _log(f"[fetch_park_precedent] Geocoding {park_name!r} in {city!r}...")
    try:
        geo = geocode(city, park_name, lat=lat, lon=lon)
    except requests.RequestException as e:
        _log(f"[fetch_park_precedent] Geocoding request failed: {e}")
        return None
    if geo is None:
        _log(f"[fetch_park_precedent] Nominatim found nothing for {park_name!r} in {city!r}.")
        return None
    _log(f"[fetch_park_precedent]   -> {geo['display_name']} @ ({geo['lat']:.5f}, {geo['lon']:.5f})")

    bbox = _padded_bbox(geo)
    try:
        elements = query_overpass(bbox)
    except requests.RequestException as e:
        _log(f"[fetch_park_precedent] Overpass request failed: {e}")
        return None
    _log(f"[fetch_park_precedent]   -> {len(elements)} raw elements returned")

    svg_root = build_svg(geo, elements)
    category_counts = {
        g.get("id"): len(list(g)) for g in svg_root if g.tag == "g" and g.get("id") != "BOUNDARY"
    }
    _log(f"[fetch_park_precedent]   -> category coverage: {category_counts}")
    if not any(category_counts.values()):
        _log(f"[fetch_park_precedent] No recognized features found for {park_name!r} -- OSM coverage too sparse.")
        return None

    # Re-check for a collision right before writing (cheap, and a second
    # process could plausibly have written the same name in between) --
    # never overwrite silently, case-insensitively, matching Windows'
    # actual filesystem behavior (see this module's own docstring).
    existing = _existing_precedent_names(target_dir)
    if not force and out_name.lower() in existing:
        return existing[out_name.lower()]

    os.makedirs(target_dir, exist_ok=True)
    out_path = os.path.join(target_dir, f"{out_name}.svg")
    ET.ElementTree(svg_root).write(out_path, encoding="utf-8", xml_declaration=True)
    _log(f"[fetch_park_precedent] Written: {out_path}")
    return out_name


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    city, park_name = sys.argv[1], sys.argv[2]
    force = "--force" in sys.argv[3:]

    result = fetch_and_write_precedent(city, park_name, force=force)
    if result is None:
        _log(f"\nFAILED: could not produce a precedent for {park_name!r} in {city!r}.")
        sys.exit(1)
    _log(f"\nSite name for remix_layers()/extract_prompt_hints(): {result!r}")


if __name__ == "__main__":
    main()
