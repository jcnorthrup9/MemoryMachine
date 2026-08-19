"""
Regenerates the precedent-grid JSON embedded in html/final_deck.html's
page 04 (id="spread-5") from scripts/precedent_park_list.py's TILE_GROUPS --
the deck's rotating 50-tile grid is generated FROM the park registry
rather than hand-maintained, so any future edit to the park list (add/
remove/reorder a park) just needs a re-run of this script to stay in
sync, instead of someone hand-editing JSON inside the HTML.

Does a targeted string-replace between two HTML comment markers already
present in final_deck.html:
    <!-- PRECEDENT_GRID_DATA_START -->
    <script id="precedent-grid-data" type="application/json">...</script>
    <!-- PRECEDENT_GRID_DATA_END -->
so re-running this script never touches any other part of the deck.

Usage:
    .venv/Scripts/python.exe scripts/build_precedent_grid_data.py
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from precedent_park_list import TILE_GROUPS, safe_name  # noqa: E402

DECK_PATH = os.path.join(REPO_ROOT, "html", "final_deck.html")
# Path is relative to html/final_deck.html itself, matching that file's
# existing "../archive/diagrams/..." relative-path convention.
THUMB_REL_DIR = "../static/thumbnails/precedent"

START_MARKER = "<!-- PRECEDENT_GRID_DATA_START -->"
END_MARKER = "<!-- PRECEDENT_GRID_DATA_END -->"


def build_grid_json():
    tiles = []
    for group in TILE_GROUPS:
        cycle = [f"{THUMB_REL_DIR}/{safe_name(entry)}.jpg" for entry in group]
        tiles.append({"cycle": cycle, "names": [entry["name"] for entry in group]})
    return tiles


def main():
    tiles = build_grid_json()
    payload = json.dumps(tiles, ensure_ascii=False)

    with open(DECK_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    if START_MARKER not in html or END_MARKER not in html:
        print(f"[ERROR] Markers not found in {DECK_PATH} -- "
              f"expected '{START_MARKER}' and '{END_MARKER}'.")
        sys.exit(1)

    block = (
        f'{START_MARKER}\n'
        f'        <script id="precedent-grid-data" type="application/json">{payload}</script>\n'
        f'        {END_MARKER}'
    )

    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        re.DOTALL,
    )
    new_html, n = pattern.subn(block, html)
    if n != 1:
        print(f"[ERROR] Expected exactly 1 marker block, found {n}.")
        sys.exit(1)

    with open(DECK_PATH, "w", encoding="utf-8") as f:
        f.write(new_html)

    print(f"[OK] Wrote {len(tiles)} tile(s) x 3 park(s) into {DECK_PATH}")


if __name__ == "__main__":
    main()
