"""
Rasterizes every precedent SVG (data/PershingMetabolizer/parkSVG/
PrecedentSVG/*.svg) to a small JPG thumbnail for the slide deck's page-04
rotating grid (html/final_deck.html, spread-5) -- browsers can render an
individual precedent SVG fine, but file sizes vary wildly (confirmed:
14KB to 19MB per file) and the deck ultimately needs 150 of them cycling
live, so pre-rasterized small thumbnails are the only practical option.

Adapted from harvest/generate_thumbnails.py (same Playwright screenshot
technique -- headless chromium, SVG wrapped in a minimal white-background
HTML doc, screenshot the rendered page) but pointed at the real precedent
directory (that script's SVG_DIR/THUMB_DIR are stale) and with a
size-aware render wait: a flat 500ms is enough for small SVGs but some
precedents (e.g. Prater.svg at 19MB) have tens of thousands of path
points and need longer for the browser to actually finish painting before
the screenshot fires.

Usage:
    .venv/Scripts/python.exe harvest/generate_precedent_thumbnails.py
    .venv/Scripts/python.exe harvest/generate_precedent_thumbnails.py --force
"""
import argparse
import os
import sys

from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG_DIR = os.path.join(REPO_ROOT, "data", "PershingMetabolizer", "parkSVG", "PrecedentSVG")
THUMB_DIR = os.path.join(REPO_ROOT, "static", "thumbnails", "precedent")


def _log(msg):
    enc = sys.stdout.encoding or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def _render_wait_ms(svg_path):
    """Small files render near-instantly; multi-MB SVGs (thousands of
    path points from dense OSM tag coverage) need more time for chromium
    to actually finish painting before the screenshot fires."""
    size = os.path.getsize(svg_path)
    if size < 1_000_000:
        return 500
    if size < 8_000_000:
        return 1200
    return 2000


def generate_thumbnails(force=False):
    if not os.path.isdir(SVG_DIR):
        _log(f"[ERROR] SVG directory not found: {SVG_DIR}")
        return

    os.makedirs(THUMB_DIR, exist_ok=True)
    svg_files = sorted(f for f in os.listdir(SVG_DIR) if f.lower().endswith(".svg"))
    if not svg_files:
        _log("[WARN] No SVGs found to process.")
        return

    _log(f"[THUMBNAILS] {len(svg_files)} SVG(s) found in {SVG_DIR}")

    ok, skipped, failed = 0, 0, 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 800, "height": 600})

        for i, filename in enumerate(svg_files, start=1):
            svg_path = os.path.join(SVG_DIR, filename)
            thumb_path = os.path.join(THUMB_DIR, filename[:-4] + ".jpg")

            if not force and os.path.exists(thumb_path):
                skipped += 1
                continue

            wait_ms = _render_wait_ms(svg_path)
            _log(f"[{i}/{len(svg_files)}] {filename} (wait {wait_ms}ms)...")
            try:
                with open(svg_path, "r", encoding="utf-8") as f:
                    svg_content = f.read()

                html_content = f"""<!DOCTYPE html>
<html><head><style>
body {{ margin:0; display:flex; justify-content:center; align-items:center; height:100vh; background:#ffffff; }}
svg {{ max-width:90%; max-height:90%; }}
</style></head><body>{svg_content}</body></html>"""

                page.set_content(html_content, timeout=60000)
                page.wait_for_timeout(wait_ms)
                page.screenshot(path=thumb_path, type="jpeg", quality=88)
                ok += 1
            except Exception as e:
                failed += 1
                _log(f"    [ERROR] {filename}: {e}")

        browser.close()

    _log(f"\n[DONE] {ok} rendered, {skipped} skipped (already existed), {failed} failed.")
    _log(f"        Thumbnails in: {THUMB_DIR}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-render even if a thumbnail already exists")
    args = parser.parse_args()
    generate_thumbnails(force=args.force)


if __name__ == "__main__":
    main()
