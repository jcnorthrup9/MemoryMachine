import csv
import os
import requests
from time import sleep

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# Configuration Paths
CSV_PATH = r"D:\MemoryMachine\data\asset_manifest.csv"
SAVE_DIR = r"D:\MemoryMachine\archive\assets\thumbnails"


def download_image(urls, save_path, asset_name):
    # Spoofing a standard Chrome browser to bypass basic security blocks
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # Try up to 10 different image links before giving up
    for index, url in enumerate(urls):
        try:
            print(f"   -> Attempt {index + 1}: Downloading from {url[:50]}...")
            response = requests.get(url, headers=headers, timeout=5)

            # If the site gives us a valid image, save it and stop hunting
            if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                with open(save_path, 'wb') as f:
                    f.write(response.content)
                return True
        except Exception:
            pass  # Silently fail the bad link and immediately try the next one

    return False


def run_scrape():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Source_Type'].upper() == "SCRAPE":
                asset_name = row['Name']
                target_file = f"{asset_name}.jpg"
                save_path = os.path.join(SAVE_DIR, target_file)

                if os.path.exists(save_path):
                    print(f"✔ Skipping {asset_name} (Already in archive)")
                    continue

                # Smarter query formatting
                search_query = f"1980s vintage {asset_name.replace('_', ' ')}"
                if any(mat in asset_name for mat in ["carpet", "wood", "vinyl", "brass", "glow"]):
                    search_query = f"vintage {asset_name.replace('_', ' ')} texture seamless"

                print(f"\n🔎 Hunting for: {search_query}")

                try:
                    with DDGS() as ddgs:
                        # Grab 10 options instead of just 1
                        results = list(ddgs.images(search_query, max_results=10))
                        if results:
                            # Extract all the image URLs into a list
                            image_urls = [res['image'] for res in results]

                            # Send the list to our resilient downloader
                            if download_image(image_urls, save_path, asset_name):
                                print(f"✅ SUCCESS: Locked {target_file} into the archive.")
                            else:
                                print(f"❌ FAIL: All 10 links were dead or blocked for {asset_name}.")
                        else:
                            print(f"⚠ NOT FOUND: The search engine returned zero results.")

                except Exception as e:
                    if "Ratelimit" in str(e) or "403" in str(e):
                        print("🛑 RATELIMIT HIT: DuckDuckGo is suspicious. Sleeping for 15 seconds...")
                        sleep(15)
                    else:
                        print(f"❌ ERROR: {e}")

                # Polite pause to avoid triggering another ban
                sleep(3)


if __name__ == "__main__":
    run_scrape()