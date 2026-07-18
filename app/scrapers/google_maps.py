"""
Micraft Growth Engine - Google Maps Scraper
Uses Google Places API (Text Search + Place Details) to find manufacturers.

This is a clean API-based approach — no browser scraping needed.
Google Places API free tier: ~$200 free credit/month (28,500 calls).
"""

import requests
from typing import Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper_google_maps")

# Google Places API endpoints
TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


class GoogleMapsScraper(BaseScraper):
    """Scraper using Google Maps Places API for manufacturer discovery."""

    SOURCE_NAME = "google_maps"

    def __init__(self, db: Session, target_product: str = None):
        super().__init__(db, target_product=target_product)
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        if not self.api_key or self.api_key == "your_google_maps_api_key_here":
            log.warning("google_maps_api_key_not_set")

    def _text_search(self, query: str, page_token: str = None) -> dict:
        """
        Perform a Google Places Text Search.
        Returns raw API response dict.
        """
        params = {
            "query": query,
            "key": self.api_key,
            "region": "in",  # India
            "language": "en",
        }
        if page_token:
            params["pagetoken"] = page_token

        response = requests.get(TEXT_SEARCH_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" and data.get("status") != "ZERO_RESULTS":
            log.warning("places_api_status", status=data.get("status"),
                        error=data.get("error_message", ""))

        return data

    def _get_place_details(self, place_id: str) -> Optional[dict]:
        """
        Get detailed info for a specific place (phone, website, etc.).
        This costs 1 additional API call per place.
        """
        params = {
            "place_id": place_id,
            "key": self.api_key,
            "fields": "name,formatted_address,formatted_phone_number,international_phone_number,website,types,business_status,user_ratings_total",
        }

        try:
            response = requests.get(DETAILS_URL, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "OK":
                return data.get("result", {})
        except Exception as e:
            log.debug("place_details_error", place_id=place_id, error=str(e))

        return None

    def _parse_place(self, place: dict, city: str, query: str) -> dict:
        """Parse a Google Places result into a lead dict."""
        lead = {
            "company_name": place.get("name", ""),
            "location": place.get("formatted_address", city),
            "industry": "Manufacturing",
            "source": self.SOURCE_NAME,
        }

        # Infer product category from the search query
        lead["product_category"] = query

        return lead

    def _enrich_with_details(self, lead: dict, place_id: str) -> dict:
        """Enrich a lead with Place Details (phone, website)."""
        details = self._get_place_details(place_id)
        if not details:
            return lead

        # Phone number
        phone = details.get("international_phone_number") or details.get("formatted_phone_number")
        if phone:
            lead["phone"] = phone

        # Website
        website = details.get("website")
        if website:
            lead["company_url"] = website

        # Address (more precise)
        address = details.get("formatted_address")
        if address:
            lead["location"] = address

        return lead

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        Search Google Maps for manufacturers in a city.

        Args:
            search_query: e.g., "automotive parts manufacturer"
            city: e.g., "Pune"
            max_pages: Max result pages (each has ~20 results, max 3 pages from Google)

        Returns:
            List of lead dicts
        """
        if not self.api_key or self.api_key == "your_google_maps_api_key_here":
            log.error("google_maps_api_key_missing",
                      msg="Set GOOGLE_MAPS_API_KEY in .env file")
            return []

        if max_pages is None:
            max_pages = min(settings.SCRAPE_MAX_PAGES, 3)  # Google caps at 3 pages (60 results)

        full_query = f"{search_query} in {city}"
        all_leads = []
        page_token = None

        for page_num in range(1, max_pages + 1):
            log.info("searching_google_maps", query=full_query, page=page_num)

            try:
                data = self._text_search(full_query, page_token)
                results = data.get("results", [])

                if not results:
                    log.info("no_more_results", page=page_num)
                    break

                log.info("places_found", count=len(results), page=page_num)

                for place in results:
                    try:
                        lead = self._parse_place(place, city, search_query)

                        # Get detailed info (phone, website) for each place
                        place_id = place.get("place_id")
                        if place_id:
                            lead = self._enrich_with_details(lead, place_id)
                            self.random_delay()  # Rate limit between detail calls

                        if lead.get("company_name"):
                            all_leads.append(lead)

                    except Exception as e:
                        log.debug("place_parse_error", error=str(e),
                                  name=place.get("name"))
                        self.stats["errors"] += 1

                # Check for next page
                page_token = data.get("next_page_token")
                if not page_token:
                    break

                # Google requires a short delay before using next_page_token
                self.random_delay()

            except requests.exceptions.RequestException as e:
                log.error("api_request_error", page=page_num, error=str(e))
                break
            except Exception as e:
                log.error("scrape_page_error", page=page_num, error=str(e))
                break

        log.info("scrape_complete", query=full_query, total_leads=len(all_leads))
        return all_leads
