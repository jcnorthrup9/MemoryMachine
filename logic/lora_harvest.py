"""
logic/lora_harvest.py
----------------------
Builds a captioned LoRA training set from Pershing Square's own photographic
record -- the site across its successive erasures.

WHY THIS SITE, THIS WAY: Pershing Square has been demolished and rebuilt
roughly five times (see ERAS below). A LoRA trained on that record is not a
style filter; it is a prosthetic memory of a place whose memory was
repeatedly destroyed, and its failures are the site misremembering itself.
That is the thesis argument made into an artifact rather than illustrated by
one.

THREE OUTPUT VARIANTS, because the interesting result is a comparison, not a
single model:

  coherent/    one era, one medium. Captioned with era. Remembers correctly.
               The control.
  collapsed/   every era mixed. Captions have the era tag STRIPPED. The
               model cannot separate 1900 from 1994, so it averages them
               into one indeterminate frame.
  controlled/  the SAME images as collapsed/, captioned WITH era tags. The
               model can separate the periods and you can steer between
               them at inference.

collapsed/ and controlled/ differ ONLY in their caption sidecars -- same
pixels, same count, same seed-comparable training run. That makes the
experiment an ablation on metadata alone: it isolates the loss of *tags*
as the cause of temporal collapse, rather than leaving it confounded with a
change of imagery. This is the paper's own claim, tested -- "the metadata
has been misplaced, lost from the image, and the tags that once guided the
user to clarity no longer exist."

SOURCES AND WHY ONLY THESE:
Wikimedia Commons is the only large archive here with a documented public
API, per-file license metadata, and an explicit bot policy this can comply
with. The other collections that hold the best Pershing material -- LA
Public Library, USC Digital Library, Water and Power Associates -- have no
comparable public API, and hammering an institutional server to scrape a
cultural archive is both fragile and rude. Those are supported instead via
manual_drop/ (see build_captions): drop images in by hand, add a line to
its sidecar TSV, and they get captioned and merged like everything else.
Library of Congress has a real JSON API and is coded for below, but it
returned 403 from this environment -- it may work from yours.

PROVENANCE: every downloaded file gets a manifest.json record (source, page
URL, title, date, creator, license) and an ATTRIBUTION.md is generated.
Most Commons material is CC BY-SA, which *requires* attribution -- and a
thesis about declaring provenance should not launder the provenance of its
own training data.

Run:
    .venv/Scripts/python.exe logic/lora_harvest.py harvest --dry-run
    .venv/Scripts/python.exe logic/lora_harvest.py harvest
    .venv/Scripts/python.exe logic/lora_harvest.py captions
"""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, "data", "lora_datasets", "pershing")
RAW_DIR = os.path.join(DATASET_DIR, "raw")
MANUAL_DIR = os.path.join(DATASET_DIR, "manual_drop")
MANIFEST_PATH = os.path.join(DATASET_DIR, "manifest.json")

# Wikimedia's User-Agent policy requires a descriptive agent with contact
# info; a browser-spoofing UA is against their terms and gets rate-limited.
USER_AGENT = "MemoryMachine-thesis-research/1.0 (https://github.com/jcnorthrup9; jcnorthrup@gmail.com)"
# Commons asks for serial, unthreaded requests from tools like this. One
# second is well inside anything they object to.
REQUEST_DELAY_S = 1.0

TRIGGER = "pershingsq"

# The site's successive lives. Boundaries are the demolition/rebuild events,
# so an image's era is a fact about WHAT IT DEPICTS, not a decade bucket.
#
#   1866      Plaza dedicated; Victorian garden square (also "St Vincent's
#             Park", "Sixth Street Park", and -- crucially for searching
#             pre-1918 material -- "Central Park").
#   1918      Renamed for Gen. John J. Pershing.
#   1952      Gutted for a subterranean parking garage; the surface becomes
#             a deck over cars. This is the erasure the thesis excavates.
#   1994      Ricardo Legorreta's redesign; pink campanile, purple walls.
#   2017-     Agence Ter redesign era; Legorreta's scheme demolished.
ERAS = [
    {"id": "garden_square", "start": 1866, "end": 1917,
     "caption": "victorian garden square, mature trees, ornamental paths"},
    {"id": "pershing_lawn", "start": 1918, "end": 1951,
     "caption": "formal lawn square, palm trees, surrounded by masonry towers"},
    {"id": "garage_deck", "start": 1952, "end": 1993,
     "caption": "flat paved deck over subterranean garage, ramps, sparse planting"},
    {"id": "legorreta", "start": 1994, "end": 2016,
     "caption": "postmodern plaza, pink campanile, purple concrete walls"},
    {"id": "present", "start": 2017, "end": 2100,
     "caption": "contemporary plaza, demolition and reconstruction"},
]

