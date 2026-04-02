# -*- coding: utf-8 -*-
"""
one_click_diagram.py
--------------------
Run inside Rhino 8 via: Tools > Python Script > Run...
Or assign to a Rhino alias:
    MemDiagram  ->  _RunPythonScript "C:\\Users\\jcnor\\MemoryMachine\\logic\\one_click_diagram.py"

What it does in one click:
  1. Detects which site the currently open .3dm belongs to.
  2. Launches the AI vision tracer externally (generates the drawing script).
  3. Executes the generated drawing script inside the live Rhino session.
"""

import os
import sys
import re
import subprocess
import time
import rhinoscriptsyntax as rs
import scriptcontext as sc
import Rhino

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR      = r"C:\Users\jcnor\MemoryMachine"
VENV_PYTHON   = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
TRACER        = os.path.join(BASE_DIR, "logic", "ai_vision_tracer.py")
SCRIPTS_DIR   = os.path.join(BASE_DIR, "data", "orchestrator_scripts")
SATELLITE_DIR = os.path.join(BASE_DIR, "assets", "precedents")

# Map .3dm filename stems to (site_name, satellite_slug, lat, zoom)
SITE_MAP = {
    "GardensbytheBay":        ("Gardens by the Bay",        "gardens_by_the_bay",        1.2816,   17.0),
    "GrandParkLA":            ("Grand Park LA",              "grand_park_la",              34.0563,  17.5),
    "MaggieDaleyPark":        ("Maggie Daley Park",          "millennium_park",            41.8826,  17.0),
    "ZaryadyePark":           ("Zaryadye Park",              "zaryadye_park",              55.7510,  17.0),
    "ParcdelaVillette":       ("Parc de la Villette",        "parc_de_la_villette",        48.8937,  16.5),
    "PershingSquare":         ("Pershing Square",            "pershing_square",            34.0483,  18.0),
    "Schouwburgplein":        ("Schouwburgplein",            "schouwburgplein",            51.9226,  18.5),
    "TheHighLine":            ("The High Line",              "the_high_line",              40.7475,  18.0),
    "FederationSquare":       ("Federation Square",          "federation_square",          -37.8179, 18.5),
    "PioneerCourthouseSquare":("Pioneer Courthouse Square",  "pioneer_courthouse_square",  45.5191,  19.0),
    "Superkilen":             ("Superkilen",                 "superkilen",                 55.6964,  16.5),
    "KlydeWarrenPark":        ("Klyde Warren Park",          "klyde_warren",               32.7893,  17.5),
    "MillenniumPark":         ("Millennium Park",            "millennium_park",            41.8826,  17.0),
    "TannerSpringsPark":      ("Tanner Springs Park",        "tanner_springs",             45.5258,  19.0),
    "PaleyPark":              ("Paley Park",                 "paley_park",                 40.7601,  20.0),
}


def slug_to_script(site_name):
    safe = site_name.lower()
    safe = re.sub(r"[^a-z0-9]+", "_", safe).strip("_")
    return os.path.join(SCRIPTS_DIR, "draw_diagram_{}.py".format(safe))


def main():
    print("=" * 60)
    print("MEMORY MACHINE  --  One-Click Diagram")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Identify site from current document name
    # ------------------------------------------------------------------
    doc_name = sc.doc.Name or ""
    stem     = os.path.splitext(doc_name)[0]

    site_info = SITE_MAP.get(stem)
    if site_info is None:
        print("[ERROR] '{}' is not a recognised site file.".format(doc_name))
        print("        Recognised stems: {}".format(", ".join(SITE_MAP.keys())))
        return

    site_name, sat_slug, lat, zoom = site_info
    sat_image   = os.path.join(SATELLITE_DIR, "{}_satellite.jpg".format(sat_slug))
    script_path = slug_to_script(site_name)

    print("Site     : {}".format(site_name))
    print("Image    : {}".format(sat_image))
    print("Script   : {}".format(script_path))
    print()

    if not os.path.exists(sat_image):
        print("[ERROR] Satellite image not found: {}".format(sat_image))
        print("        Run: .venv/Scripts/python.exe logic/precedent_scraper.py --satellites")
        return

    # ------------------------------------------------------------------
    # 2. Run the AI vision tracer (external process, UTF-8 safe)
    # ------------------------------------------------------------------
    print("[1/2] Running AI vision tracer...")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        VENV_PYTHON, TRACER,
        "--site",  site_name,
        "--image", sat_image,
        "--lat",   str(lat),
        "--zoom",  str(zoom),
    ]

    try:
        process = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout_data, stderr_data = process.communicate()
        
        output = ""
        if stdout_data:
            output += stdout_data.decode("utf-8", "replace") if hasattr(stdout_data, "decode") else str(stdout_data)
        if stderr_data:
            output += stderr_data.decode("utf-8", "replace") if hasattr(stderr_data, "decode") else str(stderr_data)
            
        for line in output.splitlines():
            try:
                safe_line = line.encode("ascii", "replace").decode("ascii")
            except:
                safe_line = str(line)
            print("  " + safe_line)
            
        if process.returncode != 0:
            print("[ERROR] Vision tracer failed (exit {}).".format(process.returncode))
            return
    except Exception as e:
        print("[ERROR] Could not launch tracer: {}".format(e))
        return

    if not os.path.exists(script_path):
        print("[ERROR] Expected script not created: {}".format(script_path))
        return

    print("  [OK] Script generated.")

    # ------------------------------------------------------------------
    # 3. Execute the generated drawing script inside Rhino
    # ------------------------------------------------------------------
    print("[2/2] Executing drawing script in Rhino...")
    script_safe = script_path.replace("\\", "/")
    Rhino.RhinoApp.RunScript('_-RunPythonScript "{}"'.format(script_safe), False)
    Rhino.RhinoApp.Wait()
    time.sleep(1.0)

    sc.doc.Views.Redraw()
    print()
    print("=" * 60)
    print("Done. Diagram drawn for: {}".format(site_name))
    print("=" * 60)


try:
    main()
except Exception as _e:
    import traceback
    print("[FATAL] {}".format(_e))
    traceback.print_exc()
