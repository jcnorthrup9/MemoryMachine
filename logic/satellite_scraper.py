import os
import time
from playwright.sync_api import sync_playwright
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def capture_satellite_map(lat, lon, zoom, output_path):
    """Captures a clean satellite image from Google Maps for the given coordinates."""
    print(f"🛰️  Initiating satellite capture at {lat}, {lon} for {os.path.basename(output_path)}...")
    
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
        
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        page.screenshot(path=output_path, type="jpeg", quality=95)
        
        browser.close()
        print(f"✅ Clean satellite image captured successfully: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capture a satellite map from Google Maps.")
    parser.add_argument("--lat", type=float, default=34.0483, help="Latitude for the map center.")
    parser.add_argument("--lon", type=float, default=-118.2525, help="Longitude for the map center.")
    parser.add_argument("--zoom", type=float, default=19.5, help="Zoom level for the map.")
    parser.add_argument("--output", default=os.path.join(DATA_DIR, 'pershing_satellite.jpg'),
                        help="Full path for the output JPG image.")
    
    args = parser.parse_args()
    
    capture_satellite_map(
        lat=args.lat,
        lon=args.lon,
        zoom=args.zoom,
        output_path=args.output
    )