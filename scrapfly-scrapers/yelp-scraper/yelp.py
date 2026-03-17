"""
This is an example web scraper for yelp.com.

To run this scraper set env variable $SCRAPFLY_KEY with your scrapfly API key:
$ export $SCRAPFLY_KEY="your key from https://scrapfly.io/dashboard"
"""

import os
import uuid
import json
import math
import base64
import re
import jmespath
from typing import Dict, List, TypedDict
from urllib.parse import urlencode
from loguru import logger as log
from scrapfly import ScrapeConfig, ScrapflyClient, ScrapeApiResponse

SCRAPFLY = ScrapflyClient(key="scp-live-1de5601897a54e3b8eb6efde0106d282")

BASE_CONFIG = {
    # bypass yelp.com web scraping blocking
    "asp": True,
    # set the proxy country to US
    "country": "US",
    # set the proxy pool to residential
    "proxy_pool": "public_residential_pool",
}


class Review(TypedDict):
    id: str
    userId: str
    business: dict
    user: dict
    comment: dict
    rating: int
    # and more


def parse_page(response: ScrapeApiResponse):
    """parse business data from yelp business pages"""
    sel = response.selector
    xpath = lambda xp: sel.xpath(xp).get(default="").strip()
    open_hours = {}
    for day in sel.xpath('//th/p[contains(@class,"day-of-the-week")]'):
        name = day.xpath("text()").get().strip()
        value = day.xpath("../following-sibling::td//p/text()").get().strip()
        open_hours[name.lower()] = value

    return dict(
        name=xpath("//h1/text()"),
        website=xpath('//p[contains(text(),"Business website")]/following-sibling::p/a/text()'),
        phone=xpath('//p[contains(text(),"Phone number")]/following-sibling::p/text()'),
        address=xpath('//a[contains(text(),"Get Directions")]/../following-sibling::p/text()'),
        logo=xpath('//img[contains(@class,"businessLogo")]/@src'),
        claim_status="".join(sel.xpath('//span[span[contains(@class,"claim")]]/text()').getall()).strip().lower(),
        open_hours=open_hours,
    )


def parse_business_id(response: ScrapeApiResponse):
    """parse the business id from yelp business pages"""
    selector = response.selector
    business_id = selector.css('meta[name="yelp-biz-id"]::attr(content)').get()
    
    if not business_id:
        # Fallback to regex search within the page content
        content = response.scrape_result.get("content", "")
        match = re.search(r'"bizId"\s*:\s*"([^"]+)"', content) or re.search(r'"businessId"\s*:\s*"([^"]+)"', content)
        if match:
            business_id = match.group(1)
            
    return business_id


def parse_review_data(response: ScrapeApiResponse):
    """parse review data from the JSON response"""
    content = response.scrape_result.get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        log.error("Failed to parse GraphQL response as JSON. Saving to 'last_gql_failed.html'")
        with open("last_gql_failed.html", "w", encoding="utf-8") as f:
            f.write(content)
        return {"reviews": [], "total_reviews": 0}
    
    business_data = data[0].get("data", {}).get("business")
    if not business_data:
        log.error(f"Unexpected GraphQL response: {json.dumps(data)[:250]}")
        return {"reviews": [], "total_reviews": 0}
        
    reviews = business_data.get("reviews", {}).get("edges", [])
    parsed_reviews = []
    for review in reviews:
        result = jmespath.search(
            """{
            encid: encid,
            text: text.{full: full, language: language},
            rating: rating,
            feedback: feedback.{coolCount: coolCount, funnyCount: funnyCount, usefulCount: usefulCount},
            author: author.{encid: encid, displayName: displayName, displayLocation: displayLocation, reviewCount: reviewCount, friendCount: friendCount, businessPhotoCount: businessPhotoCount},
            business: business.{encid: encid, alias: alias, name: name},
            createdAt: createdAt.utcDateTime,
            businessPhotos: businessPhotos[].{encid: encid, photoUrl: photoUrl.url, caption: caption, helpfulCount: helpfulCount},
            businessVideos: businessVideos,
            availableReactions: availableReactionsContainer.availableReactions[].{displayText: displayText, reactionType: reactionType, count: count}
            }""",
            review["node"],
        )
        parsed_reviews.append(result)
    total_reviews = business_data.get("reviewCount", 0)
    return {"reviews": parsed_reviews, "total_reviews": total_reviews}


