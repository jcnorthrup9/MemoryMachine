"""
Memory Machine System 9.1 -- Urban Interference Solver (Pershing Square Mutation).

Maps a 30x30 analytical grid over the Pershing Square surface / 1951 parking
garage, scores each cell against memory-volatility and asset-pressure layers,
and flags safe excavation ("Puncture_Zone") candidates for Rhino/Grasshopper.
"""
import os
import csv
import json
import math
import hashlib
import numpy as np

from structural_grid_analyzer import load_structural_grid_from_svg, load_garage_depth_from_svg

# ---------------------------------------------------------------------------
# Step 1: File & folder schema
# ---------------------------------------------------------------------------
BASE_DIR = r"D:\MemoryMachine"
DATA_DIR = os.path.join(BASE_DIR, "data")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")


def init_directory_schema():
    for d in (DATA_DIR, ARCHIVE_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)
    return DATA_DIR, ARCHIVE_DIR, OUTPUT_DIR


def _load_or_seed_json(path, seed_factory, label):
    """Read a data file if present; otherwise scaffold a starter version on disk."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    seed = seed_factory()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(seed, f, indent=2)
    print(f"[SEED] {label} not found -- wrote starter file to {path}")
    return seed


# ---------------------------------------------------------------------------
# Site constants
# Grid resolution is 30x30 analytical cells across the Pershing Square surface.
# Real site extents and the 1951 garage column grid are read directly from the
# Rhino plan-view export below; FALLBACK_SITE_BOUNDS_FT only applies if that
# file is missing (see logic/intervention_engine.py for the prior estimate).
# ---------------------------------------------------------------------------
GRID_SIZE = 30
FALLBACK_SITE_BOUNDS_FT = (330.0, 550.0)

SVG_PLAN_PATH = os.path.join(DATA_DIR, "PershingMetabolizer", "parkSVG", "pershingRhinoPlanView.svg")
SVG_LONG_ELEVATION_PATH = os.path.join(DATA_DIR, "PershingMetabolizer", "parkSVG", "pershingRhinoLongElevation.svg")
SVG_SHORT_ELEVATION_PATH = os.path.join(DATA_DIR, "PershingMetabolizer", "parkSVG", "pershingRhinoShortElevation.svg")
# Real on-center column spacing, confirmed by the user against the original drawing.
COLUMN_SPACING_FT = 27.0
# Used only if the elevation SVGs can't be read: a typical single-level parking-structure clear height.
FALLBACK_GARAGE_DEPTH_FT = 12.0

# Grid orientation (confirmed against the Rhino Top view used to export the SVGs):
#   x: 0 = west (Olive St)  -> 29 = east (Hill St)
#   y: 0 = south (6th St)   -> 29 = north (5th St)
# Bridged from data/pershing_site_context.json: transit_pavilion position,
# normalized against plaza_slab extents and mapped onto the 30x30 grid
# (z normalizes north=0/south=1 in that file, so y is inverted here to match
# the south=0/north=29 convention above).
METRO_NODE_CELL = (3, 12)

COLUMN_CLEARANCE_FT = 5.0 # A 5ft no-puncture zone around each column center.
RAMP_VOID_CLEARANCE_FT = 15.0  # Spiral ramps occupy more footprint than a single column.
NEAR_METRO_RADIUS_CELLS = 6
INTERVENTION_THRESHOLD = 0.30  # was 0.75 (placeholder-era calibration).
# Real-data max composite score is ~0.43 (p99 ~0.336) once real columns, real
# building heights, and real amenity deficits are wired in -- 0.75 never fires.
# Lowered so the top tier of real cells (near-metro, low-enclosure,
# amenity-deficit) actually qualifies as a puncture candidate.
MEMORY_WEIGHT = 0.4
ASSET_WEIGHT = 0.6
ASSET_SUBWEIGHTS = {"enclosure": 0.3, "transit": 0.3, "amenity": 0.4}


# ---------------------------------------------------------------------------
# Step 2: Core pipeline class
# ---------------------------------------------------------------------------
class MemoryMachineEngine:
    def __init__(self, grid_size=GRID_SIZE, data_dir=DATA_DIR, archive_dir=ARCHIVE_DIR, output_dir=OUTPUT_DIR):
        self.grid_size = grid_size
        self.data_dir = data_dir
        self.archive_dir = archive_dir
        self.output_dir = output_dir

        self.xs, self.ys = np.indices((grid_size, grid_size))
        self.cell_size_ft, self.garage_columns, self.ramp_voids = self._init_structural_grid()
        self.garage_depth_ft = self._init_garage_depth()

        self.building_heights = self._ingest_building_heights()
        self.transit_flux = self._ingest_transit_flux()
        self.amenity_deficits = self._ingest_amenity_deficits()
        self.memory_overlay = self._ingest_memory_overlay()

        self._last_scores = None

    # -- structural grid -----------------------------------------------------
    def _init_structural_grid(self):
        try:
            structural = load_structural_grid_from_svg(SVG_PLAN_PATH, COLUMN_SPACING_FT)
            print(f"[BRIDGE] Loaded {len(structural['columns_ft'])} real garage columns from {SVG_PLAN_PATH}")
            site_w, site_h = structural["site_width_ft"], structural["site_height_ft"]
            cell_size_ft = (site_w / self.grid_size, site_h / self.grid_size)
            garage_columns = [(x_ft / cell_size_ft[0], y_ft / cell_size_ft[1])
                              for x_ft, y_ft in structural["columns_ft"]]
            # Grid intersections with no real column -- per the user, these are
            # where the spiral parking ramps sit (built into the structure either
            # way), so treat them as excavation-exclusion points too.
            ramp_voids = [(x_ft / cell_size_ft[0], y_ft / cell_size_ft[1])
                          for x_ft, y_ft in structural["gaps_ft"]]
            print(f"[BRIDGE] {len(ramp_voids)} column-grid gaps flagged as ramp-void exclusion zones")
            return cell_size_ft, garage_columns, ramp_voids
        except (FileNotFoundError, IndexError, ValueError) as e:
            print(f"[WARN] Could not load real structural grid from SVG ({e}) -- "
                  f"falling back to {FALLBACK_SITE_BOUNDS_FT} bounds with no column data.")
            cell_size_ft = (FALLBACK_SITE_BOUNDS_FT[0] / self.grid_size, FALLBACK_SITE_BOUNDS_FT[1] / self.grid_size)
            return cell_size_ft, [], []

    def _init_garage_depth(self):
        try:
            return load_garage_depth_from_svg([SVG_LONG_ELEVATION_PATH, SVG_SHORT_ELEVATION_PATH], COLUMN_SPACING_FT)
        except (FileNotFoundError, IndexError, ValueError) as e:
            print(f"[WARN] Could not derive garage depth from elevation SVGs ({e}) -- "
                  f"falling back to {FALLBACK_GARAGE_DEPTH_FT} ft.")
            return FALLBACK_GARAGE_DEPTH_FT

    def _distance_to_nearest_column(self, x, y):
        if not self.garage_columns:
            return float("inf")
        return min(math.hypot(x - cx, y - cy) for cx, cy in self.garage_columns)

    def _distance_to_nearest_ramp_void(self, x, y):
        if not self.ramp_voids:
            return float("inf")
        return min(math.hypot(x - vx, y - vy) for vx, vy in self.ramp_voids)

    # -- ingest: asset-pressure layers ---------------------------------------
    def _ingest_building_heights(self):
        path = os.path.join(self.data_dir, "building_heights.json")

        def seed():
            return {
                "_meta": ("campanile_tower bridged from data/pershing_site_context.json. Perimeter "
                          "buildings transcribed by the user from Rhino/Google Maps measurements in "
                          "data/PershingMetabolizer/BuildingHeights.txt (real heights, real addresses). "
                          "Left-right position along each street frontage is approximated from DTLA "
                          "address-number ordering (lower number = closer to the Spring/Main baseline), "
                          "not precisely geocoded -- refine later from the OSM footprints in "
                          "PershingContext.svg if exact placement matters. Future Solutions Media (365.5ft) "
                          "was flagged by the user as possibly inaccurate -- double check before trusting "
                          "this layer for real design decisions. Biltmore Hotel corrected to 170ft (the "
                          "52ft source measurement was a mismeasured wing/parapet, not the main tower)."),
                "buildings": [
                    {"label": "campanile_tower", "x": 15, "y": 14, "height_ft": 24.0},
                    # North frontage (5th St) -- ordered east(Hill)->west(Olive) by ascending address number
                    {"label": "Cosmo Smoke Shop (312 W 5th St)", "x": 24, "y": 28, "height_ft": 184.54},
                    {"label": "Title Guarantee Building Apartments (411 W 5th St)", "x": 15, "y": 28, "height_ft": 226.02},
                    {"label": "Park Fifth Tower (427 W 5th St)", "x": 6, "y": 28, "height_ft": 249.31},
                    # South frontage (6th St) -- ordered east->west by ascending address number
                    {"label": "Foreign Currency Exchange (406 W 6th St)", "x": 24, "y": 1, "height_ft": 121.19},
                    {"label": "The Heron Building (510 W 6th St)", "x": 15, "y": 1, "height_ft": 164.94},
                    {"label": "Future Solutions Media (800 W 6th St)", "x": 6, "y": 1, "height_ft": 365.5},
                    # West frontage (Olive St) -- ordered north->south by ascending address number
                    {"label": "Biltmore Hotel (501 S Olive St)", "x": 1, "y": 22, "height_ft": 170.0},
                    {"label": "Pitchoun! (545 S Olive St)", "x": 1, "y": 8, "height_ft": 62.33},
                    # East frontage (Hill St) -- ordered north->south by ascending address number
                    {"label": "Pershing Square Building (448 S Hill St)", "x": 28, "y": 22, "height_ft": 186.5},
                    {"label": "International Jewelry Plaza (550 S Hill St)", "x": 28, "y": 8, "height_ft": 224.40},
                ],
            }

        return _load_or_seed_json(path, seed, "building_heights.json").get("buildings", [])

    def _ingest_transit_flux(self):
        path = os.path.join(self.data_dir, "transit_flux.json")

        def seed():
            return {
                "_meta": "Auto-seeded. metro_node bridged from transit_pavilion in data/pershing_site_context.json.",
                "metro_node": {"x": METRO_NODE_CELL[0], "y": METRO_NODE_CELL[1]},
                "flux_decay": 0.15,
            }

        return _load_or_seed_json(path, seed, "transit_flux.json")

    def _ingest_amenity_deficits(self):
        path = os.path.join(self.data_dir, "amenity_deficits.json")

        def seed():
            return {
                "_meta": ("Auto-seeded placeholder -- no geocoded hospitality/amenity dataset "
                          "exists yet in /data. Replace with real survey data when available."),
                "points": [
                    {"x": 5, "y": 5, "hospitality_density": 0.6, "surface_amenity_density": 0.2},
                    {"x": 24, "y": 6, "hospitality_density": 0.7, "surface_amenity_density": 0.1},
                    {"x": 15, "y": 24, "hospitality_density": 0.3, "surface_amenity_density": 0.5},
                ],
            }

        return _load_or_seed_json(path, seed, "amenity_deficits.json").get("points", [])

    def _parse_amenities_from_markdown(self, md_path):
        """
        Parses a markdown table of amenities and geocodes them to the grid.
        This is the new, preferred method for ingesting amenity data.
        """
        if not os.path.exists(md_path):
            print(f"[WARN] Amenity markdown file not found at {md_path}. Using placeholder JSON.")
            return self._ingest_amenity_deficits()

        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        header_found = False
        raw_points = []
        for line in lines:
            if '|' not in line: continue
            if '---' in line:
                header_found = True
                continue
            if not header_found: continue

            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) < 3: continue
            
            name, category, location = parts[0], parts[1], parts[2]
            raw_points.append({"name": name, "category": category, "location": location.lower()})

        # Simple address-to-grid geocoding based on street names
        geocoded_points = {} # Use a dict to aggregate densities at the same point

        for point in raw_points:
            x, y = 15, 15 # Default to center
            loc = point['location']
            if 'olive' in loc: x = 1
            if 'hill' in loc: x = 28
            if '5th' in loc: y = 28
            if '6th' in loc: y = 1
            if 'grand' in loc:
                if '506' in loc: x, y = 10, 25 # Biltmore
                if '700' in loc: x, y = 8, 10 # Bottega
                if '788' in loc: x, y = 5, 5 # Whole Foods
            if 'broadway' in loc: x = 25 # Grand Central Market is further east

            key = (x, y)
            if key not in geocoded_points:
                geocoded_points[key] = {"x": x, "y": y, "hospitality_density": 0, "surface_amenity_density": 0}
            
            if point['category'] == 'hospitality':
                geocoded_points[key]['hospitality_density'] += 1
            elif point['category'] == 'surface_amenity':
                geocoded_points[key]['surface_amenity_density'] += 1

        # Normalize densities
        # (A more robust implementation would be needed for a real-world scenario)
        return list(geocoded_points.values())

    # -- ingest: memory overlay -----------------------------------------------
    def _hash_to_cell(self, name):
        h = hashlib.sha1(name.encode("utf-8")).hexdigest()
        return int(h[:8], 16) % self.grid_size, int(h[8:16], 16) % self.grid_size

    def _ingest_memory_overlay(self):
        primary = os.path.join(self.archive_dir, "memory_logs.json")
        if os.path.exists(primary):
            with open(primary, "r", encoding="utf-8") as f:
                entries = json.load(f)
            return [
                {"x": int(e.get("x", 0)), "y": int(e.get("y", 0)),
                 "volatility": float(e.get("volatility", 0.0)),
                 "source": e.get("source", "unknown")}
                for e in entries
            ]

        # Bridge fallback: last semester's qualitative archive already holds this data.
        legacy = os.path.join(self.data_dir, "memory_manifest.json")
        if not os.path.exists(legacy):
            print("[WARN] No memory archive found -- proceeding with zero volatility overlay.")
            return []

        print(f"[BRIDGE] archive/memory_logs.json not found -- bridging qualitative weights from {legacy}")
        with open(legacy, "r", encoding="utf-8") as f:
            legacy_entries = json.load(f)

        bridged = []
        for e in legacy_entries:
            name = e.get("name", "unknown")
            sentiment = float(e.get("sentiment_score", 0.5))
            volatility = max(0.0, min(1.0, 1.0 - sentiment))  # low sentiment -> contested/volatile memory
            gx, gy = self._hash_to_cell(name)
            bridged.append({"x": gx, "y": gy, "volatility": volatility, "source": name})

        with open(primary, "w", encoding="utf-8") as f:
            json.dump(bridged, f, indent=2)
        return bridged

    # -- scoring layers --------------------------------------------------------
    @staticmethod
    def _normalize(grid):
        lo, hi = grid.min(), grid.max()
        if hi - lo < 1e-9:
            return np.zeros_like(grid)
        return (grid - lo) / (hi - lo)

    def _compute_enclosure_grid(self):
        grid = np.zeros((self.grid_size, self.grid_size))
        for b in self.building_heights:
            dist = np.hypot(self.xs - b["x"], self.ys - b["y"]) + 1.0
            grid += b["height_ft"] / dist
        return self._normalize(grid)

    def _compute_transit_grid(self):
        node = self.transit_flux.get("metro_node", {"x": 0, "y": 0})
        decay = float(self.transit_flux.get("flux_decay", 0.15))
        dist = np.hypot(self.xs - node["x"], self.ys - node["y"])
        return self._normalize(np.exp(-decay * dist))

    def _compute_amenity_grid(self):
        grid = np.zeros((self.grid_size, self.grid_size))
        for p in self.amenity_deficits:
            deficit = float(p.get("hospitality_density", 0)) - float(p.get("surface_amenity_density", 0))
            dist = np.hypot(self.xs - p["x"], self.ys - p["y"]) + 1.0
            grid += deficit / dist
        return self._normalize(np.clip(grid, 0, None))

    def _compute_memory_grid(self):
        grid = np.zeros((self.grid_size, self.grid_size))
        for m in self.memory_overlay:
            x, y = m["x"], m["y"]
            if 0 <= x < self.grid_size and 0 <= y < self.grid_size:
                grid[x, y] += m["volatility"]
        # 3x3 box-blur: a memory's volatility bleeds into the cells around it.
        padded = np.pad(grid, 1, mode="edge")
        blurred = sum(
            padded[1 + dx: 1 + dx + self.grid_size, 1 + dy: 1 + dy + self.grid_size]
            for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        ) / 9.0
        return self._normalize(blurred)

    # ---------------------------------------------------------------------
    # Step 3: Matrix interference loop + excavation solver
    # ---------------------------------------------------------------------
    def run_interference_loop(self):
        enclosure = self._compute_enclosure_grid()
        transit = self._compute_transit_grid()
        amenity = self._compute_amenity_grid()
        memory = self._compute_memory_grid()

        w = ASSET_SUBWEIGHTS
        asset_pressure = enclosure * w["enclosure"] + transit * w["transit"] + amenity * w["amenity"]
        intervention_score = memory * MEMORY_WEIGHT + asset_pressure * ASSET_WEIGHT

        self._last_scores = {"intervention": intervention_score, "memory": memory, "asset_pressure": asset_pressure}
        return intervention_score

    def solve_punctures(self, threshold=INTERVENTION_THRESHOLD):
        scores = self.run_interference_loop()
        memory = self._last_scores["memory"]
        asset_pressure = self._last_scores["asset_pressure"]
        cell_w, cell_d = self.cell_size_ft

        punctures = []
        for x in range(self.grid_size):
            for y in range(self.grid_size):
                is_on_column = self._distance_to_nearest_column(x, y) * cell_w < COLUMN_CLEARANCE_FT
                is_on_ramp_void = self._distance_to_nearest_ramp_void(x, y) * cell_w < RAMP_VOID_CLEARANCE_FT

                # Rule 4: Handle structural column cells and spiral-ramp voids
                if is_on_column or is_on_ramp_void:
                    # This cell sits on a column or ramp structure. Instead of puncturing,
                    # we could flag it for a "Structural_Column_Jacket" intervention if the
                    # score is high. For now, we will just prevent a full puncture.
                    continue

                score = float(scores[x, y])
                if score <= threshold:
                    continue
                
                near_metro = math.hypot(x - METRO_NODE_CELL[0], y - METRO_NODE_CELL[1]) <= NEAR_METRO_RADIUS_CELLS
                puncture_type = "Transit_Daylight_Canyon" if near_metro else "Infrastructural_Light_Scoop"

                punctures.append({
                    "coordinates": (x, y),
                    "puncture_type": puncture_type,
                    "bounds": {
                        "width_ft": round(cell_w, 2),
                        "length_ft": round(cell_d, 2),
                        "footprint_sqft": round(cell_w * cell_d, 2),
                        "excavation_depth_ft": round(self.garage_depth_ft, 2),
                        "volume_cuft": round(cell_w * cell_d * self.garage_depth_ft, 2),
                    },
                    "intervention_score": round(score, 4),
                    "memory_volatility": round(float(memory[x, y]), 4),
                    "asset_pressure_deficit": round(float(asset_pressure[x, y]), 4),
                })
        return punctures

    # ---------------------------------------------------------------------
    # Step 4: Auto-exporter
    # ---------------------------------------------------------------------
    def export_csv(self, punctures, filename="midterm_punctures.csv"):
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "x", "y", "puncture_type", "bounds_width_ft", "bounds_length_ft", "bounds_footprint_sqft",
                "bounds_excavation_depth_ft", "bounds_volume_cuft",
                "intervention_score", "memory_volatility", "asset_pressure_deficit",
            ])
            for p in punctures:
                x, y = p["coordinates"]
                b = p["bounds"]
                writer.writerow([
                    x, y, p["puncture_type"], b["width_ft"], b["length_ft"], b["footprint_sqft"],
                    b["excavation_depth_ft"], b["volume_cuft"],
                    p["intervention_score"], p["memory_volatility"], p["asset_pressure_deficit"],
                ])
        print(f"[EXPORT] Wrote {len(punctures)} puncture zones to {path}")
        return path


def main():
    init_directory_schema()
    engine = MemoryMachineEngine()
    
    # Use the new markdown parser instead of the old placeholder
    amenity_md_path = os.path.join(engine.data_dir, "PershingMetabolizer", "notes", "pershing_amenities_raw.md")
    engine.amenity_deficits = engine._parse_amenities_from_markdown(amenity_md_path)
    
    punctures = engine.solve_punctures()
    engine.export_csv(punctures)
    print(f"Found {len(punctures)} Puncture_Zone candidates above threshold {INTERVENTION_THRESHOLD}.")


if __name__ == "__main__":
    main()
