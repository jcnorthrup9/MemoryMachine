"""
batch_rhino_parser.py
---------------------
Orchestrates the analysis of all .3dm diagram files by commanding a live
Rhino instance to open each file and run the rhino_diagram_parser.py script.

This script runs in your standard Python environment, not inside Rhino.

Usage:
    .venv/Scripts/python.exe logic/batch_rhino_parser.py
"""

import os
import sys
import time
import win32com.client

import argparse # Added for command-line arguments

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSER_SCRIPT_PATH = os.path.abspath(os.path.join(BASE_DIR, 'logic', 'rhino_diagram_parser.py'))

def main():
    parser = argparse.ArgumentParser(description="Orchestrates Rhino diagram parsing.")
    parser.add_argument("--folder", default=os.path.join(os.path.expanduser("~"), "OneDrive - SCI-Arc", "2026_3GB_Spring", "SP26-Studio", "Rhino", "ParkDiagrams"),
                        help="Path to the folder containing .3dm diagram files.")
    args = parser.parse_args()

    DIAGRAM_FOLDER = args.folder
    if not os.path.exists(DIAGRAM_FOLDER):
        print(f"❌ Error: Diagram folder not found at {DIAGRAM_FOLDER}")
        return

    diagram_files = [f for f in os.listdir(DIAGRAM_FOLDER) if f.lower().endswith('.3dm')]
    if not diagram_files:
        print("ℹ️ No .3dm files found in the diagram folder.")
        return

    print(f"Found {len(diagram_files)} diagrams to process. Connecting to Rhino...")

    try:
        # More robust connection logic with fallbacks
        try:
            rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
        except Exception:
            rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
        
        try:
            rs_app = rhino.GetScriptObject()
        except Exception:
            rs_app = rhino # Fallback to using the main rhino object
    except Exception as e:
        print(f"❌ Error connecting to Rhino: {e}")
        print("   Please ensure Rhino 8 is running.")
        return

    for filename in diagram_files:
        file_path = os.path.join(DIAGRAM_FOLDER, filename)
        print(f"\n--- Processing: {filename} ---")

        # Command Rhino to open the file
        print(f"    -> Sending command to open '{filename}'...")
        open_cmd = f'_-Open "{file_path}" _Enter'
        if not rs_app.RunScript(open_cmd, 1):
            print(f"    ❌ WARN: Rhino was busy or failed to open the file. Skipping.")
            continue
        time.sleep(5) # Give Rhino time to load the file
        print(f"    -> File should be open. Running parser...")

        # Command Rhino to run the parser script
        parse_cmd = f'_-ScriptEditor Run "{PARSER_SCRIPT_PATH}"'
        if rs_app.RunScript(parse_cmd, 1):
            print(f"    -> Parser script executed for '{filename}'.")
        else:
            print(f"    ❌ WARN: Rhino was busy or failed to run the parser script.")
        time.sleep(2) # Wait for parser to finish

    print("\n✅ Batch processing complete!")

if __name__ == "__main__":
    main()