def parse_search(response: ScrapeApiResponse):
    """parse listing data from the search XHR data"""
    search_data = []
    total_results = 0
    selector = response.selector
    script = selector.xpath("//script[@data-id='react-root-props']/text()").get()
    data = json.loads(script.split("react_root_props = ")[-1].rsplit(";", 1)[0])
    search_page_props = data.get("legacyProps", {}).get("searchAppProps", {}).get("searchPageProps", {})
    if search_page_props:
        total_results = search_page_props.get("paginationInfo", {}).get("totalResults", 0)
    main_content = search_page_props.get("mainContentComponentsListProps", [])
    for item in main_content:
        if item.get("bizId"):
            search_data.append(item)
    return {"search_data": search_data, "total_results": total_results}


async def scrape_pages(urls: List[str]) -> List[Dict]:
    """scrape yelp business pages"""
    # add the business pages to a scraping list
    result = []
    to_scrape = [ScrapeConfig(url, **BASE_CONFIG) for url in urls]
    async for response in SCRAPFLY.concurrent_scrape(to_scrape):
        result.append(parse_page(response))
    log.success(f"scraped {len(result)} business pages")
    return result


async def request_reviews_api(url: str, start_index: int, business_id: str, session_state: list = None):
    """request the graphql API for review data"""
    pagionation_data = {"version": 1, "type": "offset", "offset": start_index}
    pagionation_data = json.dumps(pagionation_data)
    after = base64.b64encode(pagionation_data.encode("utf-8")).decode(
        "utf-8"
    )  # decode the pagination values for the payload

    payload = json.dumps(
        [
            {
                "operationName": "GetBusinessReviewFeed",
                "variables": {
                    "encBizId": f"{business_id}",
                    "reviewsPerPage": 10,
                    "selectedReviewEncId": "",
                    "hasSelectedReview": False,
                    "sortBy": "DATE_DESC",
                    "languageCode": "en",
                    "ratings": [5, 4, 3, 2, 1],
                    "isSearching": False,
                    "after": after,  # pagination parameter
                    "isTranslating": False,
                    "translateLanguageCode": "en",
                    "reactionsSourceFlow": "businessPageReviewSection",
                    "minConfidenceLevel": "HIGH_CONFIDENCE",
                    "highlightType": "",
                    "highlightIdentifier": "",
                    "isHighlighting": False,
                },
                "extensions": {
                    "operationType": "query",
                    # static value
                    "documentId": "ef51f33d1b0eccc958dddbf6cde15739c48b34637a00ebe316441031d4bf7681",
                },
            }
        ]
    )

    headers = {
        "authority": "www.yelp.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": "https://www.yelp.com",
        "referer": url,  # main business page URL
        "x-apollo-operation-name": "GetBusinessReviewFeed",
    }
    
    if session_state is None:
        session_state = [uuid.uuid4().hex]

    response = None
    for attempt in range(5):
        try:
            config = ScrapeConfig(
                url="https://www.yelp.com/gql/batch", 
                headers=headers, 
                body=payload, 
                method="POST", 
                session=session_state[0],
                **BASE_CONFIG
            )
            response = await SCRAPFLY.async_scrape(config)
            content = response.scrape_result.get("content", "")
            
            if not content or content.strip().startswith("<"):
                raise ValueError("Received HTML or empty response instead of JSON (likely a CAPTCHA block)")
            
            # Verify it parses properly before accepting
            json.loads(content)
            return response
        except Exception as e:
            log.warning(f"GraphQL API request blocked or failed (Attempt {attempt + 1}/5) offset={start_index}: {e}")
            if attempt < 4:
                session_state[0] = uuid.uuid4().hex
                log.info("Re-warming up new session to bypass block...")
                try:
                    await SCRAPFLY.async_scrape(ScrapeConfig(url=url, **BASE_CONFIG, render_js=True, session=session_state[0]))
                except Exception:
                    pass
            
    return response