# Commons categories that are genuinely about this site. Free-text search is
# deliberately NOT the spine: "Central Park Los Angeles 1900" returns 2400+
# hits dominated by the New York park, and relevance search returns
# near-duplicate bursts (12 frames from one 2013 shoot). A curated category
# is far higher precision.
COMMONS_CATEGORIES = [
    "Category:Pershing Square (Los Angeles)",
    "Category:Doughboy (Pershing Square, Los Angeles)",
    "Category:Spanish American War Memorial (Pershing Square, Los Angeles)",
    "Category:Monument to Beethoven (Pershing Square, Los Angeles)",
]

# Narrow supplement for on-site files that never got categorized.
#
# Searching the site's PRE-1918 NAMES was tried and abandoned: Commons
# free-text has no useful disambiguation for "Central Park", so the query
# returns Allentown PA's Central Park amusement park, plus scanned
# yearbooks and back issues of the Avicultural Magazine. Every variant
# tested ("Central Park" + "Los Angeles" + date range, incategory
# constraints) returned either 0 real hits or pure noise. The pre-1918 and
# 1918-1951 material simply is not on Commons in any findable quantity --
# it lives at LA Public Library, USC Digital Library, and Water and Power
# Associates, none of which expose an API. Use manual_drop/ for those eras;
# see build_captions()'s note. This is a real limit of this harvester, not
# an oversight to be fixed by a cleverer query.
COMMONS_SEARCHES = [
    'intitle:"Pershing Square" "Los Angeles"',
]


def _get(url, binary=False, retries=3):
    """GET with the required UA, polite delay, and bounded retry."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            time.sleep(REQUEST_DELAY_S)
            return data if binary else json.loads(data)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt == retries - 1:
                print(f"    ! giving up on {url[:80]}: {type(e).__name__} {e}")
                return None
            time.sleep(2 ** attempt)
    return None


def _commons_api(**params):
    params.setdefault("action", "query")
    params.setdefault("format", "json")
    return _get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))


def _extract_year(meta):
    """Best-effort depiction year from Commons extmetadata.

    Prefers DateTimeOriginal (when the photo was MADE) over upload date --
    for archival scans those differ by a century, and the depiction date is
    the only one that means anything here. Returns None rather than guessing:
    an unknown era must stay unknown, or the era tag becomes a fabrication,
    which is exactly what this project refuses to do elsewhere.
    """
    for field in ("DateTimeOriginal", "DateTime"):
        raw = (meta.get(field) or {}).get("value") or ""
        raw = re.sub(r"<[^>]+>", " ", raw)
        years = re.findall(r"\b(1[89]\d{2}|20[0-2]\d)\b", raw)
        if years:
            return int(years[0])
    return None


def _era_for_year(year):
    if year is None:
        return None
    for era in ERAS:
        if era["start"] <= year <= era["end"]:
            return era["id"]
    return None


def _ahash(path):
    """64-bit average hash for near-duplicate detection.

    Commons relevance search returns bursts of near-identical frames from a
    single shoot; those overfit a LoRA badly (the model memorizes one camera
    position). Exact-hash dedupe does not catch them because the files
    genuinely differ. Uses PIL, already a project dependency.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("L").resize((8, 8), Image.LANCZOS)
            px = list(im.getdata())
    except Exception:
        return None
    avg = sum(px) / len(px)
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def _hamming(a, b):
    return bin(a ^ b).count("1")


