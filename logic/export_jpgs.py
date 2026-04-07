from playwright.sync_api import sync_playwright
import os
from pathlib import Path

def export_jpgs():
    # Point this to your generated HTML file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, 'html', 'digitalPalimpsest.html')
    url = Path(html_path).as_uri()
    
    # Create the output directory if it doesn't exist
    output_dir = r"C:\Users\jcnor\MemoryMachine\pdf\jpg"
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Targeting Zine: {url}")
    
    with sync_playwright() as p:
        print("Launching browser...")
        # Launch browser and set a widescreen viewport to capture the full spreads nicely
        browser = p.chromium.launch(args=["--allow-file-access-from-files"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        print("Loading page and waiting for assets to download...")
        page.goto(url, wait_until="networkidle")
        
        print("Letting the system boot sequence complete (6s)...")
        page.wait_for_timeout(6000)

        print("Stabilizing the system for JPG export...")
        # Stop the degradation timers and animations
        page.evaluate("""
            if (typeof glitchInterval !== 'undefined') clearInterval(glitchInterval);
            if (typeof mildTimeout !== 'undefined') clearTimeout(mildTimeout);
            if (typeof severeTimeout !== 'undefined') clearTimeout(severeTimeout);
            if (typeof artifactInterval !== 'undefined') clearInterval(artifactInterval);
            document.body.classList.remove('glitch-mode', 'degrading-mild', 'degrading-severe');
            document.querySelectorAll('.ghost-fragment').forEach(el => el.remove());
        """)
        
        # Force all images to be visible instantly (removes CSS fade-in delays) and hide navigation buttons
        page.add_style_tag(content="""
            * { transition: none !important; animation: none !important; }
            .watercolor-image { opacity: 1 !important; }
            .nav-controls, .stability-btn, #page-indicator { display: none !important; }
        """)
        
        zine_viewer = page.locator('.zine-viewer')
        total_spreads = 19
        
        for i in range(1, total_spreads + 1):
            print(f"Capturing Spread {i:02d}...")
            page.evaluate(f"showSpread({i}, true)") # Use the zine's built-in JS to switch pages
            page.wait_for_timeout(200) # Give the DOM a tiny fraction of a second to update
            
            output_file = os.path.join(output_dir, f"spread_{i:02d}.jpg")
            zine_viewer.screenshot(path=output_file, type="jpeg", quality=100)
            
        browser.close()
        print(f"✅ Successfully exported {total_spreads} JPGs to {output_dir}")

if __name__ == "__main__":
    export_jpgs()