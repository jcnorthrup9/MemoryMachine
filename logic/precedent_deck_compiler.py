import os
import base64
import webbrowser
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, 'html', 'precedent_deck.html')

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Precedent Research Deck</title>
    <style>
        body { font-family: sans-serif; background-color: #111; color: #eee; margin: 0; padding: 40px; }
        h1 { text-align: center; color: #f9a825; border-bottom: 1px solid #444; padding-bottom: 20px; margin-bottom: 40px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 40px; }
        .card { background-color: #1a1a1a; border: 1px solid #333; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; }
        .card-image { width: 100%; height: 250px; object-fit: cover; background-color: #222; }
        .card-content { padding: 20px; }
        .card h2 { margin-top: 0; color: #f9a825; }
        .card p { color: #ccc; line-height: 1.6; }
    </style>
</head>
<body>
    <h1>Precedent Study: Successful Public Spaces</h1>
    <div class="grid">
        {{CARDS_HTML}}
    </div>
</body>
</html>
"""

def get_image_b64(rel_path):
    """Finds and encodes an image, trying common extensions."""
    img_path_base = os.path.join(BASE_DIR, *rel_path.split('/'))
    for ext in ['.jpg', '.png', '.webp']:
        img_path = img_path_base + ext
        if os.path.exists(img_path):
            with open(img_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
                mime = f"image/{ext[1:]}"
                return f"data:{mime};base64,{encoded}"
    print(f"[-] Image not found for: {rel_path}")
    return ""

def create_precedent_card(precedent):
    """Generates HTML for a single precedent card."""
    img_src = get_image_b64(precedent['image_path'])
    return f"""
    <div class="card">
        <img src="{img_src}" alt="{precedent['title']}" class="card-image">
        <div class="card-content">
            <h2>{precedent['title']}</h2>
            <p><b>Site:</b> {precedent['site']}</p>
            <p>{precedent['blurb']}</p>
        </div>
    </div>
    """

def compile_precedent_deck():
    """Main function to build the HTML deck."""
    print("\n--- Compiling Precedent Research Deck ---")

    # This data is based on the automated research pass.
    # Image paths are conceptual and assume they've been scraped into the archive.
    precedents = [
        {
            "title": "Kinetic Masts",
            "site": "Schouwburgplein, Rotterdam",
            "image_path": "archive/reference_images/precedents/schouwburgplein",
            "blurb": "A vast, elevated public square made of epoxy-coated metal panels. The space is defined by four towering, crane-like hydraulic lighting masts that can be repositioned by the public, creating an interactive and ever-changing urban stage."
        },
        {
            "title": "Wadable Pool",
            "site": "Grand Park, Los Angeles",
            "image_path": "archive/reference_images/precedents/grand_park",
            "blurb": "A large, shallow splash pad with a distinctive bright pink membrane floor. The fountain provides a playful, cooling, and highly social focal point that invites public interaction and contrasts with the surrounding hardscape."
        },
        {
            "title": "Reclaimed Art Wall",
            "site": "Tanner Springs Park, Portland",
            "image_path": "archive/reference_images/precedents/tanner_springs",
            "blurb": "An art wall constructed from 368 reclaimed railway tracks, set vertically to create a textured, weaving boundary. The rails contain inlaid panels of fused glass that depict native wetland insects, blending industrial history with natural ecology."
        },
        {
            "title": "Supertree Grove",
            "site": "Gardens by the Bay, Singapore",
            "image_path": "archive/reference_images/precedents/supertree",
            "blurb": "Iconic tree-like vertical gardens ranging from 25 to 50 meters tall. These structures consist of a concrete core, a steel trunk, and a planting canopy, serving as environmental engines for the park's conservatories."
        },
        {
            "title": "Graphic Ground Plane",
            "site": "Superkilen, Copenhagen",
            "image_path": "archive/reference_images/precedents/superkilen",
            "blurb": "An urban park known for its extreme graphic identity. The 'Black Market' section uses bold, undulating black and white stripes painted on the asphalt to create a surreal, visually dynamic surface that encourages movement and play."
        }
    ]

    cards_html = "".join([create_precedent_card(p) for p in precedents])
    final_html = HTML_TEMPLATE.replace("{{CARDS_HTML}}", cards_html)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_html)

    print(f"✅ Precedent Deck Compiled: {OUTPUT_FILE}")
    webbrowser.open(f"file://{os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    compile_precedent_deck()

```

To run it, simply execute: `python logic/precedent_deck_compiler.py`. This will generate and open `html/precedent_deck.html`.

### 2. Procedural 3D Geometry

Next, I've created `rhino_precedent_generator.py`. This script translates the core concepts from the research into basic, parametric 3D forms inside Rhino. This is the key to turning abstract ideas into physical geometry that can be cross-pollinated into the Pershing Square site.

```diff