def harvest(dry_run=False, limit_per_source=200, near_dup_threshold=6):
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(MANUAL_DIR, exist_ok=True)

    candidates = {}

    print("== Commons categories ==")
    for cat in COMMONS_CATEGORIES:
        j = _commons_api(list="categorymembers", cmtitle=cat, cmtype="file", cmlimit=500)
        members = ((j or {}).get("query") or {}).get("categorymembers") or []
        print(f"  {cat}: {len(members)} files")
        for m in members:
            candidates[m["title"]] = cat

    print("== Commons supplemental searches ==")
    for q in COMMONS_SEARCHES:
        j = _commons_api(list="search", srsearch=q, srnamespace=6, srlimit=limit_per_source)
        hits = ((j or {}).get("query") or {}).get("search") or []
        new = [h["title"] for h in hits if h["title"] not in candidates]
        print(f"  {q[:52]!r}: {len(hits)} hits, {len(new)} new")
        for t in new:
            candidates[t] = f"search:{q}"

    print(f"\n{len(candidates)} unique candidate files")
    if dry_run:
        for t in sorted(candidates)[:40]:
            print("   ", t)
        print("   ... (--dry-run: nothing downloaded)")
        return

    titles = sorted(candidates)
    records, seen_sha, seen_ahash = [], set(), []

    for i in range(0, len(titles), 40):
        batch = titles[i:i + 40]
        j = _commons_api(titles="|".join(batch), prop="imageinfo",
                         iiprop="url|extmetadata|size|mime", iiurlwidth=1536)
        pages = ((j or {}).get("query") or {}).get("pages") or {}
        for page in pages.values():
            title = page.get("title", "")
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            if not info.get("url"):
                continue
            if (info.get("mime") or "").split("/")[-1] not in ("jpeg", "png", "webp", "tiff"):
                continue

            # Prefer the scaled render over the full original: archival TIFF
            # scans can be 100MB+, and training resolution is 1024px anyway.
            src = info.get("thumburl") or info.get("url")
            blob = _get(src, binary=True)
            if not blob:
                continue

            sha = hashlib.sha256(blob).hexdigest()
            if sha in seen_sha:
                continue
            seen_sha.add(sha)

            # Commons titles routinely exceed the 70-char truncation, and
            # several share a long common prefix ("Homeless people sleeping
            # in Pershing Square in Downtown Los Angeles DT..."), so the
            # truncated stem alone COLLIDES -- silently overwriting an
            # already-downloaded image and leaving the manifest describing
            # files that no longer exist (108 records vs 95 files on disk,
            # observed). A short content hash makes the stem unique without
            # making it unreadable.
            safe = re.sub(r"[^A-Za-z0-9]+", "_", title.replace("File:", "")).strip("_")[:60]
            ext = ".jpg" if "jpeg" in (info.get("mime") or "") else ".png"
            path = os.path.join(RAW_DIR, f"{safe}_{sha[:8]}{ext}")
            with open(path, "wb") as f:
                f.write(blob)

            ah = _ahash(path)
            if ah is not None:
                dup = next((h for h in seen_ahash if _hamming(h, ah) <= near_dup_threshold), None)
                if dup is not None:
                    os.remove(path)
                    continue
                seen_ahash.append(ah)

            year = _extract_year(meta)
            def mv(k):
                v = (meta.get(k) or {}).get("value") or ""
                return re.sub(r"<[^>]+>", " ", v).strip()

            records.append({
                "file": os.path.basename(path),
                "source": "wikimedia_commons",
                "source_title": title,
                "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}",
                "image_url": src,
                "found_via": candidates.get(title),
                "year": year,
                "era": _era_for_year(year),
                "creator": mv("Artist"),
                "credit": mv("Credit"),
                "license": mv("LicenseShortName"),
                "license_url": mv("LicenseUrl"),
                "description": mv("ImageDescription")[:400],
                "width": info.get("width"),
                "height": info.get("height"),
                "sha256": sha,
            })
            print(f"  + {os.path.basename(path)[:56]:<56} {year or '????'} {record_era(records[-1])}")

    os.makedirs(DATASET_DIR, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf8") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "trigger": TRIGGER, "eras": ERAS, "images": records}, f, indent=2)
    _write_attribution(records)

    print(f"\n{len(records)} images kept -> {RAW_DIR}")
    print(f"manifest -> {MANIFEST_PATH}")
    _print_era_histogram(records)


def record_era(rec):
    return rec.get("era") or "unknown-era"


def _print_era_histogram(records):
    print("\nera coverage:")
    for era in ERAS:
        n = sum(1 for r in records if r.get("era") == era["id"])
        bar = "#" * n
        print(f"  {era['id']:<14} {era['start']}-{era['end']:<5} {n:>3} {bar}")
    unknown = sum(1 for r in records if not r.get("era"))
    print(f"  {'(undated)':<14} {'':<10} {unknown:>3} {'#' * unknown}")


def _write_attribution(records):
    """CC BY-SA requires attribution. Also: a thesis about declaring
    provenance cannot quietly strip the provenance of its own inputs."""
    path = os.path.join(DATASET_DIR, "ATTRIBUTION.md")
    with open(path, "w", encoding="utf8") as f:
        f.write("# Training set attribution\n\n")
        f.write("Sources for the Pershing Square LoRA training set. Most Wikimedia\n")
        f.write("Commons material is CC BY-SA and requires attribution on reuse --\n")
        f.write("including in any published render produced by a model trained on it.\n\n")
        for r in sorted(records, key=lambda r: (r.get("year") or 0)):
            f.write(f"- **{r['file']}** — {r.get('year') or 'undated'} — "
                    f"{r.get('creator') or 'unknown creator'} — "
                    f"{r.get('license') or 'license unstated'} — <{r['page_url']}>\n")
    print(f"attribution -> {path}")


def _load_manual_drops():
    """Images added by hand from archives with no usable API (LAPL, USC,
    Water and Power Associates). Reads an optional sidecar TSV so those
    keep the same provenance discipline as the API-harvested ones:

        filename<TAB>year<TAB>creator<TAB>source_url

    Files present without a TSV row are still used, but land as undated --
    they'll train, they just can't carry an era tag.
    """
    if not os.path.isdir(MANUAL_DIR):
        return []
    meta = {}
    tsv = os.path.join(MANUAL_DIR, "sources.tsv")
    if os.path.exists(tsv):
        with open(tsv, encoding="utf8") as f:
            for line in f:
                if not line.strip() or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.rstrip("\n").split("\t")]
                if parts:
                    meta[parts[0]] = parts
    out = []
    for fn in sorted(os.listdir(MANUAL_DIR)):
        if not fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")):
            continue
        row = meta.get(fn, [fn])
        year = int(row[1]) if len(row) > 1 and row[1].isdigit() else None
        out.append({
            "file": fn, "source": "manual_drop", "_dir": MANUAL_DIR,
            "year": year, "era": _era_for_year(year),
            "creator": row[2] if len(row) > 2 else "",
            "page_url": row[3] if len(row) > 3 else "",
            "license": "see source", "description": "",
        })
    return out


