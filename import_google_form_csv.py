"""
Converts a downloaded Google Forms responses CSV (Responses tab -> (kebab
menu) -> "Download responses (.csv)") into outputs/qr_event/submissions.jsonl
-- the exact record shape ingest_qr_event.py already reads, so that script
needs zero changes regardless of how responses were actually collected.

Expects a Form built per the companion plan's exact wording (checkbox
options / site options below) -- see that plan for the full field list.
Column headers are matched by SUBSTRING (not exact text) so small
rewording of the question prompts themselves doesn't break this; the
OPTION LABELS inside each answer do need to match LAYER_LABEL_TO_ID/
SITE_LABEL_TO_ID below (case/whitespace-insensitive) -- any option text
that doesn't match is reported as a warning, not silently dropped, so a
Form wording mismatch gets caught in a dry run instead of quietly losing
votes.

Usage: python import_google_form_csv.py path/to/responses.csv
"""
import csv
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
EVENT_DIR = os.path.join(REPO_ROOT, "outputs", "qr_event")
SUBMISSIONS_PATH = os.path.join(EVENT_DIR, "submissions.jsonl")

# Must match the checkbox option labels used when the Google Form was
# actually built (see this repo's plan for the exact wording given to the
# user) -- keys are matched case/whitespace-insensitively.
LAYER_LABEL_TO_ID = {
    "more shade": "SHADE",
    "more green space": "GREEN_SPACE",
    "more water": "WATER_FEATURES",
    "more plaza / hardscape": "HARDSCAPE",
    "more walking paths": "PEDESTRIAN_PATH",
    "more seating": "STREET_FURNITURE",
    "a landmark feature": "MAJOR_ATTRACTORS",
}

SITE_LABEL_TO_ID = {
    "pershing square (la)": "PershingSquare",
    "parc de la villette (paris)": "ParcVillette",
    "zaryadye park (moscow)": "ZaryadyePark",
    "schouwburgplein (rotterdam)": "Schouwburgplein",
    "gardens by the bay (singapore)": "GardensBytheBay",
    "no preference": None,
}

# Substrings to find each question's column by, independent of exact
# question phrasing -- e.g. a "missing" column header matches "What's
# missing?" or "What would you add?" equally.
LAYER_COLUMN_HINT = "missing"
SITE_COLUMN_HINT = "park"
TEXT_COLUMN_HINT = "else"


def _find_column(fieldnames, hint):
    for name in fieldnames:
        if hint.lower() in name.lower():
            return name
    return None


def _parse_layers(cell):
    layers = []
    for label in (cell or "").split(","):
        label = label.strip().lower()
        if not label:
            continue
        canonical = LAYER_LABEL_TO_ID.get(label)
        if canonical:
            layers.append(canonical)
        else:
            print(f"      WARNING: unrecognized layer option {label!r} -- check Form wording matches LAYER_LABEL_TO_ID")
    return layers


def _parse_site(cell):
    label = (cell or "").strip().lower()
    if not label:
        return None
    if label in SITE_LABEL_TO_ID:
        return SITE_LABEL_TO_ID[label]
    print(f"      WARNING: unrecognized site option {label!r} -- check Form wording matches SITE_LABEL_TO_ID")
    return None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    csv_path = sys.argv[1]

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        layer_col = _find_column(fieldnames, LAYER_COLUMN_HINT)
        site_col = _find_column(fieldnames, SITE_COLUMN_HINT)
        text_col = _find_column(fieldnames, TEXT_COLUMN_HINT)

        print(f"Detected columns -- layers: {layer_col!r}, site: {site_col!r}, text: {text_col!r}")
        if not (layer_col or site_col or text_col):
            print(f"ERROR: none of the expected columns were found. Available headers: {fieldnames}")
            sys.exit(1)

        rows = list(reader)

    os.makedirs(EVENT_DIR, exist_ok=True)
    written = 0
    with open(SUBMISSIONS_PATH, "a", encoding="utf-8") as out:
        for row in rows:
            record = {
                "ts": row.get("Timestamp", ""),
                "layers": _parse_layers(row.get(layer_col, "")) if layer_col else [],
                "site": _parse_site(row.get(site_col, "")) if site_col else None,
                "text": (row.get(text_col, "") or "").strip()[:500] if text_col else "",
            }
            out.write(json.dumps(record) + "\n")
            written += 1

    print(f"{written} responses imported from {csv_path} -> {SUBMISSIONS_PATH}")
    print("Run ingest_qr_event.py next.")


if __name__ == "__main__":
    main()
