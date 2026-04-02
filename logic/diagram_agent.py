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
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── prompt ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are a world-class spatial analyst and architectural critic. You have been given a manually-drawn architectural diagram of a public space which may include a legend. Your first priority is to find and interpret the legend. All classifications MUST adhere to the provided legend.

Your task: analyse the image and return a structured JSON object with the following keys:

  "site":             (string) Your best guess at the site name or "Unknown".
  "orientation_analysis": (string) Describe the site's orientation relative to the primary surrounding street grid. Note if the site is orthogonal, rotated (e.g., 'rotated 45 degrees'), or irregular in relation to the streets.
  "zones":            (array) Each zone is {"id":"A", "label":"...", "type":"...", "system":"...", "character":"...", "bounding_polygon": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "rotation_degrees": 0}.
                      Identify distinct spatial zones. Use the diagram's legend to classify the "type" as one of:
                      "Main Attractor", "Minor Attractor", "Water Feature", "Green Space", "Unique Element", "Hardscape Plaza".
                      Classify its "system" as "points" (for discrete attractors/follies), or "surfaces" (for broad areas like plazas/gardens).
                      The "bounding_polygon" must be a TIGHT quadrilateral enclosing the individual element, following its orientation. For a small circle, it should tightly enclose it. The coordinates must be normalized (0-1000). "rotation_degrees" is optional, 0 if axis-aligned, otherwise estimate clockwise rotation relative to image top.
  "paths":            (array) Each path is {"id":"P1", "label":"...", "type":"...", "system":"lines", "connects":["zone_id","zone_id"], "bounding_polygon": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "rotation_degrees": 0}.
                      Identify circulation routes. Use the legend to classify the "type" as:
                      "Vehicular Street", "Primary Pedestrian", "Secondary Pedestrian", "Site Boundary", "Infrastructure Connection".
                      All paths belong to the "lines" system.
                      The "bounding_polygon" must be a TIGHT quadrilateral enclosing the individual line segment, following its orientation. The coordinates must be normalized (0-1000). "rotation_degrees" is optional, 0 if axis-aligned, otherwise estimate clockwise rotation relative to image top.
  "erasure_targets":  (array of strings) If you see any zone or path explicitly labeled with text like `[HOSTILE]`, `[ERASE]`, or `[TARGET]`,
                      add its label to this list. This is for identifying elements to be overwritten.
  "relationships":    (array of strings) Describe 6-10 key spatial relationships between zones, paths, and systems.
                      Examples: "The 'points' system of follies is overlaid on the 'surfaces' system of green space, creating deliberate tension.",
                      "The 'lines' system of pathways connects the attractors in a non-hierarchical network."
  "design_logic":     (string) One paragraph summary of the dominant spatial logic, referencing the relationships and systems you found.

Return ONLY valid JSON — no markdown code fences, no explanations outside the JSON object.
If the image is unclear or abstract, make your best analytical interpretation.
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def load_image_base64(path):
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
    return base64.b64encode(buf.getvalue()).decode("utf-8"), "image/jpeg"


def call_gemini(image_path):
    from dotenv import load_dotenv
    import google.generativeai as genai

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")
    genai.configure(api_key=api_key)

    img_b64, mime = load_image_base64(image_path)

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([
        SYSTEM_PROMPT,
        {
            "inline_data": {
                "mime_type": mime,
                "data": img_b64,
            }
        }
    ])
    return response.text.strip()


def clean_json_response(text):
    """Strip any accidental markdown fences from the model output."""
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$',          '', text, flags=re.MULTILINE)
    return text.strip()


