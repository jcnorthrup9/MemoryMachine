import asyncio
import json
import re
from pathlib import Path
import yelp

output = Path(__file__).parent / "results"
output.mkdir(exist_ok=True)

async def run():
    # We disable cache to ensure we get fresh data
    yelp.BASE_CONFIG["cache"] = False

    target_url = "https://www.yelp.com/biz/bottega-louie-los-angeles"
    print(f"Scraping reviews for {target_url}...")
    
    # Hardcode the Business ID here to skip the highly-blocked initial page load.
    # You can find any restaurant's ID by going to their Yelp page in your browser, 
    # right-clicking -> View Page Source -> search for "yelp-biz-id".
    # Bottega Louie's ID is "laXVRoQsCaqu5x4nJ4m9iw"
    biz_id = "laXVRoQsCaqu5x4nJ4m9iw"
    
    # Pass the business_id directly to the scraper
    reviews_data = await yelp.scrape_reviews(target_url, max_reviews=500, business_id=biz_id)
    
    print("Anonymizing reviews...")
    # Regex to catch variations of the Bottega Louie name, ignoring case
    redact_pattern = re.compile(r'(Bottega Louie|Bottega|Louie)', re.IGNORECASE)
    
    for item in reviews_data:
        # Redact the business name from the actual review text
        if "text" in item and "full" in item["text"]:
            item["text"]["full"] = redact_pattern.sub("[REDACTED]", item["text"]["full"])
        
        # Strip the business metadata just to be completely anonymous
        if "business" in item:
            item["business"]["name"] = "[REDACTED]"
            item["business"]["alias"] = "[REDACTED]"
            item["business"]["encid"] = "[REDACTED]"

    output_file = output.joinpath("anonymized_bottega_louie_reviews.json")
    
    # Load existing reviews if the file already exists
    existing_reviews = []
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as file:
            try:
                existing_reviews = json.load(file)
            except json.JSONDecodeError:
                existing_reviews = []
                
    # Create a set of existing review IDs to prevent duplicates
    existing_ids = {r.get("encid") for r in existing_reviews if r.get("encid")}
    
    new_reviews_added = 0
    for item in reviews_data:
        if item.get("encid") not in existing_ids:
            existing_reviews.append(item)
            existing_ids.add(item.get("encid"))
            new_reviews_added += 1

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(existing_reviews, file, indent=2, ensure_ascii=False)
        
    print(f"Added {new_reviews_added} new reviews. Total reviews in file: {len(existing_reviews)}")

if __name__ == "__main__":
    asyncio.run(run())