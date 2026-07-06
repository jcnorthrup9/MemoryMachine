"""
Memory Machine -- Amenity-Deficit Data Ingestion (Section 2).

Replaces terracing_engine.py's DEFAULT_DEFICIT_HOTSPOTS (a 2-point diagrammatic
placeholder) with real survey data -- per project decision, a Google Forms
export dropped into a data folder, not a scraped dataset.

CSV contract (columns, case-insensitive, extra columns ignored):
  x_frac, y_frac   -- required. Normalized site position, 0..1 each, same
                       convention as DEFAULT_DEFICIT_HOTSPOTS: x_frac along
                       the site's width axis, y_frac along its length axis.
                       A Google Form can't natively collect this directly --
                       expected workflow is the organizer curates raw survey
                       responses (e.g. "which corner of the plaza", a written
                       location description) into approximate x_frac/y_frac
                       before dropping the CSV in, same kind of manual
                       curation step real survey data usually needs anyway.
  strength         -- required. 0..1, how strongly this response indicates
                       amenity deficit at that point (e.g. a normalized
                       1-5 Likert-scale rating).
  radius_ft        -- optional, defaults to DEFAULT_RADIUS_FT. How far this
                       response's influence extends. Not something a survey
                       respondent would set -- a per-project tuning constant,
                       left as a column mainly so it CAN be overridden per
                       row if curating multiple response types together.

No aggregation/clustering is done here -- every row becomes its own hotspot.
Multiple nearby weak responses naturally combine into a stronger influence
via terracing_engine.py's existing additive deficit_influence sum; that's
already the right behavior, not something this loader needs to duplicate.
"""
import csv

DEFAULT_RADIUS_FT = 50.0


def load_deficit_hotspots_from_csv(csv_path, site_width_ft, site_length_ft,
                                    default_radius_ft=DEFAULT_RADIUS_FT):
    """
    Read a Google-Forms-style CSV export and return a list of hotspot dicts
    in the real-feet format TerracingEngine's deficit_hotspots expects
    ({"x", "y", "strength", "radius"} in real site feet) -- NOT the
    frac-based DEFAULT_DEFICIT_HOTSPOTS shape, since a caller passing their
    own deficit_hotspots to TerracingEngine is expected to already be in
    real feet (only the module's own frac-based default gets converted
    internally). Ready to pass straight to TerracingEngine(deficit_hotspots=...).
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


def find_latest_csv(folder=r"D:\MemoryMachine\data\amenity_survey"):
    """Return the most recently modified .csv file in `folder`, or None."""
    import os
    if not os.path.isdir(folder):
        return None
    candidates = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)
