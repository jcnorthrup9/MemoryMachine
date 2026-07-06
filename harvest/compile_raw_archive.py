import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (this file lives one level down)
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_FILE = os.path.join(DATA_DIR, "ParksRawDataArchive.md")

# Core mapping to ensure we catch specific anomalous files
SITES = {
    "Bottega Louie": ["bottega_louie_reviews.txt", "redacted_spatial_data.txt"],
    "Gardens By The Bay": ["GardensByTheBay.md", "GardensByTheBay_reviews.txt", "GardensByTheBay_spatial_data.txt"],
    "Nakagin Capsule Tower": ["nakagin.txt"],
    "O. T. Johnson Building": ["O. T. Johnson Building_reviews.txt", "O. T. Johnson Building_spatial_data.txt"],
    "Parc de la Villette": ["ParcdelaVillette.md", "ParcdelaVillette_reviews.txt", "ParcdelaVillette_spatial_data.txt"],
    "Pershing Square": ["urban_design_guidelines.md", "urban_design_guidelinesOLD.md", "PershingSquare_reviews.txt", "PershingSquare_spatial_data.txt"],
    "Schouwburgplein": ["Schouwburgplein.md", "Schouwburgplein_reviews.txt", "Schouwburgplein_spatial_data.txt"],
    "Tanner Springs Park": ["TannerSprings_reviews.txt", "TannerSprings_spatial_data.txt"],
    "Zaryadye Park": ["ZaryadyePark.md", "ZaryadyePark_reviews.txt", "ZaryadyePark_spatial_data.txt"]
}

# Dynamically find any other harvested sites (from harvest_all.py)
for f in os.listdir(DATA_DIR):
    if f.endswith("_spatial_data.txt"):
        site_name = f.replace("_spatial_data.txt", "")
        if site_name not in SITES and site_name.replace(" ", "") not in [k.replace(" ", "") for k in SITES.keys()]:
            SITES[site_name] = [f"{site_name}.md", f"{site_name}_reviews.txt", f"{site_name}_spatial_data.txt"]

print("📚 Compiling the Apophenic Raw Data Archive...")

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    out.write("# FORENSIC RAW DATA ARCHIVE // THE MEMORY MACHINE\n")
    out.write("**WARNING:** UNFILTERED DATA STREAM. NOISE-TO-SIGNAL RATIO EXCEEDS NOMINAL LIMITS. PROCEED WITH APOPHENIC INTENT.\n\n")
    out.write("---\n\n")

    for idx, site in enumerate(sorted(SITES.keys()), 1):
        out.write(f"## {idx}. {site.upper()}\n\n")
        
        files_to_check = SITES[site]
        found_data = False
        
        for file_name in files_to_check:
            # Check data dir, then base dir
            file_path = os.path.join(DATA_DIR, file_name)
            if not os.path.exists(file_path):
                file_path = os.path.join(BASE_DIR, file_name)
                
            if os.path.exists(file_path):
                found_data = True
                out.write(f"### 📄 SOURCE: `{file_name}`\n")
                out.write("```text\n")
                try:
                    with open(file_path, "r", encoding="utf-8") as rf:
                        content = rf.read()
                        out.write(content)
                        if not content.endswith("\n"):
                            out.write("\n")
                except Exception as e:
                    out.write(f"[ CORRUPT DATA SEGMENT: {e} ]\n")
                out.write("```\n\n")
                
        if not found_data:
            out.write("> `[ DATA FRAGMENT MISSING OR CORRUPTED ]`\n\n")
            
        out.write("---\n\n")

    # Add unclassified noise (e.g. raw JSON scrapes)
    out.write("## 10. UNCLASSIFIED NOISE & FRAGMENTS\n\n")
    hotels_json = os.path.join(BASE_DIR, "scrapfly-scrapers", "tripadvisor-scraper", "results", "hotels.json")
    if os.path.exists(hotels_json):
        out.write("### 📄 SOURCE: `hotels.json`\n```json\n")
        with open(hotels_json, "r", encoding="utf-8") as rf:
            out.write(rf.read())
        out.write("\n```\n\n")

print(f"✅ MASSIVE ARCHIVE COMPILED: {OUTPUT_FILE}")