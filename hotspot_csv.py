"""
Memory Machine -- Shared CSV Hotspot-Loader (2026-07-12).

Extracted from amenity_deficit.py/foot_traffic.py, which had grown into two
byte-for-byte identical implementations of the exact same x_frac/y_frac/
strength/radius_ft CSV contract for two different data channels -- adding a
THIRD channel (noise, see noise_survey.py) by copy-pasting a third time
would have made "the contract" implicit and driftable instead of a single
source of truth. Both existing modules now delegate here; their own
find_latest_csv() stays separate (folder-specific) since that part is
genuinely per-channel, not shared.

CSV contract (columns, case-insensitive, extra columns ignored):
  x_frac, y_frac   -- required. Normalized site position, 0..1 each: x_frac
                       along the site's width axis, y_frac along its length
                       axis.
  strength         -- required. 0..1, how strongly this point indicates the
                       channel's phenomenon (deficit / foot traffic / noise
                       / etc) at that location.
  radius_ft        -- optional, defaults to default_radius_ft. How far this
                       point's influence extends -- a per-project tuning
                       constant, left as a column mainly so it CAN be
                       overridden per row if curating multiple sources
                       together.

No aggregation/clustering is done here -- every row becomes its own
hotspot. Multiple nearby weak points naturally combine into a stronger
influence via terracing_engine.py's existing additive per-channel sum;
that's already the right behavior, not something this loader needs to
duplicate.
"""
import csv
import os

DEFAULT_RADIUS_FT = 50.0


def load_hotspots_from_csv(csv_path, site_width_ft, site_length_ft, default_radius_ft=DEFAULT_RADIUS_FT):
    """
    Read a hotspot CSV export and return a list of dicts in the real-feet
    format TerracingEngine's *_hotspots constructor args expect
    ({"x", "y", "strength", "radius"} in real site feet) -- NOT the
    frac-based shape a module's own DEFAULT_*_HOTSPOTS placeholder uses
    (only those get converted internally by TerracingEngine itself). Ready
    to pass straight to TerracingEngine(<channel>_hotspots=...).
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


def find_latest_csv_in(folder):
    """Return the most recently modified .csv file in `folder`, or None."""
    if not os.path.isdir(folder):
        return None
    candidates = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)
