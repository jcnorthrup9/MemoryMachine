from playwright.sync_api import sync_playwright
import os
from pathlib import Path

def export_zine():
    # Point this to your generated HTML file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, 'html', 'digitalPalimpsest.html')
    
    # Create URI for local file so Playwright can load it
    url = Path(html_path).as_uri()
    
    print(f"Targeting Zine: {url}")
    
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(args=["--allow-file-access-from-files"])
        page = browser.new_page()
        
        # Load the page and wait for all network requests (images) to finish
        print("Loading page and waiting for assets to download...")
        page.goto(url, wait_until="networkidle")
        
        # Let the Zine's natural 5-second boot/glitch sequence finish organically
        print("Letting the system boot sequence complete (6s)...")
        page.wait_for_timeout(6000)

        # Force the browser to wait until all image data is fully decoded visually
        print("Verifying all images are fully decoded...")
        page.evaluate("() => Promise.all(Array.from(document.images).map(img => { if (img.complete) return Promise.resolve(); return new Promise(resolve => { img.onload = img.onerror = resolve; }); }))")

        # Forcefully stabilize the zine by removing all glitch/decay classes instantly
        print("Stabilizing the system for print...")
        page.evaluate("""
            // Stop all animations
            if (typeof glitchInterval !== 'undefined') clearInterval(glitchInterval);
            if (typeof mildTimeout !== 'undefined') clearTimeout(mildTimeout);
            if (typeof severeTimeout !== 'undefined') clearTimeout(severeTimeout);
            if (typeof artifactInterval !== 'undefined') clearInterval(artifactInterval);
            
            // Remove CSS classes that distort the layout
            document.body.classList.remove('glitch-mode', 'degrading-mild', 'degrading-severe');
            
            // Remove any ghost fragments
            document.querySelectorAll('.ghost-fragment').forEach(el => el.remove());
        """)
        
        # Give the browser a brief moment to paint the stabilized DOM
        page.wait_for_timeout(1000) 
        
        output_pdf = os.path.join(base_dir, "MemoryMachine_Zine_Print.pdf")
        
        print(f"Exporting to PDF: {output_pdf}")
        # Export to PDF
        page.pdf(
            path=output_pdf,
            format="Letter",
            landscape=True,
            print_background=True, # Critical for your dark theme
            scale=1.0
        )
        browser.close()
        print("✅ PDF Exported Successfully!")

if __name__ == "__main__":
    export_zine()