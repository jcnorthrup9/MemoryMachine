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

2026-07-12: the actual CSV-parsing body moved to hotspot_csv.py (shared
with foot_traffic.py/noise_survey.py, which had grown into byte-for-byte
copies of this same contract) -- this module now just wraps it with this
channel's own default radius/folder.
"""
from hotspot_csv import load_hotspots_from_csv, find_latest_csv_in, survey_dir, DEFAULT_RADIUS_FT


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
    return load_hotspots_from_csv(csv_path, site_width_ft, site_length_ft, default_radius_ft)


def find_latest_csv(folder=None):
    """Return the most recently modified .csv file in `folder`, or None.

    Defaults to data/amenity_survey/ relative to the repo root -- see
    hotspot_csv.survey_dir() for why this isn't an absolute path anymore.
    """
    return find_latest_csv_in(folder if folder is not None else survey_dir("amenity_survey"))
