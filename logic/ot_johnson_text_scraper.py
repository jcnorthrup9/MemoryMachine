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
OUTPUT_PATH = os.path.join(DATA_DIR, 'ot_johnson_data.txt')

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def scrape_ot_johnson_info():
    # Using Wikipedia API as it is 100% free, doesn't block, and has rich historic architectural data
    queries = [
        "O. T. Johnson Building",
        "Broadway Theater District (Los Angeles)",
        "Architecture of Los Angeles",
        "Romanesque Revival architecture"
    ]
    
    extracted_text = []
    
    print("🔎 Fetching specific source: Grokipedia...")
    try:
        url = "https://grokipedia.com/page/o_t_johnson_building"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            text = clean_html(response.text)
            extracted_text.append(text)
            print("   ✅ Successfully fetched Grokipedia data.")
        else:
            print(f"   ❌ Failed to fetch. Status code: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error fetching specific URL: {e}")

    print("🔎 Booting up Wikipedia API scraper (Free & Reliable)...")
    
    for query in queries:
        print(f"   -> Searching Wikipedia for: '{query}'")
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
            response = requests.get(search_url, params=params)
            data = response.json()
            
            for item in data.get("query", {}).get("search", []):
                extracted_text.append(item["title"])
                extracted_text.append(clean_html(item["snippet"]))
                
                # Fetch the full summary extract for each search result
                page_title = item["title"]
                extract_params = {
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "titles": page_title,
                    "format": "json"
                }
                page_res = requests.get(search_url, params=extract_params).json()
                pages = page_res.get("query", {}).get("pages", {})
                for page_id, page_info in pages.items():
                    if "extract" in page_info:
                        extracted_text.append(page_info["extract"])
                        
            time.sleep(1) # Be polite to Wikipedia's servers
        except Exception as e:
            print(f"      ❌ Error querying Wikipedia: {e}")
            
    # Try DuckDuckGo as a secondary fallback, suppressing the warning
    try:
        import warnings
        warnings.filterwarnings("ignore")
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
            
        print("🔎 Attempting DuckDuckGo fallback...")
        with DDGS() as ddgs:
            for query in queries:
                results = ddgs.text(query + " Los Angeles historic interior", max_results=5)
                if results:
                    for res in results:
                        extracted_text.append(res.get('title', ''))
                        extracted_text.append(res.get('body', ''))
    except Exception:
        pass # Silently fail DDGS since Wikipedia already got us the data

    # Filter out empty strings and deduplicate
    final_text = []
    for t in extracted_text:
        if t and len(t.strip()) > 20 and t.strip() not in final_text:
            final_text.append(t.strip())

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(final_text))
        
    print(f"✅ Successfully compiled {len(final_text)} text snippets into {OUTPUT_PATH}")

if __name__ == "__main__":
    scrape_ot_johnson_info()