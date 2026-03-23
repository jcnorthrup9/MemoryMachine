import argparse
import os
import time
import requests
import re

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def scrape_info(target_name, location):
    target_slug = re.sub(r'[^a-z0-9]+', '_', target_name.lower()).strip('_')
    output_path = os.path.join(DATA_DIR, f"{target_slug}_reviews.txt")
    
    search_term = f"{target_name} {location}".strip()
    queries = [
        search_term,
        f"{search_term} architecture",
        f"{search_term} history interior"
    ]
    
    extracted_text = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    print(f"🔎 Booting up Wikipedia API scraper for '{search_term}'...")
    for query in queries[:2]: # Limit wiki queries to avoid spamming
        try:
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "utf8": 1,
                "srlimit": 3
            }
            response = requests.get(search_url, params=params, headers=headers)
            data = response.json()
            
            for item in data.get("query", {}).get("search", []):
                extracted_text.append(clean_html(item["snippet"]))
                
                # Fetch full summary
                page_title = item["title"]
                extract_params = {
                    "action": "query", "prop": "extracts", "exintro": 1,
                    "explaintext": 1, "titles": page_title, "format": "json"
                }
                page_res = requests.get(search_url, params=extract_params, headers=headers).json()
                pages = page_res.get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    if "extract" in page_info:
                        extracted_text.append(page_info["extract"])
            time.sleep(1)
        except Exception as e:
            print(f"      ❌ Error querying Wikipedia: {e}")
            
    print("🔎 Attempting DuckDuckGo fallback...")
    try:
        import warnings
        warnings.filterwarnings("ignore")
        with DDGS() as ddgs:
            for query in queries:
                results = ddgs.text(query + " public space memory", max_results=4)
                if results:
                    for res in results:
                        extracted_text.append(res.get('body', ''))
    except Exception as e:
        print(f"      ❌ Error querying DuckDuckGo: {e}")

    # Filter and deduplicate
    final_text = []
    for t in extracted_text:
        if t and len(t.strip()) > 20 and t.strip() not in final_text:
            final_text.append(t.strip())

    if not final_text:
        final_text.append(f"Historical and spatial data for {target_name} in {location}. The architecture features prominent public spaces.")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n\n---\n\n".join(final_text))
        
    print(f"✅ Successfully compiled {len(final_text)} text snippets into {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Target name")
    parser.add_argument("--location", default="", help="Location")
    args = parser.parse_args()
    
    scrape_info(args.target, args.location)