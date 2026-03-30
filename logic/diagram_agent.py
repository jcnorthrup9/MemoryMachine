"""
diagram_agent.py
----------------
Vision-Language agent that analyses an architectural diagram and extracts
spatial relationships as structured JSON.

Uses: google-generativeai (Gemini multimodal) + Pillow for image loading.

Usage:
    .venv/Scripts/python.exe logic/diagram_agent.py <image_path>
    .venv/Scripts/python.exe logic/diagram_agent.py archive/diagrams/superkilen_diagram.png

Output (stdout): clean JSON like:
    {
      "site": "...",
      "zones": [ {"id": "A", "label": "splash pad", "character": "..."}, ... ],
      "paths": [ {"id": "P1", "label": "main promenade", "connects": ["A","B"]}, ... ],
      "relationships": [ "seating area adjacent to water feature", ... ],
      "material_notes": [...],
      "program_notes": [...]
    }
"""

import os, sys, json, argparse, base64, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── prompt ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a spatial analyst and architectural critic working on a public space redesign project.
You have been given a diagram, plan, or aerial image of an outdoor public space.

Your task: analyse the image and return a structured JSON object with the following keys:

  "site"          : (string) Your best guess at the site name or "Unknown"
  "zones"         : (array) Each zone is {"id":"Z1","label":"...","character":"...", "box": [ymin, xmin, ymax, xmax]}
                    Identify distinct spatial zones: plazas, lawns, water features, seating areas,
                    performance spaces, service edges, thresholds, etc. For 'box', provide the bounding box capturing the zone using normalized coordinates from 0 to 1000 (where [0,0] is top-left and [1000,1000] is bottom-right).
  "paths"         : (array) Each path is {"id":"P1","label":"...","type":"primary|secondary|edge", "connects":["zone_id","zone_id"], "box": [ymin, xmin, ymax, xmax]}
                    Identify major and minor circulation routes. For 'box', provide the bounding box encompassing the path using 0-1000 normalized coordinates.
  "relationships" : (array of strings) Describe 6-10 spatial relationships between zones and paths.
                    Examples: "water feature anchors the geometric centre",
                    "stepped seating creates acoustic bowl facing performance stage",
                    "canopy edges define soft boundary between active and passive zones"
  "material_notes": (array of strings) Observations on visible materials, textures, surface types.
  "program_notes" : (array of strings) Inferred programmatic activations, events, social dynamics.
  "scale_notes"   : (string) Any observations on scale, proportion, human vs monumental elements.
  "design_logic"  : (string) One paragraph summary of the dominant spatial / design logic.

Return ONLY valid JSON — no markdown code fences, no explanations outside the JSON object.
If the image is unclear or abstract, make your best analytical interpretation.
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def load_image_bytes(path):
    from PIL import Image
    import io
    # Normalise to JPEG for API compatibility
    img = Image.open(path).convert("RGB")
    # Downscale if very large (API has a size limit)
    max_dim = 2048
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize(
            (int(img.width * ratio), int(img.height * ratio)),
            Image.LANCZOS
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue(), "image/jpeg"


def call_gemini(image_path):
    from dotenv import load_dotenv
    from google import genai
    from google.genai import types

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")
    
    client = genai.Client(api_key=api_key)

    img_bytes, mime = load_image_bytes(image_path)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            SYSTEM_PROMPT,
            types.Part.from_bytes(data=img_bytes, mime_type=mime)
        ]
    )
    return response.text.strip()


def annotate_image(image_path, data, output_path):
    """Draws bounding boxes from the AI's JSON back onto the image."""
    from PIL import Image, ImageDraw
    
    try:
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size
        
        def draw_box(item, outline_color):
            box = item.get("box")
            if box and len(box) == 4:
                ymin, xmin, ymax, xmax = box
                # Convert 0-1000 normalized coords to actual image pixels
                px0, py0 = (xmin * w) / 1000, (ymin * h) / 1000
                px1, py1 = (xmax * w) / 1000, (ymax * h) / 1000
                
                # Draw thick bounding box
                draw.rectangle([px0, py0, px1, py1], outline=outline_color, width=4)
                # Draw label text just above the box
                label = f"{item.get('id', '?')}: {item.get('label', 'Unknown')}"
                draw.text((px0, max(0, py0 - 15)), label, fill=outline_color)

        for zone in data.get("zones", []):
            draw_box(zone, "red")
            
        for path in data.get("paths", []):
            draw_box(path, "blue")
            
        img.save(output_path)
        print(f"[OK] Saved annotated visual map to {output_path}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] Failed to annotate image: {e}", file=sys.stderr)

def clean_json_response(text):
    """Strip any accidental markdown fences from the model output."""
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$',          '', text, flags=re.MULTILINE)
    return text.strip()


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyse an architectural diagram with Gemini Vision and output spatial JSON."
    )
    parser.add_argument("image", help="Path to the diagram image (PNG, JPG, etc.)")
    parser.add_argument("--pretty", action="store_true", default=True,
                        help="Pretty-print the JSON output (default: True)")
    parser.add_argument("--save", metavar="FILE",
                        help="Also save the JSON to a file")
    args = parser.parse_args()

    # Validate image path
    image_path = args.image
    if not os.path.isabs(image_path):
        image_path = os.path.join(BASE_DIR, image_path)
    if not os.path.exists(image_path):
        print(f"[ERROR] Image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[DIAGRAM AGENT] Analysing: {os.path.basename(image_path)}", file=sys.stderr)

    try:
        raw = call_gemini(image_path)
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Gemini call failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse and re-emit clean JSON
    cleaned = clean_json_response(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Could not parse model response as JSON: {e}", file=sys.stderr)
        print("[RAW RESPONSE]", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(1)

    indent = 2 if args.pretty else None
    output = json.dumps(data, indent=indent, ensure_ascii=False)
    print(output)

    if args.save:
        save_path = args.save
        if not os.path.isabs(save_path):
            save_path = os.path.join(BASE_DIR, save_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[OK] Saved to {save_path}", file=sys.stderr)
        
        # Generate and save the annotated image alongside the JSON
        base_name = os.path.splitext(save_path)[0]
        annotated_img_path = f"{base_name}_annotated.jpg"
        annotate_image(image_path, data, annotated_img_path)

    print(f"[DONE] Extracted {len(data.get('zones',[]))} zones, "
          f"{len(data.get('paths',[]))} paths, "
          f"{len(data.get('relationships',[]))} relationships.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
