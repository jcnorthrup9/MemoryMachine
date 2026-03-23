import os
import time
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
OUTPUT_IMAGE = os.path.join(DATA_DIR, 'pershing_satellite.jpg')

def capture_satellite_map(lat=34.0483, lon=-118.2525, zoom=19.5):
    print(f"🛰️  Initiating satellite capture at {lat}, {lon}...")
    
    # Google Maps URL forced to Satellite view (!3m1!1e3)
    url = f"https://www.google.com/maps/@{lat},{lon},{zoom}z/data=!3m1!1e3"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Custom viewport to match the OpenCV aspect ratio we used earlier
        page = browser.new_page(viewport={"width": 1100, "height": 660})
        
        print("   -> Loading Google Maps...")
        # Using "load" instead of "networkidle" prevents timeouts on heavy maps
        page.goto(url, wait_until="load", timeout=60000)
        
        # Wait for the high-res 3D tiles to fully load
        print("   -> Waiting for satellite tiles to render (6s)...")
        time.sleep(6) 
        
        print("   -> Stripping UI elements for a clean capture...")
        # Inject CSS to hide all the Google Maps search boxes, buttons, and footers
        page.add_style_tag(content="""
            #omnibox-container, #titlecard, #watermark, #minimap, 
            .app-viewcard-strip, .scene-footer, .app-horizontal-widget-holder,
            .widget-settings-button, .gmnoprint, .vasqq, .wo101b { display: none !important; }
        """)
        time.sleep(1) # Give the DOM a second to hide everything
        
        os.makedirs(DATA_DIR, exist_ok=True)
        page.screenshot(path=OUTPUT_IMAGE, type="jpeg", quality=100)
        
        browser.close()
        print(f"✅ Clean satellite image captured successfully: {OUTPUT_IMAGE}")

if __name__ == "__main__":
    capture_satellite_map()