def annotate_image(image_path, data):
    """Draws bounding boxes from the analysis onto a copy of the image."""
    try:
        img = Image.open(image_path).convert("RGBA")
        draw = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("cour.ttf", 22)
        except IOError:
            font = ImageFont.load_default()

        img_w, img_h = img.size

        def draw_annotation(item, color, prefix):
            # Check for the new key, but also accept 'box' or 'bounding_box' as a fallback
            poly_coords = item.get('bounding_polygon')
            if not poly_coords and 'box' in item: poly_coords = item.get('box')
            if not poly_coords and 'bounding_box' in item: poly_coords = item.get('bounding_box')

            if poly_coords and isinstance(poly_coords, list):
                # Handle both [[x,y],...] and [x1,y1,x2,y2] formats for robustness
                if len(poly_coords) == 4 and isinstance(poly_coords[0], list):
                    denormalized_points = [((p[0]/1000)*img_w, (p[1]/1000)*img_h) for p in poly_coords]
                elif len(poly_coords) == 4 and all(isinstance(p, (int, float)) for p in poly_coords):
                    x1 = (poly_coords[0] / 1000) * img_w
                    y1 = (poly_coords[1] / 1000) * img_h
                    x2 = (poly_coords[2] / 1000) * img_w
                    y2 = (poly_coords[3] / 1000) * img_h
                    denormalized_points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                else:
                    return # Invalid format

                # --- ANNOTATION LOGIC CHANGE ---
                # Instead of drawing the polygon, calculate its centroid to place a label.
                # This avoids visual clutter from inaccurate or overlapping rotated boxes.
                
                # Calculate the center of the polygon
                x_coords = [p[0] for p in denormalized_points]
                y_coords = [p[1] for p in denormalized_points]
                center_x = sum(x_coords) / len(x_coords)
                center_y = sum(y_coords) / len(y_coords)

                label = f"{prefix}: {item.get('label', 'Unknown')}"
                
                # Draw a background rectangle for the text for legibility
                text_bbox = draw.textbbox((center_x, center_y), label, font=font, anchor="mm")
                padded_bbox = [text_bbox[0] - 6, text_bbox[1] - 4, text_bbox[2] + 6, text_bbox[3] + 4]
                draw.rectangle(padded_bbox, fill=color)
                draw.text((center_x, center_y), label, fill="black", font=font, anchor="mm")

        for zone in data.get('zones', []):
            draw_annotation(zone, "#3399FF", "Zone")

        for path in data.get('paths', []):
            draw_annotation(path, "#FF5733", "Path")

        base, ext = os.path.splitext(image_path)
        annotated_path = f"{base}_annotated.jpg"

        img.convert("RGB").save(annotated_path, "JPEG", quality=90)
        print(f"[OK] Saved annotated image to {annotated_path}", file=sys.stderr)

    except Exception as e:
        print(f"[WARN] Could not annotate image: {e}", file=sys.stderr)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Analyse an architectural diagram with Gemini Vision and output spatial JSON."
    )
    parser.add_argument("path", help="Path to a diagram image or a directory of images.")
    parser.add_argument("--pretty", action="store_true", default=True,
                        help="Pretty-print the JSON output (default: True)")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not save the JSON output to a file.")
    args = parser.parse_args()

    target_path = args.path
    if not os.path.isabs(target_path):
        target_path = os.path.join(BASE_DIR, target_path)

    if not os.path.exists(target_path):
        print(f"[ERROR] Path not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    image_paths = []
    if os.path.isdir(target_path):
        print(f"[DIAGRAM AGENT] Processing directory: {target_path}", file=sys.stderr)
        for f in sorted(os.listdir(target_path)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) and '_annotated' not in f:
                image_paths.append(os.path.join(target_path, f))
    else:
        image_paths.append(target_path)

    if not image_paths:
        print("[INFO] No images found to process.", file=sys.stderr)
        return

    for image_path in image_paths:
        process_single_image(image_path, args)

def process_single_image(image_path, args):
    print(f"\n[DIAGRAM AGENT] Analysing: {os.path.basename(image_path)}", file=sys.stderr)
    try:
        raw = call_gemini(image_path)
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e}", file=sys.stderr)
        return
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[ERROR] Gemini call failed: {e}", file=sys.stderr)
        return

    # Parse and re-emit clean JSON
    cleaned = clean_json_response(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Could not parse model response as JSON: {e}", file=sys.stderr)
        print("[RAW RESPONSE]", file=sys.stderr)
        print(raw, file=sys.stderr)
        return

    indent = 2 if args.pretty else None
    output = json.dumps(data, indent=indent, ensure_ascii=False)
    print(output)

    if not args.no_save:
        base, _ = os.path.splitext(image_path)
        save_path = f"{base}_diagram.json"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[OK] Saved to {save_path}", file=sys.stderr)

    annotate_image(image_path, data)

    print(f"[DONE] Extracted {len(data.get('zones',[]))} zones, "
          f"{len(data.get('paths',[]))} paths, "
          f"{len(data.get('relationships',[]))} relationships.",
          file=sys.stderr)

if __name__ == "__main__":
    main()
