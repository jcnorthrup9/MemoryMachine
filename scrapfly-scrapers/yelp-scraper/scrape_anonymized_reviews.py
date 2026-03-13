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

    target_url = "https://www.yelp.com/biz/chimney-coffee-house-los-angeles"
    print(f"Scraping reviews for {target_url}...")
    
    # Scrape the reviews using the existing yelp module
    # 50 is a good starting point, adjust max_reviews as needed
    reviews_data = await yelp.scrape_reviews(target_url, max_reviews=50)
    
    print("Anonymizing reviews...")
    # Regex to catch variations of the name, ignoring case
    redact_pattern = re.compile(r'(Chimney Coffee House|Chimney Coffee|Chimney)', re.IGNORECASE)
    
    for item in reviews_data:
        # Redact the business name from the actual review text
        if "text" in item and "full" in item["text"]:
            item["text"]["full"] = redact_pattern.sub("[REDACTED]", item["text"]["full"])
        
        # Strip the business metadata just to be completely anonymous
        if "business" in item:
            item["business"]["name"] = "[REDACTED]"
            item["business"]["alias"] = "[REDACTED]"
            item["business"]["encid"] = "[REDACTED]"

    output_file = output.joinpath("anonymized_chimney_reviews.json")
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(reviews_data, file, indent=2, ensure_ascii=False)
        
    print(f"Saved {len(reviews_data)} anonymized reviews to {output_file}")

if __name__ == "__main__":
    asyncio.run(run())