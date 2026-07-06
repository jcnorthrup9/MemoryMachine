import os
import json
import webbrowser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
PLAN_DATA_FILE = os.path.join(DATA_DIR, 'project_plan.json')
FIGMA_PLAN_OUTPUT = os.path.join(DATA_DIR, 'figma_plan_payload.json')

def build_plan_payload():
    """Generates the content payload for the project plan."""
    if not os.path.exists(PLAN_DATA_FILE):
        print(f"❌ Plan data file not found at {PLAN_DATA_FILE}")
        return None

    with open(PLAN_DATA_FILE, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)

    # The payload is a list of "slides", but in this case, just one.
    payload = {
        "slides": [
            {
                "type": "project_plan_slide",
                "title": plan_data.get("title", "Project Plan"),
                "weeks": plan_data.get("weeks", [])
            }
        ]
    }
    return payload

def compile_plan():
    print("\n--- Compiling Project Plan for Figma ---")
    payload = build_plan_payload()
    if payload:
        with open(FIGMA_PLAN_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        print(f"✅ FIGMA PLAN PAYLOAD GENERATED: {FIGMA_PLAN_OUTPUT}")

if __name__ == "__main__":
    compile_plan()