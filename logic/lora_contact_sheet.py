"""
logic/lora_contact_sheet.py
----------------------------
Contact sheets for culling a harvested training set by eye (2026-07-28).

The harvester's perceptual-hash dedupe removes near-identical frames, but it
cannot tell whether the site is the SUBJECT of a photograph or merely its
backdrop -- a march photographed in Pershing Square teaches a model about
banners. That judgement is human, and it is the last quality gate before
training. This just makes it fast: one sheet per era, every image numbered
and labelled, so a pass that would mean opening 108 files becomes a look at
five pages.

Writes an `index.txt` beside the sheets mapping tile number -> filename, so
culling is: mark the numbers to drop, then delete those filenames.

Run:
    .venv/Scripts/python.exe logic/lora_contact_sheet.py
    .venv/Scripts/python.exe logic/lora_contact_sheet.py --dir data/lora_datasets/pershing/raw
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SET = os.path.join(BASE_DIR, "data", "lora_datasets", "pershing")

THUMB = 300          # px per tile
COLS = 6
LABEL_H = 26
PAD = 4


def build(dataset_dir, raw_dir=None, out_dir=None):
    from PIL import Image, ImageDraw, ImageFont

    raw_dir = raw_dir or os.path.join(dataset_dir, "raw")
    out_dir = out_dir or os.path.join(dataset_dir, "contact_sheets")
    os.makedirs(out_dir, exist_ok=True)

    manifest_path = os.path.join(dataset_dir, "manifest.json")
    by_file = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf8") as f:
            for r in json.load(f)["images"]:
                by_file[r["file"]] = r

    files = sorted(f for f in os.listdir(raw_dir)
                   if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")))
    if not files:
        raise SystemExit(f"no images in {raw_dir}")

    # Group by era so each sheet is internally comparable -- spotting an
    # outlier is much easier against its own period than against a mixed page.
    groups = {}
    for fn in files:
        era = (by_file.get(fn) or {}).get("era") or "undated"
        groups.setdefault(era, []).append(fn)

    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    index_lines = []
    n = 0
    for era in sorted(groups):
        group = groups[era]
        rows = (len(group) + COLS - 1) // COLS
        W = COLS * (THUMB + PAD) + PAD
        H = rows * (THUMB + LABEL_H + PAD) + PAD + 30
        sheet = Image.new("RGB", (W, H), (18, 18, 18))
        draw = ImageDraw.Draw(sheet)
        draw.text((PAD, 8), f"{era}   ({len(group)} images)", fill=(0, 255, 102), font=font)

        for i, fn in enumerate(group):
            n += 1
            index_lines.append(f"{n:>4}  {era:<14} {fn}")
            col, row = i % COLS, i // COLS
            x = PAD + col * (THUMB + PAD)
            y = 30 + PAD + row * (THUMB + LABEL_H + PAD)
            try:
                with Image.open(os.path.join(raw_dir, fn)) as im:
                    im = im.convert("RGB")
                    im.thumbnail((THUMB, THUMB), Image.LANCZOS)
                    sheet.paste(im, (x + (THUMB - im.width) // 2,
                                     y + (THUMB - im.height) // 2))
            except Exception:
                draw.rectangle([x, y, x + THUMB, y + THUMB], outline=(120, 40, 40))
            draw.text((x + 2, y + THUMB + 4), f"{n}", fill=(0, 255, 102), font=font)
            draw.text((x + 26, y + THUMB + 4), fn[:38], fill=(170, 170, 170), font=font)

        path = os.path.join(out_dir, f"sheet_{era}.jpg")
        sheet.save(path, quality=88)
        print(f"  {era:<14} {len(group):>3} images -> {path}")

    idx = os.path.join(out_dir, "index.txt")
    with open(idx, "w", encoding="utf8") as f:
        f.write("tile  era            filename\n")
        f.write("\n".join(index_lines) + "\n")
    print(f"\nindex -> {idx}")
    print(f"{n} images across {len(groups)} sheets")
    print("\nCull by deleting the files you don't want from raw/, then re-run\n"
          "`lora_harvest.py captions` to rebuild the training variants.")


def main():
    ap = argparse.ArgumentParser(description="Contact sheets for culling a training set.")
    ap.add_argument("--dataset", default=DEFAULT_SET)
    ap.add_argument("--dir", default=None, help="image dir (default: <dataset>/raw)")
    args = ap.parse_args()
    build(args.dataset, raw_dir=args.dir)


if __name__ == "__main__":
    main()
