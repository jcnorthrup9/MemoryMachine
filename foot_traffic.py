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

2026-07-12: the actual CSV-parsing body moved to hotspot_csv.py (shared
with amenity_deficit.py/noise_survey.py, which had grown into byte-for-byte
copies of this same contract) -- this module now just wraps it with this
channel's own default radius/folder.
"""
from hotspot_csv import load_hotspots_from_csv, find_latest_csv_in, survey_dir, DEFAULT_RADIUS_FT


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
    return load_hotspots_from_csv(csv_path, site_width_ft, site_length_ft, default_radius_ft)


def find_latest_csv(folder=None):
    """Return the most recently modified .csv file in `folder`, or None.

    Defaults to data/foot_traffic_survey/ relative to the repo root -- see
    hotspot_csv.survey_dir() for why this isn't an absolute path anymore.
    """
    return find_latest_csv_in(folder if folder is not None else survey_dir("foot_traffic_survey"))
