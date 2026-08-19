"""
Batch-fetches SVG geometry + review text for the precedent-library
expansion: the 3 hand-built SVGs flagged replace=True in
data/precedent_park_list.py (force-refetched through the OSM pipeline for
visual-style consistency) plus the 98 new international parks (52 -> 150
total).

Rate limiting matters here: fetch_and_write_precedent()'s Overpass calls
have no built-in inter-call spacing, and empirically 8/16 back-to-back
calls failed at 1s spacing vs 8/8 succeeding at 25s (see
data/precedent_park_list.py's neighbors / project memory) -- this script
supplies that spacing itself, jittered the same way logic/batch_scraper.py
already proves out for its own DDG/Wikipedia pacing.

Resumable: skips a park's SVG/review step if the target file already
exists (unless the park is flagged replace=True, which always re-fetches
the SVG), and appends one JSON-lines record per attempt to
data/precedent_batch_progress.jsonl so a crash partway through doesn't
require starting over -- rerun the same command and already-done parks
just get skipped again.

Usage:
    .venv/Scripts/python.exe scripts/batch_fetch_precedents.py
    .venv/Scripts/python.exe scripts/batch_fetch_precedents.py --start-index 40 --limit 10
    .venv/Scripts/python.exe scripts/batch_fetch_precedents.py --skip-reviews
    .venv/Scripts/python.exe scripts/batch_fetch_precedents.py --only-failed
"""
import argparse
import json
import os
import random
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from precedent_park_list import ALL_PARKS, REPLACE_PARKS, NEW_PARKS, safe_name  # noqa: E402
from fetch_park_precedent import fetch_and_write_precedent, PRECEDENT_DIR  # noqa: E402
from logic.free_scraper import scrape_info, DATA_DIR  # noqa: E402

PROGRESS_PATH = os.path.join(REPO_ROOT, "data", "precedent_batch_progress.jsonl")

# The run's actual work list: replacements first (small, high-value for
# visual consistency), then the 98 new parks in registry order.
WORK_LIST = REPLACE_PARKS + NEW_PARKS


def _log(msg):
    """Same Windows-console-safe pattern as fetch_park_precedent.py/
    free_scraper.py's own _log() -- non-Latin park/city names are common
    in this list (e.g. Xi'an, Sao Paulo) and a bare print() has crashed on
    that before."""
    enc = sys.stdout.encoding or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


def _review_slug(name):
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_progress():
    if not os.path.exists(PROGRESS_PATH):
        return []
    records = []
    with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def _append_progress(record):
    os.makedirs(os.path.dirname(PROGRESS_PATH), exist_ok=True)
    with open(PROGRESS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _svg_exists(entry):
    path = os.path.join(PRECEDENT_DIR, safe_name(entry) + ".svg")
    return os.path.exists(path)


def _review_exists(entry):
    slug = _review_slug(entry["name"])
    path = os.path.join(DATA_DIR, f"{slug}_reviews.txt")
    return os.path.exists(path)


def run(work_list, skip_svg=False, skip_reviews=False):
    total = len(work_list)
    _log(f"\n[BATCH] {total} park(s) queued.\n")

    for i, entry in enumerate(work_list, start=1):
        name, city = entry["name"], entry["city"]
        force = bool(entry.get("replace"))
        record = {"name": name, "city": city, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

        # ── SVG geometry ──────────────────────────────────────────────
        if skip_svg:
            record["svg_status"] = "skipped_flag"
        elif not force and _svg_exists(entry):
            _log(f"[{i}/{total}] {name!r} ({city}) -- SVG already exists, skipping fetch.")
            record["svg_status"] = "skip"
        else:
            _log(f"[{i}/{total}] {name!r} ({city}) -- fetching SVG (force={force})...")
            try:
                result = fetch_and_write_precedent(city, name, force=force)
                record["svg_status"] = "ok" if result else "fail"
                if not result:
                    _log(f"    [WARN] fetch_and_write_precedent returned None for {name!r}")
            except Exception as e:
                record["svg_status"] = "fail"
                record["svg_error"] = str(e)
                _log(f"    [ERROR] SVG fetch raised for {name!r}: {e}")
            # Only pace Overpass calls when a fetch attempt actually happened.
            delay = random.uniform(22, 28)
            _log(f"    [WAIT] {delay:.1f}s (Overpass spacing)...")
            time.sleep(delay)

        # ── Review text ───────────────────────────────────────────────
        if skip_reviews:
            record["review_status"] = "skipped_flag"
        elif _review_exists(entry):
            _log(f"    review text already exists, skipping scrape.")
            record["review_status"] = "skip"
        else:
            try:
                scrape_info(name, city)
                record["review_status"] = "ok"
            except Exception as e:
                record["review_status"] = "fail"
                record["review_error"] = str(e)
                _log(f"    [ERROR] scrape_info raised for {name!r}: {e}")
            delay = random.uniform(3.0, 6.0)
            _log(f"    [WAIT] {delay:.1f}s (inter-park pacing)...")
            time.sleep(delay)

        _append_progress(record)

    _log(f"\n[DONE] {total} park(s) processed. Progress log: {PROGRESS_PATH}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-index", type=int, default=0, help="Start at this index into the work list")
    parser.add_argument("--limit", type=int, default=None, help="Process at most this many parks")
    parser.add_argument("--skip-svg", action="store_true", help="Skip SVG geometry fetch entirely")
    parser.add_argument("--skip-reviews", action="store_true", help="Skip review-text scraping entirely")
    parser.add_argument("--only-failed", action="store_true",
                         help="Only re-run parks whose most recent progress record shows a failure")
    args = parser.parse_args()

    work_list = WORK_LIST

    if args.only_failed:
        progress = _load_progress()
        latest = {}
        for rec in progress:
            latest[(rec["name"], rec["city"])] = rec
        failed_keys = {
            k for k, rec in latest.items()
            if rec.get("svg_status") == "fail" or rec.get("review_status") == "fail"
        }
        work_list = [e for e in WORK_LIST if (e["name"], e["city"]) in failed_keys]
        _log(f"[BATCH] --only-failed: {len(work_list)} park(s) had a prior failure.")

    if args.start_index:
        work_list = work_list[args.start_index:]
    if args.limit is not None:
        work_list = work_list[: args.limit]

    if not work_list:
        _log("[BATCH] Nothing to do.")
        return

    run(work_list, skip_svg=args.skip_svg, skip_reviews=args.skip_reviews)


if __name__ == "__main__":
    main()
