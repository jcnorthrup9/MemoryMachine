"""
Memory Machine -- Foot-Traffic Data Ingestion.

Replaces terracing_engine.py's DEFAULT_FOOT_TRAFFIC_HOTSPOTS (a 2-point
diagrammatic placeholder) with real foot-traffic data -- pedestrian counts,
mobility-data station exports, curated observation points, etc. dropped into
a data folder, not scraped live. Same shape/contract as amenity_deficit.py's
CSV loader (that project decision applies equally well here: no live scrape,
a human curates real data into this frac-based CSV format).

CSV contract (columns, case-insensitive, extra columns ignored):
  x_frac, y_frac   -- required. Normalized site position, 0..1 each, same
                       convention as DEFAULT_FOOT_TRAFFIC_HOTSPOTS: x_frac
                       along the site's width axis, y_frac along its length
                       axis.
  strength         -- required. 0..1, how strongly this point indicates
                       foot traffic (e.g. a normalized pedestrian count).
  radius_ft        -- optional, defaults to DEFAULT_RADIUS_FT. How far this
                       point's influence extends -- a per-project tuning
                       constant, left as a column mainly so it CAN be
                       overridden per row if curating multiple data sources
                       together.

No aggregation/clustering is done here -- every row becomes its own hotspot.
Multiple nearby weak points naturally combine into a stronger influence via
terracing_engine.py's existing additive foot_traffic_influence sum; that's
already the right behavior, not something this loader needs to duplicate.
"""
import csv

DEFAULT_RADIUS_FT = 50.0


def load_foot_traffic_hotspots_from_csv(csv_path, site_width_ft, site_length_ft,
                                         default_radius_ft=DEFAULT_RADIUS_FT):
    """
    Read a foot-traffic CSV export and return a list of hotspot dicts in the
    real-feet format TerracingEngine's foot_traffic_hotspots expects
    ({"x", "y", "strength", "radius"} in real site feet) -- NOT the
    frac-based DEFAULT_FOOT_TRAFFIC_HOTSPOTS shape, since a caller passing
    their own foot_traffic_hotspots to TerracingEngine is expected to already
    be in real feet (only the module's own frac-based default gets converted
    internally). Ready to pass straight to
    TerracingEngine(foot_traffic_hotspots=...).
    """
    hotspots = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # case-insensitive column lookup
        fieldmap = {name.strip().lower(): name for name in reader.fieldnames or []}

        def get(row, key):
            return row.get(fieldmap[key]) if key in fieldmap else None

        required = ("x_frac", "y_frac", "strength")
        missing = [k for k in required if k not in fieldmap]
        if missing:
            raise ValueError(f"{csv_path}: missing required column(s) {missing} "
                              f"(found columns: {list(fieldmap.values())})")

        for i, row in enumerate(reader, start=2):  # start=2: row 1 is the header
            try:
                x_frac = float(get(row, "x_frac"))
                y_frac = float(get(row, "y_frac"))
                strength = float(get(row, "strength"))
            except (TypeError, ValueError):
                raise ValueError(f"{csv_path} line {i}: x_frac/y_frac/strength must be numeric, "
                                  f"got {get(row, 'x_frac')!r}/{get(row, 'y_frac')!r}/{get(row, 'strength')!r}")
            radius_raw = get(row, "radius_ft")
            radius_ft = float(radius_raw) if radius_raw not in (None, "") else default_radius_ft

            hotspots.append({
                "x": x_frac * site_width_ft,
                "y": y_frac * site_length_ft,
                "strength": strength,
                "radius": radius_ft,
            })

    if not hotspots:
        raise ValueError(f"{csv_path}: no data rows found")

    return hotspots


def find_latest_csv(folder=r"D:\MemoryMachine\data\foot_traffic_survey"):
    """Return the most recently modified .csv file in `folder`, or None."""
    import os
    if not os.path.isdir(folder):
        return None
    candidates = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)
