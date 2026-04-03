"""
autonomous_diagram_orchestrator.py
-----------------------------------
Autonomous pipeline: finds undiagrammed sites, runs the AI vision tracer on
their satellite images, and commands the live Rhino 8 session to open the
corresponding .3dm file and execute the generated drawing script.

Usage:
    .venv/Scripts/python.exe logic/autonomous_diagram_orchestrator.py
    .venv/Scripts/python.exe logic/autonomous_diagram_orchestrator.py --dry-run
    .venv/Scripts/python.exe logic/autonomous_diagram_orchestrator.py --site "Schouwburgplein"

Requires:
    - Rhino 8 open and running
    - GEMINI_API_KEY in .env
    - pip install pywin32 opencv-python google-genai
"""

import os
import sys
import re
import json
import argparse
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DIAGRAMS_DIR    = os.path.join(BASE_DIR, 'archive', 'diagrams')
SATELLITE_DIR   = os.path.join(BASE_DIR, 'assets', 'precedents')
PARK_DIAG_DIR   = os.path.join(os.path.expanduser("~"), "OneDrive - SCI-Arc", "2026_3GB_Spring", "SP26-Studio", "Rhino", "ParkDiagrams")
SCRIPTS_DIR     = os.path.join(BASE_DIR, 'data', 'orchestrator_scripts')
VISION_TRACER   = os.path.join(BASE_DIR, 'logic', 'ai_vision_tracer.py')

