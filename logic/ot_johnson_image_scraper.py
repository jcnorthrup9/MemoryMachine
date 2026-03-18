import os
import requests
from time import sleep

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Setting up the new folder inside archive/reference_images/
SAVE_DIR = os.path.join(BASE_DIR, "archive", "reference_images", "ot_johnson")

def download_ot_johnson_images():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        print(f"📁 Created new directory: {SAVE_DIR}")

    queries = [
        "O.T. Johnson Building 356 S Broadway Los Angeles historic",
        "O.T. Johnson block Los Angeles architecture"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    downloaded = 0
    target_count = 10  # How many images we want to successfully grab

    print("🔎 Hunting for O.T. Johnson Building reference images...")

    try:
        with DDGS() as ddgs:
            for query in queries:
                print(f"   -> Searching: '{query}'")
                results = list(ddgs.images(query, max_results=15))
                
                for res in results:
                    if downloaded >= target_count:
                        break
                    img_url = res.get('image')
                    if img_url:
                        try:
                            response = requests.get(img_url, headers=headers, timeout=5)
                            if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                                file_path = os.path.join(SAVE_DIR, f"ot_johnson_ref_{downloaded+1}.jpg")
                                with open(file_path, 'wb') as f:
                                    f.write(response.content)
                                print(f"   ✅ Downloaded: {os.path.basename(file_path)}")
                                downloaded += 1
                                sleep(1) # Polite pause
                        except Exception:
                            pass # Skip broken links silently
                            
    except Exception as e:
        print(f"❌ Error during search: {e}")

    print(f"\n🎉 Process complete! Locked {downloaded} images into the archive.")

if __name__ == "__main__":
    download_ot_johnson_images()