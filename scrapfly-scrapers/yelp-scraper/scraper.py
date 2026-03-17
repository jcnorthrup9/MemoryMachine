import argparse
import os
from urllib.parse import quote_plus
from scrapfly import ScrapflyClient, ScrapeConfig

# --- AUTHENTICATION ---
API_KEY = "scp-live-1de5601897a54e3b8eb6efde0106d282"
client = ScrapflyClient(key=API_KEY)

def scrape_yelp_search(search_term, location):
    print(f"--- Scraping Yelp: '{search_term}' in '{location}' ---")
    
    target_url = f"https://www.yelp.com/search?find_desc={search_term}&find_loc={location}"
    encoded_search = quote_plus(search_term)
    encoded_location = quote_plus(location)
    target_url = f"https://www.yelp.com/search?find_desc={encoded_search}&find_loc={encoded_location}"
    
    # ADVANCED CONFIG TO BYPASS 403/422
    config = ScrapeConfig(
        url=target_url,
        asp=True,                      # Anti-Scraping Protection bypass
        country="US",
        proxy_pool="public_residential_pool", # Uses "home" IPs instead of data centers
        render_js=True,                # Executes JavaScript to look like a real browser
        wait_for_selector="div.container__09f24__m9SfG" # Waits for content to load before timing out
    )
    
    try:
        result = client.scrape(config)
        
        if result.response.status_code == 200:
            print(f"✅ SUCCESS! Status: 200")
            output_file = 'last_scrape_result.html'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result.content)
            print(f"📂 Saved data to: {output_file}")
        else:
            print(f"⚠️  Scrape finished but returned Status: {result.response.status_code}")
            
    except Exception as e:
        # Re-raise the exception so random_site.py knows it failed
        raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", required=True)
    parser.add_argument("--location", required=True)
    args = parser.parse_args()
    scrape_yelp_search(args.search, args.location)