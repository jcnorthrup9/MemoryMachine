"""
Memory Machine -- Noise Data Ingestion (2026-07-12).

A third real-data channel, alongside amenity_deficit.py (survey-based
deficit) and foot_traffic.py (foot traffic) -- see hotspot_csv.py for the
shared x_frac/y_frac/strength/radius_ft CSV contract all three now use.

Feeds terracing_engine.py's Voxel.noise_influence, which -- unlike
deficit_influence/foot_traffic_influence -- does NOT affect excavation
depth at all. It only feeds _classify_typology's SANCTUARY check, scaled by
RebuildParams.data_alpha: a cell painted greenscape+amenity_resting is only
classified SANCTUARY if the real (or placeholder) noise data at that point,
times data_alpha, stays below SANCTUARY_NOISE_THRESHOLD -- data_alpha=0
means noise data never overrides the designer's painted intent (matches
sketch_alpha's own "designer-dominant by default" framing); data_alpha=1
means a loud real-world location can't earn SANCTUARY status no matter what
was painted there.
"""
from hotspot_csv import load_hotspots_from_csv, find_latest_csv_in, survey_dir, DEFAULT_RADIUS_FT


def load_noise_hotspots_from_csv(csv_path, site_width_ft, site_length_ft,
                                  default_radius_ft=DEFAULT_RADIUS_FT):
    """
    Read a noise-survey CSV export and return a list of hotspot dicts in the
    real-feet format TerracingEngine's noise_hotspots expects ({"x", "y",
    "strength", "radius"} in real site feet). Ready to pass straight to
    TerracingEngine(noise_hotspots=...).
    """
    return load_hotspots_from_csv(csv_path, site_width_ft, site_length_ft, default_radius_ft)


def find_latest_csv(folder=None):
    """Return the most recently modified .csv file in `folder`, or None.

    Defaults to data/noise_survey/ relative to the repo root -- see
    hotspot_csv.survey_dir() for why this isn't an absolute path anymore.
    """
    return find_latest_csv_in(folder if folder is not None else survey_dir("noise_survey"))
