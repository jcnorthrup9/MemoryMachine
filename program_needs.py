"""
Memory Machine -- Program Needs Ingestion.

Reads data/amenityData/amenity_needs.csv (transcribed from a site-specific
Amenity Needs Report -- see data/amenityData/andres/) and returns structured
records for reconciling against / cross-checking data/program_requirements.json.
Same case-insensitive-column pattern as amenity_deficit.py's
load_deficit_hotspots_from_csv, but this CSV carries WHAT to build and HOW
MUCH (target_sf) and PRIORITY (need_level), not spatial coordinates --
placement location comes from a separate signal (see logic/program_placement.py).

CSV contract (columns, case-insensitive, extra columns ignored):
  category      -- required. Broad grouping (Green Space, Sports, Enrichment,
                    Outdoor, Health Care, Fresh Food, ...).
  program_item  -- required, may be blank (e.g. the Fresh Food row, which has
                    no specific item -- the category itself was assessed as
                    not needed).
  need_level    -- required. One of NEEDED / Suggested / Optional, the
                    report's own priority tier.
  target_sf     -- required. Suggested square footage for that item (0 if
                    nothing is actually being suggested, e.g. Fresh Food).
  notes         -- optional, free text.
"""
import csv
import os

DEFAULT_CSV_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "amenityData", "amenity_needs.csv")

VALID_NEED_LEVELS = ("NEEDED", "Suggested", "Optional")


def load_amenity_needs_csv(csv_path=DEFAULT_CSV_PATH):
    """
    Read amenity_needs.csv and return a list of dicts:
    {"category", "program_item", "need_level", "target_sf", "notes"}.
    Rows with a blank program_item (documenting a category assessed as not
    needed, e.g. Fresh Food) are still returned -- callers that want only
    placeable items should filter on program_item/target_sf themselves.
    """
    records = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldmap = {name.strip().lower(): name for name in reader.fieldnames or []}

        def get(row, key):
            return row.get(fieldmap[key]) if key in fieldmap else None

        required = ("category", "need_level", "target_sf")
        missing = [k for k in required if k not in fieldmap]
        if missing:
            raise ValueError(f"{csv_path}: missing required column(s) {missing} "
                              f"(found columns: {list(fieldmap.values())})")

        for i, row in enumerate(reader, start=2):  # start=2: row 1 is the header
            need_level = (get(row, "need_level") or "").strip()
            if need_level not in VALID_NEED_LEVELS:
                raise ValueError(f"{csv_path} line {i}: need_level must be one of "
                                  f"{VALID_NEED_LEVELS}, got {need_level!r}")
            try:
                target_sf = float(get(row, "target_sf"))
            except (TypeError, ValueError):
                raise ValueError(f"{csv_path} line {i}: target_sf must be numeric, "
                                  f"got {get(row, 'target_sf')!r}")

            records.append({
                "category": (get(row, "category") or "").strip(),
                "program_item": (get(row, "program_item") or "").strip(),
                "need_level": need_level,
                "target_sf": target_sf,
                "notes": (get(row, "notes") or "").strip(),
            })

    if not records:
        raise ValueError(f"{csv_path}: no data rows found")

    return records