os.makedirs(SCRIPTS_DIR, exist_ok=True)
os.makedirs(DIAGRAMS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Site registry  (name → metadata used by the orchestrator)
# Each entry maps a SOURCE_INFO key to its satellite image slug, coordinate
# data for the vision tracer, and the matching .3dm filename.
# ---------------------------------------------------------------------------
SITE_MAP = {
    # SOURCE_INFO key          : satellite slug,               lat,        zoom,   3dm filename
    "Pershing Square"          : ("pershing_square",           34.0483,    18.0,   "PershingSquare.3dm"),
    "Schouwburgplein"          : ("schouwburgplein",           51.9226,    18.0,   "Schouwburgplein.3dm"),
    "Grand Park LA"            : ("grand_park_la",             34.0563,    17.5,   "GrandParkLA.3dm"),
    "Gardens by the Bay"       : ("gardens_by_the_bay",        1.2816,     17.0,   "GardensbytheBay.3dm"),
    "Superkilen"               : ("superkilen",                55.6964,    17.5,   None),
    "Paley Park"               : ("paley_park",                40.7601,    19.0,   None),
    "Klyde Warren Park"        : ("klyde_warren",              32.7893,    17.5,   None),
    "Millennium Park"          : ("millennium_park",           41.8826,    17.0,   None),
    "Parc de la Villette"      : ("parc_de_la_villette",       48.8937,    16.5,   "ParcdelaVillette.3dm"),
    "Zaryadye Park"            : ("zaryadye_park",             55.7510,    17.0,   "ZaryadyePark.3dm"),
    "Tanner Springs Park"      : ("tanner_springs",            45.5258,    19.0,   None),
    "The High Line"            : ("the_high_line",             40.7475,    17.0,   None),
    "Piazza del Campo"         : ("piazza_del_campo",          43.3183,    18.0,   None),
    "Federation Square"        : ("federation_square",         -37.8179,   18.0,   None),
    "Pioneer Courthouse Square": ("pioneer_courthouse_square", 45.5191,    19.0,   None),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slug(name):
    return re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')


def find_rhino_parsed(site_name):
    """
    Return path to existing _rhino_parsed.json for this site, or None.
    Checks both snake_case and PascalCase-ish filenames.
    """
    if not os.path.isdir(DIAGRAMS_DIR):
        return None
    s = slug(site_name)
    for f in os.listdir(DIAGRAMS_DIR):
        if '_rhino_parsed' in f.lower():
            stem = f.lower().replace('_rhino_parsed.json', '').replace('-', '_')
            if stem == s or stem == slug(s):
                return os.path.join(DIAGRAMS_DIR, f)
            # Also try matching without underscores (PascalCase flattened)
            if stem.replace('_', '') == s.replace('_', ''):
                return os.path.join(DIAGRAMS_DIR, f)
    return None


def find_satellite_image(site_key):
    """Return path to satellite image if it exists, else None."""
    sat_slug, *_ = SITE_MAP.get(site_key, (None,))
    if not sat_slug:
        return None
    path = os.path.join(SATELLITE_DIR, f"{sat_slug}_satellite.jpg")
    return path if os.path.exists(path) else None


def find_threedm(site_key):
    """Return path to .3dm file if it exists, else None."""
    entry = SITE_MAP.get(site_key)
    if not entry or not entry[3]:
        return None
    path = os.path.join(PARK_DIAG_DIR, entry[3])
    return path if os.path.exists(path) else None


def expected_drawing_script(site_name):
    """Return the path the vision tracer will write its output script to."""
    safe = site_name.lower().replace(' ', '_').replace(',', '').replace('.', '')
    return os.path.join(SCRIPTS_DIR, f"draw_diagram_{safe}.py")


# ---------------------------------------------------------------------------
# Step 1 — discover sites that need diagramming
# ---------------------------------------------------------------------------

def discover_pending_sites(target_site=None, force=False):
    """
    Returns list of dicts for sites that:
      - have a satellite image
      - do NOT already have a _rhino_parsed.json  (unless --force)
    """
    pending = []
    for site_name, (sat_slug, lat, zoom, threedm_file) in SITE_MAP.items():
        if target_site and site_name.lower() != target_site.lower():
            continue

        # Check if already parsed
        existing = find_rhino_parsed(site_name)
        if existing and not force:
            print(f"  [SKIP] {site_name} — rhino_parsed.json found: {os.path.basename(existing)}")
            continue
        if existing and force:
            print(f"  [FORCE] {site_name} — overwriting: {os.path.basename(existing)}")

        # Check for satellite image
        img = find_satellite_image(site_name)
        if not img:
            print(f"  [SKIP] {site_name} — no satellite image at assets/precedents/{sat_slug}_satellite.jpg")
            continue

        threedm = find_threedm(site_name)
        pending.append({
            "name":     site_name,
            "img":      img,
            "lat":      lat,
            "zoom":     zoom,
            "threedm":  threedm,
            "script":   expected_drawing_script(site_name),
        })
        threedm_label = os.path.basename(threedm) if threedm else "no .3dm"
        print(f"  [PENDING] {site_name} — {threedm_label}")

    return pending


# ---------------------------------------------------------------------------
# Step 2 — run the vision tracer to generate the drawing script
# ---------------------------------------------------------------------------

def run_vision_tracer(site):
    """
    Invokes ai_vision_tracer.py as a subprocess with UTF-8 encoding so that
    emoji in its print statements don't crash on Windows cp1252 consoles.
    Returns True if the output script was created successfully.
    """
    print(f"\n  [VISION TRACER] Analysing: {site['name']}")
    print(f"    Image : {site['img']}")
    print(f"    Lat   : {site['lat']}  Zoom: {site['zoom']}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = [
        sys.executable, VISION_TRACER,
        "--site",  site['name'],
        "--image", site['img'],
        "--lat",   str(site['lat']),
        "--zoom",  str(site['zoom']),
    ]

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        # Stream tracer output (strip emoji for safe Windows printing)
        for line in (result.stdout + result.stderr).splitlines():
            safe = line.encode('ascii', errors='replace').decode('ascii')
            print(f"    {safe}")
        if result.returncode != 0:
            print(f"  [ERROR] Vision tracer exited with code {result.returncode}")
            return False
    except subprocess.TimeoutExpired:
        print("  [ERROR] Vision tracer timed out after 120 seconds.")
        return False
    except Exception as e:
        print(f"  [ERROR] Could not launch vision tracer: {e}")
        return False

    if not os.path.exists(site['script']):
        print(f"  [ERROR] Expected script not created: {site['script']}")
        return False

    print(f"  [OK] Drawing script: {os.path.basename(site['script'])}")
    return True


# ---------------------------------------------------------------------------
# Step 3 — inject into Rhino via COM
# ---------------------------------------------------------------------------

def inject_into_rhino(site, dry_run=False):
    """
    Uses win32com to:
      1. Open the site's .3dm file (if available).
      2. Execute the generated drawing script via RunPythonScript.
    """
    if dry_run:
        print(f"  [DRY RUN] Would inject into Rhino:")
        if site['threedm']:
            print(f"    Open : {site['threedm']}")
        print(f"    Run  : {site['script']}")
        return True

    if not site['threedm']:
        print(f"  [WARN] No .3dm file for {site['name']} — skipping Rhino injection.")
        print(f"    Drawing script saved at: {site['script']}")
        print(f"    Run it manually via Rhino > Tools > Python Script > Run...")
        return True

    print(f"  [RHINO] Opening {os.path.basename(site['threedm'])} ...")
    try:
        import win32com.client

        # Connect to running Rhino 8 instance
        try:
            rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
        except Exception:
            rhino = win32com.client.dynamic.Dispatch("Rhino.Application")

        # Open the .3dm file — use the safe Rhino command string
        threedm_safe = site['threedm'].replace('\\', '/')
        open_cmd = f'_-Open "{threedm_safe}" _Enter'
        rhino.RunScript(open_cmd, 1)
        time.sleep(3)   # let Rhino finish loading the file

        # Execute the drawing script
        script_safe = site['script'].replace('\\', '/')
        run_cmd = f'_-RunPythonScript "{script_safe}"'
        print(f"  [RHINO] Executing drawing script...")
        rhino.RunScript(run_cmd, 1)
        time.sleep(2)

        # Save the file
        rhino.RunScript('_-Save _Enter', 1)
        print(f"  [OK] Rhino injection complete for {site['name']}.")
        return True

    except ImportError:
        print("  [ERROR] pywin32 not installed. Run: .venv/Scripts/pip install pywin32")
        print(f"    Script ready at: {site['script']}")
        return False
    except Exception as e:
        print(f"  [ERROR] Rhino COM error: {e}")
        print(f"    Script ready at: {site['script']}")
        return False


# ---------------------------------------------------------------------------
# Main orchestration loop
# ---------------------------------------------------------------------------

def orchestrate(target_site=None, dry_run=False, skip_rhino=False, force=False):
    print("\n" + "=" * 60)
    print("AUTONOMOUS DIAGRAM ORCHESTRATOR")
    print("=" * 60)

    # Confirm site list (SOURCE_INFO import may fail on Windows due to emoji in
    # app.py startup prints; SITE_MAP is the authoritative source here)
    try:
        import io, contextlib
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf), contextlib.redirect_stderr(_buf):
            from app import SOURCE_INFO
        print(f"[OK] SOURCE_INFO loaded — {len(SOURCE_INFO)} sites registered.\n")
    except Exception:
        print(f"[OK] Using built-in SITE_MAP — {len(SITE_MAP)} sites registered.\n")

    print("[1/3] Discovering pending sites...")
    pending = discover_pending_sites(target_site, force=force)

    if not pending:
        print("\n[DONE] All sites are already diagrammed. Nothing to do.")
        return

    print(f"\n[2/3] Processing {len(pending)} site(s)...")
    results = []
    for site in pending:
        print(f"\n--- {site['name']} ---")

        # Vision tracer
        traced = run_vision_tracer(site)
        if not traced:
            results.append((site['name'], 'TRACER_FAILED'))
            continue

        # Rhino injection
        if skip_rhino:
            print(f"  [SKIP RHINO] Script saved at: {site['script']}")
            results.append((site['name'], 'SCRIPT_ONLY'))
        else:
            ok = inject_into_rhino(site, dry_run=dry_run)
            results.append((site['name'], 'SUCCESS' if ok else 'RHINO_FAILED'))

    # Summary
    print("\n" + "=" * 60)
    print("[3/3] SUMMARY")
    print("=" * 60)
    for name, status in results:
        print(f"  {status:<20} {name}")

    success = sum(1 for _, s in results if s in ('SUCCESS', 'SCRIPT_ONLY', 'DRY_RUN'))
    print(f"\n  {success}/{len(results)} site(s) processed successfully.")
    if any(s == 'SCRIPT_ONLY' for _, s in results):
        print(f"\n  Scripts saved to: {SCRIPTS_DIR}")
        print("  Run them manually: Rhino > Tools > Python Script > Run...")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Autonomously diagram all unprocessed sites using AI vision + Rhino."
    )
    parser.add_argument(
        "--site", type=str, default=None,
        help="Process a single site by name (e.g. 'Schouwburgplein'). Default: all pending."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Discover and trace but do not open Rhino files."
    )
    parser.add_argument(
        "--skip-rhino", action="store_true",
        help="Run vision tracer only — save scripts but do not inject into Rhino."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-run even if a _rhino_parsed.json already exists (overwrites it)."
    )
    args = parser.parse_args()

    orchestrate(
        target_site = args.site,
        force       = args.force,
        dry_run     = args.dry_run,
        skip_rhino  = args.skip_rhino,
    )
