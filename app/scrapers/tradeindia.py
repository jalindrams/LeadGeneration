"""
Micraft Growth Engine - TradeIndia Scraper
B2B directory scraper using TradeIndia's server-rendered Next.js JSON
(no browser needed — fast and stable).

Contact strategy ("triangulation"): TradeIndia masks phone numbers, but most
listings include the company's OWN website (catalog_mobile_url). We visit that
site with the website extractor and take phone/email/decision-maker from the
company's own pages — the most credible contact source there is.

Search URL returns ~28 listings/page across all of India; we filter to the
target city client-side and paginate until enough matches are found.
"""

import json
import re
import time
import random
from typing import Optional

import httpx

from sqlalchemy.orm import Session

from app.scrapers.base import BaseScraper
from app.enrichment.website_extractor import extract_website_contacts
from app.utils.logger import get_logger

log = get_logger("scraper_tradeindia")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL)

# Hard cap on pages walked per query even when city matches are scarce
MAX_PAGE_WALK = 15


class TradeIndiaScraper(BaseScraper):
    """Scraper for TradeIndia B2B listings with company-website triangulation."""

    SOURCE_NAME = "tradeindia"

    def __init__(self, db: Session, target_product: str = None):
        super().__init__(db, target_product=target_product)
        self.client: Optional[httpx.Client] = None

    def _fetch_listing_page(self, query: str, page: int) -> tuple[list[dict], dict]:
        q = query.strip().replace(" ", "+")
        url = f"https://www.tradeindia.com/search.html?keyword={q}"
        if page > 1:
            url += f"&page={page}"
        resp = self.client.get(url)
        if resp.status_code != 200:
            log.warning("listing_page_failed", url=url, status=resp.status_code)
            return [], {}
        m = NEXT_DATA_RE.search(resp.text)
        if not m:
            log.warning("next_data_missing", url=url)
            return [], {}
        try:
            payload = json.loads(m.group(1))
            sld = (payload.get("props", {}).get("pageProps", {})
                   .get("serverData", {}).get("searchListingData", {}))
            return sld.get("listing_data", []) or [], sld.get("pagination", {}) or {}
        except (json.JSONDecodeError, AttributeError) as e:
            log.warning("next_data_parse_error", url=url, error=str(e))
            return [], {}

    def _item_matches_city(self, item: dict, city: str) -> bool:
        if (item.get("country_name") or "").strip().lower() not in ("india", ""):
            return False
        item_city = (item.get("city") or "").strip().lower()
        return bool(item_city) and city.strip().lower() in item_city

    def _item_to_lead(self, item: dict, city: str) -> Optional[dict]:
        company = (item.get("co_name") or item.get("initial_co_name") or "").strip()
        if len(company) < 3:
            return None

        website = (item.get("catalog_mobile_url") or "").strip()
        profile_url = item.get("profile_url") or ""
        if profile_url and not profile_url.startswith("http"):
            profile_url = "https://www.tradeindia.com" + profile_url

        lead = {
            "company_name": company,
            "company_url": website or profile_url,
            "location": f"{item.get('city') or city}, {item.get('state') or ''}".strip(", "),
            "industry": (item.get("business_type") or "Manufacturer").replace(" | ", ", ")[:190],
            "product_category": (item.get("product_name")
                                 or item.get("product_description") or "")[:290],
        }

        # Triangulate contacts from the company's own website
        if website:
            contacts = extract_website_contacts(website, timeout=10.0, max_pages=3)
            if not contacts.get("error"):
                if contacts.get("phone"):
                    lead["phone"] = contacts["phone"]
                if contacts.get("email"):
                    lead["email"] = contacts["email"]
                if contacts.get("contact_name"):
                    lead["full_name"] = contacts["contact_name"]
                if contacts.get("contact_title"):
                    lead["title"] = contacts["contact_title"]

        return lead

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        Collect city-matching listings across paginated search results, then
        triangulate contact data from each company's own website.
        """
        wanted = (max_pages or 3) * 10  # rough lead budget for this query
        leads = []
        seen_profiles = set()

        with httpx.Client(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            self.client = client
            pages_walked = 0
            for page in range(1, MAX_PAGE_WALK + 1):
                items, pagination = self._fetch_listing_page(search_query, page)
                pages_walked += 1
                if not items:
                    break

                matches = [i for i in items if self._item_matches_city(i, city)]
                log.info("page_scanned", page=page, items=len(items),
                         city_matches=len(matches))

                for item in matches:
                    key = item.get("profile_id") or item.get("co_name")
                    if key in seen_profiles:
                        continue
                    seen_profiles.add(key)

                    lead = self._item_to_lead(item, city)
                    if lead:
                        leads.append(lead)
                        # polite gap between company-website visits
                        time.sleep(random.uniform(0.5, 1.5))

                if len(leads) >= wanted:
                    break
                if not pagination.get("has_next"):
                    break
                time.sleep(random.uniform(1.0, 2.5))

            self.client = None

        log.info("scrape_complete", query=search_query, city=city,
                 pages_walked=pages_walked, leads=len(leads))
        return leads
