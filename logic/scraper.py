import argparse, os
import re
import urllib.parse
from scrapfly import ScrapflyClient, ScrapeConfig
from parsel import Selector

API_KEY = "scp-live-1de5601897a54e3b8eb6efde0106d282"
client = ScrapflyClient(key=API_KEY)


def scrape_yelp_search(search_term, location):
    print(f"--- Scraping Yelp: {search_term} in {location} ---")
    target_url = f"https://www.yelp.com/search?find_desc={search_term}&find_loc={location}"
    config = ScrapeConfig(
        url=target_url,
        asp=True,
        country="US",
        render_js=False
    )
    try:
        result = client.resilient_scrape(config)
        if result.success:
            print("SUCCESS!")
            with open("last_scrape_result.html", "w", encoding="utf-8") as f:
                f.write(result.content)
            return True
        else:
            print("Failed: Target site responded with non-200 status.")
            return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def scrape_business_reviews(business_name, location, total_to_scrape=1000):
    """
    Scrapes all reviews for a specific business on Yelp, up to a specified total.
    """
    print(f"--- Starting review scrape for '{business_name}' in '{location}' ---")

    # 1. Construct the business URL directly to bypass the slow and protected search page.
    # This is a more reliable method than trying to parse search results.
    name_slug = re.sub(r'[^a-z0-9\s-]', '', business_name.lower()).replace(' ', '-')
    
    # Take the last part of the location string (e.g., "Los Angeles" from "DTLA, Los Angeles")
    # and create a clean slug from it.
    city_slug_raw = location.split(',')[-1].strip()
    city_slug = re.sub(r'[^a-z0-9\s-]', '', city_slug_raw.lower()).replace(' ', '-')

    # Yelp URLs often follow this pattern. Scrapfly will automatically follow any redirects
    # (e.g., from /bottega-louie-los-angeles to /bottega-louie-los-angeles-3)
    business_url = f"https://www.yelp.com/biz/{name_slug}-{city_slug}"
    print(f"Constructed business URL: {business_url}")
    # The first scrape will now be for the first page of reviews, skipping the search step.

    reviews = []
    page_start = 0
    # Yelp shows 10 reviews per page. We'll paginate until we hit our target or run out of reviews.
    while len(reviews) < total_to_scrape:
        # Yelp paginates with the `start` parameter (e.g., start=10 for page 2)
        paginated_url = f"{business_url}?start={page_start}"
        print(f"   -> Scraping reviews from page {page_start//10 + 1}... ({len(reviews)}/{total_to_scrape} collected)")

        page_config = ScrapeConfig(
            url=paginated_url, 
            asp=True, 
            country="US",
            render_js=False
        )
        page_result = client.resilient_scrape(page_config)
        if not page_result.success:
            # Retrieve explicit error details from Scrapfly to diagnose the block
            status = getattr(page_result, 'upstream_status_code', 'N/A')
            try:
                err = page_result.error_message
            except KeyError:
                # SDK bug workaround: fall back to raw dictionary if 'message' is missing
                err = str(getattr(page_result, 'result', 'Unknown ASP block or timeout'))
            print(f"   ❌ Failed to scrape page {page_start//10 + 1}. Status: {status} | Error: {err}")
            break

        page_selector = Selector(text=page_result.content)
        # This CSS selector targets the review text. It is subject to change if Yelp redesigns their site.
        page_reviews_text = page_selector.css('p[class*="comment"] span[lang="en"]::text').getall()

        if not page_reviews_text:
            print("   ✅ No more reviews found. Concluding scrape.")
            break

        for review_text in page_reviews_text:
            # Per your request, remove the business name (case-insensitive)
            cleaned_text = re.sub(business_name, "[BUSINESS NAME]", review_text, flags=re.IGNORECASE)
            reviews.append(cleaned_text)
        
        page_start += 10 # Go to the next page

    print(f"\n--- Collected {len(reviews)} reviews in total. ---")
    output_filename = f"{business_name.replace(' ', '_').lower()}_reviews.txt"
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data', output_filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(reviews))
    print(f"✅ Successfully saved reviews to {output_path}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", help="Search term for a general Yelp search (e.g., 'Cafe').")
    parser.add_argument("--scrape-reviews-for", help="The name of the business to scrape reviews for.")
    parser.add_argument("--location", required=True, help="Search location (e.g., 'DTLA, Los Angeles').")
    parser.add_argument("--total", type=int, default=1000, help="Total number of reviews to scrape.")
    args = parser.parse_args()

    if args.scrape_reviews_for:
        if not scrape_business_reviews(args.scrape_reviews_for, args.location, args.total):
            exit(1)
    elif args.search:
        if not scrape_yelp_search(args.search, args.location):
            exit(1)
    else:
        parser.error("You must specify either --search or --scrape-reviews-for.")