async def scrape_reviews(url: str, max_reviews: int = None, business_id: str = None) -> List[Review]:
    session_state = [uuid.uuid4().hex]
    # first find business ID from business URL if not explicitly provided
    if not business_id:
        response_business = None
        for attempt in range(5):
            log.info(f"scraping the business id from the business page (Attempt {attempt + 1}/5)")
            try:
                session_state[0] = uuid.uuid4().hex
                # We use wait_for_selector to ensure we don't accidentally accept the Yelp homepage redirect.
                # Using a unique session ID guarantees a completely fresh proxy and fingerprint on each retry.
                config = ScrapeConfig(
                    url=url, 
                    **BASE_CONFIG, 
                    render_js=True, 
                    wait_for_selector="meta[name='yelp-biz-id']",
                    session=session_state[0]
                )
                response_business = await SCRAPFLY.async_scrape(config)
                extracted_id = parse_business_id(response_business)
                if extracted_id:
                    business_id = extracted_id
                    break
            except Exception as e:
                log.warning(f"Scrape timeout or error: {e}")
                
            log.warning("Failed to find business ID (likely a CAPTCHA block), retrying with a new proxy...")
        
        if not business_id:
            # Save the raw HTML to help with debugging
            if response_business and hasattr(response_business, "scrape_result"):
                with open("last_failed_page.html", "w", encoding="utf-8") as f:
                    f.write(response_business.scrape_result.get("content", ""))
            raise ValueError(f"Failed to find business ID for {url}. The page might have been blocked. Raw HTML saved to 'last_failed_page.html'.")
    else:
        log.info("Warming up session to bypass anti-bot protections...")
        try:
            await SCRAPFLY.async_scrape(ScrapeConfig(url=url, **BASE_CONFIG, render_js=True, session=session_state[0]))
        except Exception:
            pass

    log.info("scraping the first review page")
    first_page = await request_reviews_api(url=url, business_id=business_id, start_index=1, session_state=session_state)
    review_data = parse_review_data(first_page)
    reviews = review_data["reviews"]
    total_reviews = review_data["total_reviews"]

    # find total page count to scrape
    if max_reviews and max_reviews < total_reviews:
        total_reviews = max_reviews

    # next, scrape the remaining review pages
    log.info(f"scraping review pagination, remaining ({total_reviews // 10}) more pages")
    for offset in range(11, total_reviews, 10):
        try:
            response = await request_reviews_api(url=url, business_id=business_id, start_index=offset, session_state=session_state)
            new_review_data = parse_review_data(response)["reviews"]
            reviews.extend(new_review_data)
        except Exception as e:
            log.error(f"An error occurred while scraping review pages: {e}")
            pass
    log.success(f"scraped {len(reviews)} reviews from review pages")
    return reviews


async def scrape_search(keyword: str, location: str, max_pages: int = None):
    """scrape single page of yelp search"""

    def make_search_url(offset):
        base_url = "https://www.yelp.com/search?"
        params = {"find_desc": keyword, "find_loc": location, "start": offset}
        return base_url + urlencode(params)
        # final url example:
        # https://www.yelp.com/search?find_desc=plumbers&find_loc=Seattle%2C+WA&start=1

    log.info("scraping the first search page")
    first_page = await SCRAPFLY.async_scrape(ScrapeConfig(make_search_url(1), **BASE_CONFIG, render_js=True))
    data = parse_search(first_page)
    search_data = data["search_data"]
    total_results = data["total_results"]

    # find total page count to scrape
    total_pages = math.ceil(total_results / 10)  # each page contains 10 results
    if max_pages and max_pages < total_pages:
        total_pages = max_pages

    # add the remaining pages to a scraping list and scrape them concurrently
    log.info(f"scraping search pagination, remaining ({total_pages - 1}) more pages")
    other_pages = [
        ScrapeConfig(make_search_url(offset), **BASE_CONFIG, render_js=True)
        for offset in range(11, total_pages * 10, 10)
    ]
    async for response in SCRAPFLY.concurrent_scrape(other_pages):
        try:
            search_data.extend(parse_search(response)["search_data"])
        except Exception as e:
            log.error(f"An error occurred while scraping search pages", e)
            pass
    log.success(f"scraped {len(search_data)} listings from search pages")
    return search_data
