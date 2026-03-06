import csv
import os

CSV_PATH = r"D:\MemoryMachine\data\asset_manifest.csv"
IMG_DIR = r"D:\MemoryMachine\archive\assets\thumbnails"

def check_sync():
    with open(CSV_PATH, mode='r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            img_file = os.path.basename(row['Thumbnail_Path'])
            full_path = os.path.join(IMG_DIR, img_file)
            if os.path.exists(full_path):
                print(f"✅ FOUND: {row['Name']}")
            else:
                print(f"❌ MISSING: {row['Name']} (Expected at {full_path})")

if __name__ == "__main__":
    check_sync()