def _caption_for(rec, include_era):
    """Caption what VARIES; never restate what is constant.

    The trigger token carries "this site". Describing the site in words
    would bind the concept to those words instead of to the token, which is
    the single most common way a LoRA fails to learn anything useful. So:
    trigger, then (optionally) era, then only what actually differs between
    images.
    """
    parts = [TRIGGER]
    if include_era and rec.get("era"):
        era = next(e for e in ERAS if e["id"] == rec["era"])
        parts.append(era["id"].replace("_", " "))
        parts.append(era["caption"])
    desc = (rec.get("description") or "").lower()
    if any(w in desc for w in ("aerial", "birds eye", "bird's eye", "from above")):
        parts.append("aerial view")
    if "postcard" in desc or "postcard" in rec.get("file", "").lower():
        parts.append("printed postcard, halftone")
    if any(w in desc for w in ("night", "evening")):
        parts.append("night")
    if any(w in desc for w in ("construction", "excavation", "demolition")):
        parts.append("construction site")
    return ", ".join(parts)


# Images where the site is incidental background to a crowd event. A
# march or protest photographed IN Pershing Square teaches a model about
# banners and crowds, not about the place -- and Commons is heavily
# weighted toward them (a single 2013 Syria-solidarity march accounts for
# a large share of this set's "legorreta" era). Excluded by default.
DRIFT_TERMS = ("protest", "march", "rally", "occupy", "syrian",
               "woman_s", "women_s", "protester", "protestor")


def _is_subject_drift(rec):
    hay = ((rec.get("description") or "") + " " + rec.get("file", "")).lower()
    return any(term in hay for term in DRIFT_TERMS)


