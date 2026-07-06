import os
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (this file lives one level down)
SVG_DIR = os.path.join(BASE_DIR, 'data', 'ParkSVG')
THUMB_DIR = os.path.join(BASE_DIR, 'static', 'thumbnails')

# Ensure the output directory exists
os.makedirs(THUMB_DIR, exist_ok=True)

def generate_thumbnails():
    if not os.path.exists(SVG_DIR):
        print(f"❌ Error: SVG directory not found at {SVG_DIR}")
        return
        
    svg_files = [f for f in os.listdir(SVG_DIR) if f.lower().endswith('.svg')]
    
    if not svg_files:
        print("⚠️ No SVGs found to process.")
        return

    print(f"🔍 Found {len(svg_files)} SVGs. Starting generation...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 800x600 gives a standard 4:3 aspect ratio for the thumbnails
        page = browser.new_page(viewport={"width": 800, "height": 600})

        for filename in svg_files:
            svg_path = os.path.join(SVG_DIR, filename)
            thumb_filename = filename[:-4] + '.jpg'
            thumb_path = os.path.join(THUMB_DIR, thumb_filename)
            
            print(f" -> Creating {thumb_filename}...")
            
            with open(svg_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()

            # Wrap the SVG in an HTML document to enforce a white background
            # and center the diagram perfectly in the middle of the frame.
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ margin: 0; display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #ffffff; }}
                    svg {{ max-width: 90%; max-height: 90%; }}
                </style>
            </head>
            <body>{svg_content}</body>
            </html>
            """
            
            page.set_content(html_content)
            page.wait_for_timeout(500) # Give it half a second to ensure rendering settles
            page.screenshot(path=thumb_path, type="jpeg", quality=90)
            
        browser.close()
        print(f"✅ Success! Thumbnails saved to {THUMB_DIR}")

if __name__ == "__main__":
    generate_thumbnails()