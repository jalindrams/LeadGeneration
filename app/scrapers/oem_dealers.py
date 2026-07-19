"""
Micraft Growth Engine - OEM Dealer Locator Scraper (DMS source)

Why this source family is gold for DMS:
  - OEMs publish their FULL dealer network (name, address, phone) and keep it
    accurate because retail customers use it to find showrooms
  - Every entry is a real, operating, franchised dealership — zero fake listings
  - Phone numbers are showroom lines the dealership itself registered

Mechanics: vendor-built locator microsites (dealers.<brand>.com) expose
sitemap.xml listing every dealer page; each page embeds schema.org JSON-LD
(MotorcycleDealer/AutoDealer) with name, telephone, address, geo.

Currently enabled OEMs: Royal Enfield. The OEM_CONFIGS dict is the plug-in
point for more brands (Hero/Dashloc needs API auth — pending).
"""

import html as htmllib
import json
import random
import re
import time

import httpx
from sqlalchemy.orm import Session

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper_oem_dealers")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

OEM_CONFIGS = {
    "royal_enfield": {
        "brand": "Royal Enfield",
        "sitemap": "https://dealers.royalenfield.com/sitemap.xml",
        # dealer pages look like /<state>/<city>/<slug>
        "page_depth": 3,
        "industry": "Automobile Two Wheeler Dealer (Royal Enfield)",
        "category": "Royal Enfield Motorcycle Dealership",
    },
}

# JSON-LD @type values that identify a dealer/store entity
DEALER_TYPES = {
    "MotorcycleDealer", "AutoDealer", "AutomotiveBusiness", "LocalBusiness", "Store",
}


class OemDealerScraper(BaseScraper):
    """Harvests OEM dealer-locator microsites via sitemap + JSON-LD."""

    SOURCE_NAME = "oem_dealers"

    def __init__(self, db: Session, target_product: str = "dms", oem: str = "royal_enfield"):
        super().__init__(db, target_product=target_product)
        if oem not in OEM_CONFIGS:
            raise KeyError(f"Unknown OEM '{oem}'. Valid: {', '.join(OEM_CONFIGS)}")
        self.oem = oem
        self.cfg = OEM_CONFIGS[oem]
        self.client = httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30)

    # ------------------------------------------------------------------
    def dealer_urls(self, state_slug: str = None) -> list[str]:
        """All dealer-page URLs from the sitemap, optionally one state only."""
        r = self.client.get(self.cfg["sitemap"])
        r.raise_for_status()
        locs = [htmllib.unescape(u) for u in re.findall(r"<loc>(.*?)</loc>", r.text)]
        pages = []
        for u in locs:
            path = u.split("://", 1)[-1].split("/", 1)
            if len(path) < 2:
                continue
            parts = [p for p in path[1].split("/") if p]
            if len(parts) == self.cfg["page_depth"]:
                pages.append((parts[0], u))  # (state_slug, url)
        if state_slug:
            want = state_slug.strip().lower().replace(" ", "-")
            pages = [(s, u) for s, u in pages if s == want]
        return [u for _, u in pages]

    def states(self) -> dict:
        """State slug -> dealer-page count, from the sitemap."""
        counts = {}
        for u in self.dealer_urls():
            slug = u.split("://", 1)[-1].split("/")[1]
            counts[slug] = counts.get(slug, 0) + 1
        return counts

    # ------------------------------------------------------------------
    def _parse_dealer_page(self, url: str) -> dict | None:
        r = self.client.get(url)
        if r.status_code != 200:
            log.warning("dealer_page_status", url=url, status=r.status_code)
            return None
        blocks = re.findall(
            r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', r.text, re.S)
        for b in blocks:
            try:
                data = json.loads(b.strip())
            except (ValueError, TypeError):
                continue
            items = data if isinstance(data, list) else [data]
            for it in items:
                if not isinstance(it, dict):
                    continue
                if it.get("@type") in DEALER_TYPES and it.get("telephone"):
                    return self._lead_from_jsonld(it, url)
        return None

    def _lead_from_jsonld(self, it: dict, url: str) -> dict:
        name = re.sub(r"\s+", " ", str(it.get("name", ""))).strip(" ,")
        name = re.sub(r"\s*,\s*", ", ", name)
        phone = re.sub(r"[^\d+]", "", str(it.get("telephone", "")))
        addr = it.get("address") or {}
        locality, region, postal, street = "", "", "", ""
        if isinstance(addr, dict):
            locality = str(addr.get("addressLocality") or "").strip()
            region = str(addr.get("addressRegion") or "").strip()
            postal = str(addr.get("postalCode") or "").strip()
            street = str(addr.get("streetAddress") or "").strip()
        if locality and name.lower().endswith(f", {locality.lower()}"):
            name = name[: -(len(locality) + 2)].rstrip(" ,")
        # state slug from URL as region fallback (/state/city/slug)
        parts = url.split("://", 1)[-1].split("/")
        if not region and len(parts) > 1:
            region = parts[1].replace("-", " ").title()
        location = ", ".join(p for p in [locality, region] if p)
        return {
            "company_name": f"{name}" if self.cfg["brand"].lower() in name.lower()
                            else f"{name} ({self.cfg['brand']})",
            "phone": phone,
            "email": (it.get("email") or None),
            "company_url": url,
            "industry": self.cfg["industry"],
            "product_category": self.cfg["category"],
            "location": location or locality,
            "company_size": None,
            "title": None,
            "full_name": None,
            "gst_number": None,
            "turnover": "",
            "notes": street[:200] if street else None,
        }

    # ------------------------------------------------------------------
    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        search_query = state slug ('maharashtra', 'tamil-nadu', ...) or 'all'.
        city         = optional city filter (matches the /city/ URL segment).
        max_pages    = cap on dealer pages fetched (None = all).
        """
        state = None if (search_query or "").lower() in ("", "all") else search_query
        urls = self.dealer_urls(state)
        if city:
            want = city.strip().lower().replace(" ", "-")
            urls = [u for u in urls if f"/{want}/" in u.lower()]
        if max_pages:
            urls = urls[:max_pages]
        log.info("oem_dealer_pages", oem=self.oem, state=state or "all",
                 city=city or "-", count=len(urls))

        leads = []
        for i, u in enumerate(urls, 1):
            try:
                lead = self._parse_dealer_page(u)
                if lead:
                    leads.append(lead)
            except Exception as e:
                self.stats["errors"] += 1
                log.error("dealer_page_error", url=u, error=str(e)[:150])
            if i % 25 == 0:
                log.info("oem_progress", done=i, total=len(urls), leads=len(leads))
            time.sleep(random.uniform(1.2, 2.8))
        return leads