def build_captions(coherent_era=None, max_per_era=None, keep_drift=False):
    if not os.path.exists(MANIFEST_PATH):
        raise SystemExit(f"no manifest at {MANIFEST_PATH} -- run `harvest` first")
    with open(MANIFEST_PATH, encoding="utf8") as f:
        manifest = json.load(f)
    records = [dict(r, _dir=RAW_DIR) for r in manifest["images"]] + _load_manual_drops()

    if not keep_drift:
        before = len(records)
        records = [r for r in records if not _is_subject_drift(r)]
        print(f"  dropped {before - len(records)} crowd-event images "
              f"(--keep-drift to retain)")

    dated = [r for r in records if r.get("era")]
    if not dated:
        raise SystemExit("no dated images -- cannot build era-based variants")

    counts = {}
    for r in dated:
        counts[r["era"]] = counts.get(r["era"], 0) + 1

    # Class balance. Left to itself this archive is ~85% post-1994, so a
    # "temporally collapsed" model would really just be a Legorreta model
    # with a few ghosts in it -- the collapse has to be BETWEEN eras to mean
    # anything. Capping each era to a common ceiling makes the mixture
    # actually temporal. Deliberately not upsampling the thin eras: printing
    # the same 1 garage-deck image 15 times would overfit it into a
    # memorized artifact, which is worse than under-representing it.
    # NOTE the cap applies to the MIXED variants only. `coherent` is a
    # single-era control whose whole job is to remember one period well, so
    # capping it just starves it -- with a fat era selected it would train on
    # 15 images while 65 sat unused. Balance is a property the mixed sets
    # need; the control needs volume.
    mixed = dated
    if max_per_era:
        capped, per = [], {}
        for r in sorted(dated, key=lambda r: (r["era"], r.get("year") or 0)):
            if per.get(r["era"], 0) < max_per_era:
                capped.append(r)
                per[r["era"]] = per.get(r["era"], 0) + 1
        dropped = len(dated) - len(capped)
        if dropped:
            print(f"  capped mixed sets to {max_per_era}/era, dropped {dropped} surplus")
        mixed = capped

    # The coherent control defaults to the best-represented era, but that is
    # usually the WRONG choice for this thesis -- the archive's fattest era
    # is the most recent one, while the argument is about the older
    # erasures. Override with --era.
    best_era = coherent_era or max(counts, key=counts.get)
    if best_era not in counts:
        raise SystemExit(f"era {best_era!r} has no images; available: {sorted(counts)}")

    variants = {
        # uncapped: the control wants every image of its era
        "coherent":   ([r for r in dated if r["era"] == best_era], True),
        "collapsed":  (mixed, False),
        "controlled": (mixed, True),
    }

    import shutil
    for name, (recs, include_era) in variants.items():
        out = os.path.join(DATASET_DIR, name)
        os.makedirs(out, exist_ok=True)
        for old in os.listdir(out):
            os.remove(os.path.join(out, old))
        for r in recs:
            src = os.path.join(r.get("_dir", RAW_DIR), r["file"])
            if not os.path.exists(src):
                continue
            dst = os.path.join(out, r["file"])
            shutil.copy2(src, dst)
            stem = os.path.splitext(dst)[0]
            with open(stem + ".txt", "w", encoding="utf8") as f:
                f.write(_caption_for(r, include_era) + "\n")
        n = len([x for x in os.listdir(out) if x.endswith(".txt")])
        note = f"(era={best_era})" if name == "coherent" else ""
        print(f"  {name:<11} {n:>3} images  era_tags={'yes' if include_era else 'NO '} {note}")

    print(f"\n-> {DATASET_DIR}")
    print("collapsed/ and controlled/ hold identical pixels and differ only in\n"
          "their .txt sidecars -- train both, same seed and steps, and the only\n"
          "variable between them is whether the model was given its tags.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[3])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest", help="download + dedupe + write manifest")
    h.add_argument("--dry-run", action="store_true", help="list candidates, download nothing")
    c = sub.add_parser("captions", help="build coherent/collapsed/controlled caption variants")
    c.add_argument("--era", default=None,
                   help=f"era for the coherent control ({', '.join(e['id'] for e in ERAS)})")
    c.add_argument("--max-per-era", type=int, default=15,
                   help="cap images per era so the mix is actually temporal (0 = uncapped)")
    c.add_argument("--keep-drift", action="store_true",
                   help="keep crowd-event images where the site is incidental")
    args = ap.parse_args()
    if args.cmd == "harvest":
        harvest(dry_run=args.dry_run)
    else:
        build_captions(coherent_era=args.era,
                       max_per_era=args.max_per_era or None,
                       keep_drift=args.keep_drift)


if __name__ == "__main__":
    main()
