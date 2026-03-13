import argparse
import os
from urllib.parse import quote_plus # This fixes the space/comma issue
from scrapfly import ScrapflyClient, ScrapeConfig

# 1. HARDCODE THE KEY - No middleman, no environment variables
API_KEY = "scp-live-1de5601897a54e3b8eb6efde0106d282"
client = ScrapflyClient(key=API_KEY)

def scrape_yelp_search(search_term, location):
    print(f"--- Scraping Yelp: '{search_term}' in '{location}' ---")
    
    # VS CODE FIX: Properly encode spaces and commas
    encoded_search = quote_plus(search_term)
    encoded_location = quote_plus(location)
    
    # This creates a URL like: ...find_loc=Little+Tokyo%2C+Los+Angeles%2C+CA
    target_url = f"https://www.yelp.com/search?find_desc={encoded_search}&find_loc={encoded_location}"
    print(f"Target URL: {target_url}")
    
    config = ScrapeConfig(
        url=target_url,
        asp=True,
        country="US"
    )
    
    try:
        # We pass the key explicitly AGAIN here to force it past school firewalls
        result = client.scrape(config)
        print(f"✅ SUCCESS! Status: {result.response.status_code}")
        
        with open('last_scrape_result.html', 'w', encoding='utf-8') as f:
            f.write(result.content)
            
    except Exception as e:
        print(f"❌ Error during scrape: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", required=True)
    parser.add_argument("--location", required=True)
    args = parser.parse_args()
    scrape_yelp_search(args.search, args.location)