"""
Converts the real hospitality/amenity venue list from
D:\\boxy_player\\obsidian\\boxy_player\\PershingContext.md into the
data/amenity_deficits.json schema documented in
data/PershingMetabolizer/AMENITY_DEFICITS_GUIDE.md, replacing the
auto-seeded placeholder.

Run directly to regenerate data/amenity_deficits.json from RAW_VENUES below.
Re-run any time PershingContext.md changes -- update RAW_VENUES to match.
"""
import json
import os

DATA_DIR = r"D:\MemoryMachine\data"
OUTPUT_PATH = os.path.join(DATA_DIR, "amenity_deficits.json")

# Transcribed from D:\boxy_player\obsidian\boxy_player\PershingContext.md.
#
# x, y follow the grid convention in urban_interference_solver.py:
#   x: 0 = west (Olive St)  -> 29 = east (Hill St)
#   y: 0 = south (6th St)   -> 29 = north (5th St)
# Venues directly fronting the square use the same edge convention as
# data/building_heights.json. Venues "a few blocks away" are placed at
# extrapolated coordinates beyond 0-29 in the real direction described --
# the engine's inverse-distance falloff works correctly outside the grid
# bounds, it just attenuates their influence the way real distance would.
# These off-site positions are directional approximations, not geocoded.
#
# density is a 0-1 relative scale within its category: 1.0 = the largest/
# most intense venue of that category in this dataset. Derived from the
# qualitative "Size / Notes" column: huge/massive -> 1.0, large/high-volume
# -> 0.7-0.8, medium -> 0.45, modest/ground-floor retail -> 0.3.
RAW_VENUES = [
    {"name": "Millennium Biltmore Hotel", "category": "hospitality",
     "x": 1, "y": 22, "density": 1.0,
     "note": "501 S Olive St, directly west across Olive. 683 rooms, 170ft tall -- "
             "largest hospitality source in this dataset."},
    {"name": "The Nomad Hotel / Perla LA", "category": "hospitality",
     "x": 1, "y": 10, "density": 0.7,
     "note": "649 S Olive St / 400 S Broadway -- large hotel(s) nearby. Dual-address "
             "venue; placed south of the Biltmore along the Olive St frontage."},
    {"name": "Pershing Square Building (food retail)", "category": "surface_amenity",
     "x": 28, "y": 22, "density": 0.3,
     "note": "448 S Hill St, directly east across Hill. Ground-floor cafe/food retail only."},
    {"name": "Subway / Local Fast Food", "category": "surface_amenity",
     "x": 28, "y": 4, "density": 0.45,
     "note": "Along S Hill St corner blocks -- medium food supply, placed near the "
             "south end of the Hill St frontage."},
    {"name": "Grand Central Market", "category": "surface_amenity",
     "x": 55, "y": 50, "density": 1.0,
     "note": "317 S Broadway, a few blocks NE -- massive food supply hub. Off-site, "
             "extrapolated NE beyond the grid."},
    {"name": "Bottega Louie", "category": "surface_amenity",
     "x": -30, "y": -12, "density": 0.8,
     "note": "700 S Grand Ave, two blocks W/SW -- high-volume food destination. "
             "Off-site, extrapolated WSW beyond the grid."},
]


def normalize():
    points = []
    for v in RAW_VENUES:
        point = {"x": v["x"], "y": v["y"], "label": v["name"], "source_note": v["note"]}
        if v["category"] == "hospitality":
            point["hospitality_density"] = v["density"]
            point["surface_amenity_density"] = 0.0
        else:
            point["hospitality_density"] = 0.0
            point["surface_amenity_density"] = v["density"]
        points.append(point)

    payload = {
        "_meta": ("Real hospitality/amenity data transcribed from "
                  "D:\\boxy_player\\obsidian\\boxy_player\\PershingContext.md via normalize_amenity_data.py. "
                  "Replaces the auto-seeded placeholder. See "
                  "data/PershingMetabolizer/AMENITY_DEFICITS_GUIDE.md for the schema and grid orientation."),
        "points": points,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(points)} amenity points to {OUTPUT_PATH}")


if __name__ == "__main__":
    normalize()
