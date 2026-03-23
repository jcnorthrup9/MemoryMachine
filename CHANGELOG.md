# Memory Machine - Development Log

## [Latest Updates] - Architecture, Autonomous Discovery & High-Fidelity Generation

### 1. System Infrastructure & Orchestration
*   **Virtual Environment Initialization:** Successfully isolated the project dependencies using a local `venv` to avoid global package conflicts. Installed core libraries (`playwright`, `opencv-python`, `google-generativeai`, `duckduckgo-search`).
*   **Machine OS (`machine_os.py`):** Created the central orchestrator. It now uses Gemini NLP to interpret natural language directives, extract target locations, and automatically trigger the entire data-harvesting and mapping pipeline.
*   **Universal Parsers (`spatial_extractor.py`, `spatial_mapper.py`):** Upgraded scripts from hardcoded single-use files to accept command-line arguments. Expanded the architectural vocabulary to include landscape and park elements (e.g., `tree`, `path`, `water`, `pavilion`).

### 2. Autonomous Discovery & Scraping
*   **Free Data Scraper (`free_scraper.py`):** Built a 100% free data scraper utilizing the Wikipedia API and DuckDuckGo text search to bypass paid APIs. Implemented RegEx for safe filename generation.
*   **Autonomous Discovery Protocol (`autonomous_discovery.py`):** Engineered an AI-driven agent capable of searching the web for highly rated public spaces based on open-ended queries, parsing the results, and automatically feeding the best locations into the Memory Machine.

### 3. Computer Vision & Satellite Mapping
*   **Satellite Drone Scraper (`satellite_scraper.py`):** Automated Google Maps satellite captures using headless Chromium (Playwright). The script flies to specific GPS coordinates, injects CSS to hide the UI, and saves a clean aerial photograph.
*   **OpenCV Site Mapper (`opencv_site_mapper.py`):** Implemented an AI computer vision script to scan satellite images, detect green vegetation pixels, calculate real-world Rhino coordinates, and export them to `extracted_trees.csv`. It also outputs an analyzed visual markup image (`pershing_satellite_analyzed.jpg`) for the presentation deck.

### 4. High-Fidelity Rhino Generation
*   **Pershing Square Base (`site_reconstruction.py`):** Upgraded the base site from simple boxes to a high-fidelity architectural proxy.
    *   Added the 3-story subterranean parking garage.
    *   Used Boolean Difference to carve out the entry ramps on Olive and Hill streets.
    *   Carved the iconic cutout in the purple Campanile tower and the arches in the yellow aqueduct wall.
    *   Added the recessed water basin, stepped amphitheater, yellow transit pavilion, and geometric view-framing walls.
    *   Integrated the OpenCV CSV data to automatically plant trees in their exact real-world locations.
*   **Intervention Engine (`intervention_engine.py`):** Transitioned from manual placement to an Auto-Deploy system. 
    *   The script now automatically imports and builds the Pershing Square base first.
    *   Auto-scatters parsed memory assets dynamically across the site.
    *   Upgraded procedural geometry fallbacks (e.g., multi-sphere tree canopies, tiered fountains, columned pavilions, and rotating stepped monuments).
    *   Checks the `archive/assets/models/` folder to automatically import high-fidelity `.obj` or `.3dm` files if they match the asset name.
*   **Universal Builder (`rhino_universal.py`):** Created a standalone Rhino script capable of reading *any* generated CSV massing blueprint and procedurally building the space with organic scattering and dynamic geometries.

### 5. Quality of Life & Workflow Improvements
*   **Automated Archiving:** Added Rhino Python commands (`_-ViewCaptureToFile`) to automatically take high-resolution 1920x1080 screenshots of the 3D viewport after scripts finish running, saving them directly to `archive/render_output/`.
*   **Label Management:** Standardized all generated text dots across all scripts to be placed on a uniform `06_LABELS` layer, allowing them to be instantly toggled off for clean rendering.