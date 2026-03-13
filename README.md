# Memory Machine // Palimpsest

**The Machine That Forgets**

A computational design project exploring the intersection of human memory decay (dementia), artificial intelligence (LoRAs/Hallucinations), and architectural reconstruction. This repository contains the logic for procedurally reconstructing memories, harvesting digital artifacts, and compiling the forensic findings into a digital zine.

## Project Structure

### `logic/`
The core computational engine.
*   **`zine_compiler.py`**: Aggregates text data, system logic, and asset references to generate the interactive HTML zine (`digitalPalimpsest.html`).
*   **`generate_trailer_88.py`**: A Rhino Python script that procedurally builds the "1988 Trailer" site. It generates the 100x100 grid, the glitched trailer mesh, and narrative anomalies based on lore.
*   **`scraper_auto.py`**: Automated tool using DuckDuckGo to hunt for vintage textures (e.g., "burnt orange carpet") and assets based on the asset manifest.
*   **`import_assets.py`**: Utility for importing, scaling, and placing `.obj` assets into the Rhino environment based on sensory data.

### `data/`
The memory substrate.
*   Contains raw narrative logs (`1988_trailer_raw.txt`), parsed vignettes, thesis abstracts, and JSON logic definitions.

### `html/`
The visualization layer.
*   **`digitalPalimpsest.html`**: The interactive, glitch-aesthetic viewer that presents the project as a forensic dossier.

### `archive/`
*   Stores scraped thumbnails and rendered outputs from Rhino.

## Usage

### 1. Compiling the Zine
To regenerate the digital viewer after modifying text files in `data/`:
```bash
python logic/zine_compiler.py
```
This will update `html/digitalPalimpsest.html`.

### 2. Rhino Reconstruction
The procedural generation scripts are designed for **Rhino 8**.
1.  Open Rhino 8.
2.  Open the Python Editor (`EditPythonScript` or `ScriptEditor`).
3.  Run `logic/generate_trailer_88.py` to generate the environment foundation and trailer geometry.

### 3. Asset Harvesting
To populate the texture library:
```bash
python logic/scraper_auto.py
```
*Dependencies: `duckduckgo_search`, `requests`*

## Concept
> "Memory is not a static archive, but an unstable process of encoding, retrieval, and decay."

The project treats memory as a dataset subject to "bit rot" and "hallucination." The reconstruction is not meant to be perfect; it intentionally includes artifacts, glitches, and gaps, mirroring the failure modes of both biological memory (dementia) and synthetic memory (AI hallucination).