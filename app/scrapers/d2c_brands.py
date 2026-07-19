"""
Micraft Growth Engine - D2C Brand Scraper (Ecom / Shiplystic)

Finds Indian D2C brands that are strong prospects for Shiplystic:
  - They ship their own products direct-to-consumer
  - They're on a self-managed ecom platform (Shopify / WooCommerce / Magento)
  - They have a shipping volume problem that a shipping aggregator solves

Multi-source strategy (all free, no paid APIs):
  Source 1 — Seed list of ~120 known Indian D2C brand URLs (curated)
  Source 2 — DPIIT Startup India ecom/retail sector companies (government DB)
  Source 3 — Google Custom Search for myshopify.com India stores (optional;
             requires GOOGLE_CSE_ID + GOOGLE_CSE_KEY env vars, free 100 q/day)
  Source 4 — Platform detection from existing leads' company_url fields

Platform detection: fetches each website and looks for:
  Shopify   → cdn.shopify.com OR myshopify.com OR /cdn/shop/ in source
  WooCommerce → woocommerce OR wp-content/plugins/woocommerce in source
  Magento   → mage/cookies.js OR Magento_ OR /static/version in source
  Custom    → significant ecom signals (product pages, cart, checkout)

Contact extraction: /contact OR /contact-us → scrape phone + email from page text.
Falls back to Google Places (within free-tier budget).
"""

import re
import time
import random
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils import places_budget
from app.utils.logger import get_logger

log = get_logger("scraper_d2c")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

DPIIT_SEARCH_URL = "https://startupindia.gov.in/content/sih/en/search.html"
DPIIT_API_URL = "https://startupindia.gov.in/api/search/startup"

# --- Curated seed list: known Indian D2C brands with their websites ---
# SME-to-mid segment, likely on standard Shopify/WooCommerce plans
# These companies have direct shipping needs → Shiplystic targets
D2C_SEED_BRANDS = [
    # Fashion / Apparel
    {"name": "Snitch", "url": "https://www.snitch.co.in", "category": "Fashion"},
    {"name": "The Souled Store", "url": "https://www.thesouledstore.com", "category": "Fashion"},
    {"name": "Bewakoof", "url": "https://www.bewakoof.com", "category": "Fashion"},
    {"name": "Damensch", "url": "https://www.damensch.com", "category": "Fashion"},
    {"name": "Bonkers Corner", "url": "https://bonkerscorner.com", "category": "Fashion"},
    {"name": "House of Pataudi", "url": "https://www.houseofpataudi.com", "category": "Fashion"},
    {"name": "Zymrat", "url": "https://www.zymrat.com", "category": "Athleisure"},
    {"name": "Wearcraft", "url": "https://www.wearcraft.in", "category": "Fashion"},
    {"name": "Urbanic India", "url": "https://www.urbanic.com/in", "category": "Fashion"},
    {"name": "Breakbounce", "url": "https://www.breakbounce.com", "category": "Fashion"},
    {"name": "Rare Rabbit", "url": "https://rarerabbit.in", "category": "Fashion"},
    {"name": "Wrogn", "url": "https://wrogn.com", "category": "Fashion"},
    {"name": "Vegnonveg", "url": "https://vegnonveg.com", "category": "Sneakers"},
    {"name": "Neemans", "url": "https://www.neemans.com", "category": "Footwear"},
    {"name": "The Label Life", "url": "https://www.thelabellife.com", "category": "Fashion"},
    {"name": "Okhai", "url": "https://www.okhai.com", "category": "Ethnic Wear"},
    {"name": "Itse", "url": "https://www.itse.in", "category": "Fashion"},
    {"name": "Andamen", "url": "https://www.andamen.com", "category": "Fashion"},
    {"name": "Priya Chaudhary", "url": "https://www.priyachaudhary.com", "category": "Fashion"},
    {"name": "Label Deepika Nagpal", "url": "https://labeldeepa.com", "category": "Fashion"},
    # Beauty / Personal Care
    {"name": "mCaffeine", "url": "https://www.mcaffeine.com", "category": "Beauty"},
    {"name": "Minimalist India", "url": "https://www.theminimalist.co.in", "category": "Skincare"},
    {"name": "Pilgrim Beauty", "url": "https://www.pilgrimbeauty.com", "category": "Beauty"},
    {"name": "Plum Goodness", "url": "https://www.plumgoodness.com", "category": "Beauty"},
    {"name": "Juicy Chemistry", "url": "https://www.juicychemistry.com", "category": "Beauty"},
    {"name": "Just Herbs", "url": "https://justherbs.in", "category": "Beauty"},
    {"name": "Dot And Key", "url": "https://www.dotandkey.com", "category": "Skincare"},
    {"name": "Earth Rhythm", "url": "https://www.earthrhythm.com", "category": "Beauty"},
    {"name": "Aqualogica", "url": "https://www.aqualogica.in", "category": "Skincare"},
    {"name": "Deconstruct Skin", "url": "https://www.deconstruct.co", "category": "Skincare"},
    {"name": "Prolixr", "url": "https://www.prolixr.com", "category": "Skincare"},
    {"name": "House of Beauty", "url": "https://www.houseofbeauty.in", "category": "Beauty"},
    {"name": "Nat Habit", "url": "https://www.nathabit.in", "category": "Beauty"},
    {"name": "The Derma Co", "url": "https://www.thederma.co", "category": "Skincare"},
    {"name": "Kapiva Ayurveda", "url": "https://www.kapiva.in", "category": "Ayurveda"},
    {"name": "Blue Nectar", "url": "https://www.bluenectar.co.in", "category": "Ayurveda"},
    # Food / Nutrition / Health
    {"name": "True Elements", "url": "https://www.trueelements.com", "category": "Health Food"},
    {"name": "Oziva Nutrition", "url": "https://www.oziva.in", "category": "Nutrition"},
    {"name": "Wellbeing Nutrition", "url": "https://www.wellbeingnutrition.com", "category": "Nutrition"},
    {"name": "Nourish Organics", "url": "https://www.nourishorganics.in", "category": "Organic Food"},
    {"name": "Happilo", "url": "https://www.happilo.com", "category": "Dry Fruits"},
    {"name": "Millet Amma", "url": "https://www.milletamma.com", "category": "Millets"},
    {"name": "Slurrp Farm", "url": "https://www.slurrpfarm.com", "category": "Kids Food"},
    {"name": "Soulfull", "url": "https://www.soulfull.co.in", "category": "Health Food"},
    {"name": "Farmley", "url": "https://www.farmley.com", "category": "Dry Fruits"},
    {"name": "Keeros Super Foods", "url": "https://www.keeros.com", "category": "Health Food"},
    {"name": "Eat Anytime", "url": "https://www.eatanytime.in", "category": "Health Food"},
    {"name": "Borges India", "url": "https://www.borges-india.com", "category": "Olive Oil"},
    {"name": "Jiwa Foods", "url": "https://www.jiwafoods.com", "category": "Healthy Snacks"},
    # Home / Lifestyle
    {"name": "Nestasia", "url": "https://www.nestasia.in", "category": "Home Decor"},
    {"name": "Chumbak", "url": "https://www.chumbak.com", "category": "Lifestyle"},
    {"name": "Pepperfry", "url": "https://www.pepperfry.com", "category": "Furniture"},
    {"name": "HomeTown India", "url": "https://www.hometown.in", "category": "Home Decor"},
    {"name": "Wakefit", "url": "https://www.wakefit.co", "category": "Mattress/Sleep"},
    {"name": "The Knotty Ones", "url": "https://www.theknottyones.com", "category": "Towels"},
    {"name": "Ekatra", "url": "https://ekatra.in", "category": "Home Decor"},
    {"name": "Ellementry", "url": "https://www.ellementry.com", "category": "Home"},
    {"name": "Klove Studio", "url": "https://www.klovestudio.com", "category": "Lighting"},
    {"name": "Soulflower", "url": "https://www.soulflower.biz", "category": "Wellness"},
    {"name": "Petal Fresh India", "url": "https://petalfresh.in", "category": "Beauty/Home"},
    {"name": "Saffola Active", "url": "https://saffolaactive.com", "category": "Health"},
    # Electronics / Tech accessories
    {"name": "Noise Gadgets", "url": "https://www.gonoise.com", "category": "Wearables"},
    {"name": "Boat Lifestyle", "url": "https://www.boat-lifestyle.com", "category": "Audio"},
    {"name": "Fire Boltt", "url": "https://www.fireboltt.com", "category": "Wearables"},
    {"name": "Portronics", "url": "https://www.portronics.com", "category": "Tech Accessories"},
    {"name": "Zebronics", "url": "https://www.zebronics.com", "category": "Tech Accessories"},
    {"name": "Crossbeats", "url": "https://www.crossbeats.com", "category": "Audio"},
    {"name": "Pebble India", "url": "https://www.pebble.in", "category": "Tech Accessories"},
    # Kids / Baby
    {"name": "Moms Co", "url": "https://www.the-moms-co.com", "category": "Baby Products"},
    {"name": "Babyorgano", "url": "https://www.babyorgano.com", "category": "Baby Organic"},
    {"name": "Babyhug", "url": "https://www.babyhug.com", "category": "Baby Products"},
    {"name": "Nite Owl Books", "url": "https://niteowlbooks.in", "category": "Kids Books"},
    # Sports / Outdoors
    {"name": "Cultsport", "url": "https://www.cultsport.com", "category": "Sports"},
    {"name": "Six5Six Sport", "url": "https://www.six5six.in", "category": "Sportswear"},
    {"name": "Nivia Sports", "url": "https://www.nivia.com", "category": "Sports Equipment"},
    # Gifting / Artisan
    {"name": "Giftpiper", "url": "https://www.giftpiper.com", "category": "Gifting"},
    {"name": "Itsy Bitsy", "url": "https://itsybitsy.in", "category": "Art Supplies"},
    {"name": "Asha Handicrafts", "url": "https://www.ashahandicrafts.com", "category": "Handicraft"},
    {"name": "Jaypore", "url": "https://www.jaypore.com", "category": "Ethnic/Artisan"},
    {"name": "Craftsvilla", "url": "https://www.craftsvilla.com", "category": "Ethnic/Artisan"},
    # Pet Care
    {"name": "Heads Up For Tails", "url": "https://www.headsupfortails.com", "category": "Pet Care"},
    {"name": "Wiggles Pet", "url": "https://www.wigglespet.com", "category": "Pet Care"},
    {"name": "Drools India", "url": "https://drools.co.in", "category": "Pet Food"},
    # Stationery / Office
    {"name": "Flintobox", "url": "https://www.flintobox.com", "category": "Kids Activity Kits"},
    {"name": "Paper Boat Press", "url": "https://paperboatpress.com", "category": "Stationery"},
    {"name": "Poprun", "url": "https://www.poprun.in", "category": "Stationery"},
]


def detect_platform(html: str, url: str) -> Optional[str]:
    """Detect ecommerce platform from page source."""
    h = html.lower()
    if "cdn.shopify.com" in h or "myshopify.com" in h or "/cdn/shop/" in h or "shopify.js" in h:
        return "shopify"
    if "woocommerce" in h or "wp-content/plugins/woo" in h or "wc-cart" in h:
        return "woocommerce"
    if "mage/cookies" in h or "magento_" in h.replace("-", "_") or "/static/version" in h:
        return "magento"
    if "bigcommerce" in h or "bc-storefront" in h:
        return "bigcommerce"
    if "opencart" in h or "opencart_token" in h:
        return "opencart"
    # Generic ecom signals
    if any(s in h for s in ("add-to-cart", "shopping-cart", "cart-drawer",
                            "checkout", "/products/", "product_id")):
        return "custom_ecom"
    return None


def extract_contact(html: str) -> dict:
    """Extract phone and email from page text."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    phones = re.findall(r"(?<!\d)(\+?91[-.\s]?)?([6-9]\d{9})(?!\d)", text)
    emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    phone = None
    if phones:
        p = phones[0]
        phone = f"+91{p[1]}" if not p[0] else f"{p[0].replace(' ', '').replace('-', '').replace('.', '')}{p[1]}"
    email = emails[0].lower() if emails else None
    # Filter platform/junk emails
    junk = {"example.com", "email.com", "noreply", "no-reply", "shopify.com", "wordpress.com"}
    if email and any(j in email for j in junk):
        email = None
    return {"phone": phone, "email": email}


class D2cBrandsScraper(BaseScraper):
    """Finds Indian D2C brands and detects their ecom platform."""

    SOURCE_NAME = "d2c_brands"

    def __init__(self, db: Session, target_product: str = "ecom",
                 resolve_phones: bool = True, use_cse: bool = False):
        super().__init__(db, target_product=target_product)
        self.resolve_phones = resolve_phones
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        self.use_cse = use_cse
        self.platform_stats = {}

    def _fetch_url(self, url: str, timeout: int = 15) -> Optional[str]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout,
                             allow_redirects=True)
            if r.status_code == 200:
                return r.text
        except Exception as e:
            log.debug("fetch_error", url=url[:60], error=str(e)[:60])
        return None

    def _contact_from_site(self, base_url: str, existing_html: str) -> dict:
        """Try contact page extraction, fall back to homepage text."""
        # First try contact page
        base = base_url.rstrip("/")
        for path in ("/contact", "/contact-us", "/pages/contact", "/pages/contact-us"):
            html = self._fetch_url(f"{base}{path}")
            if html:
                contact = extract_contact(html)
                if contact["phone"] or contact["email"]:
                    return contact
                time.sleep(0.3)
        # Fall back to homepage
        return extract_contact(existing_html) if existing_html else {}

    def _places_phone(self, name: str, city: str = "India") -> dict:
        result = {"phone": None, "website": None}
        if not places_budget.allow(1, kind="text_search"):
            return result
        try:
            r = requests.get(TEXT_SEARCH_URL, params={
                "query": f"{name} {city}", "key": self.api_key,
                "region": "in",
            }, timeout=15)
            candidates = r.json().get("results", [])[:2]
            if candidates and places_budget.allow(1, kind="details"):
                d = requests.get(DETAILS_URL, params={
                    "place_id": candidates[0]["place_id"], "key": self.api_key,
                    "fields": "formatted_phone_number,international_phone_number,website",
                }, timeout=15).json().get("result", {})
                result["phone"] = d.get("international_phone_number") or d.get("formatted_phone_number")
                result["website"] = d.get("website")
        except Exception as e:
            log.debug("d2c_places_error", name=name, error=str(e)[:80])
        return result

    def _cse_shopify_search(self) -> list[dict]:
        """
        Google Custom Search for Indian myshopify.com stores.
        Requires GOOGLE_CSE_ID env var. Free tier: 100 queries/day, 10 results each.
        """
        cse_id = getattr(settings, "GOOGLE_CSE_ID", None)
        if not cse_id:
            log.info("cse_skipped_no_id")
            return []
        CSE_URL = "https://www.googleapis.com/customsearch/v1"
        queries = [
            'site:myshopify.com "India" "COD available"',
            'site:myshopify.com "Made in India" OR "Ships from India"',
            'site:myshopify.com "free shipping India" -shopify.com/blog',
            'site:myshopify.com "India" clothing OR apparel OR fashion',
            'site:myshopify.com "India" beauty OR skincare OR cosmetics',
        ]
        brands = []
        for q in queries:
            try:
                r = requests.get(CSE_URL, params={
                    "key": self.api_key, "cx": cse_id, "q": q, "num": 10,
                    "gl": "in",
                }, timeout=20)
                items = r.json().get("items", [])
                for item in items:
                    parsed = urlparse(item.get("link", ""))
                    if "myshopify.com" in parsed.netloc:
                        shop_name = parsed.netloc.replace(".myshopify.com", "")
                        brands.append({
                            "name": shop_name.replace("-", " ").title(),
                            "url": f"https://{parsed.netloc}",
                            "category": "D2C (Shopify)",
                        })
                log.info("cse_query_done", query=q[:60], results=len(items))
                time.sleep(1.0)
            except Exception as e:
                log.warning("cse_error", query=q[:40], error=str(e)[:80])
        return brands

    def _dpiit_brands(self, max_pages: int = 5) -> list[dict]:
        """
        Scrape DPIIT Startup India database for ecommerce/retail startups.
        Endpoint: startupindia.gov.in with sector filter.
        """
        brands = []
        ecom_sectors = ["Consumer Internet", "Retail", "E-Commerce", "D2C"]
        for sector in ecom_sectors[:2]:  # limit to avoid over-scraping
            try:
                r = requests.post(
                    "https://api.startupindia.gov.in/sih/api/noauth/search/profiles/startup/",
                    json={
                        "pageNo": 0, "pageSize": 20,
                        "sector": sector,
                        "country": "India",
                    },
                    headers={**HEADERS, "Content-Type": "application/json"},
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    startups = data.get("startups") or data.get("content") or data.get("data") or []
                    for s in startups:
                        name = s.get("name") or s.get("startupName") or ""
                        website = s.get("website") or s.get("websiteUrl") or ""
                        city = s.get("city") or ""
                        if name and website:
                            brands.append({
                                "name": name,
                                "url": website if website.startswith("http") else f"https://{website}",
                                "category": f"DPIIT Startup ({sector})",
                                "city": city,
                            })
                    log.info("dpiit_sector", sector=sector, found=len(startups))
            except Exception as e:
                log.warning("dpiit_error", sector=sector, error=str(e)[:80])
            time.sleep(1.5)
        return brands

    # ------------------------------------------------------------------
    def scrape(self, search_query: str = "all", city: str = "",
               max_pages: int = None) -> list[dict]:
        """
        Collect brands from all sources, detect platform, extract contacts.
        search_query: 'all' | 'seed' | 'cse' | 'dpiit'
        """
        brands = []

        # Source 1: Seed list
        if search_query in ("all", "seed"):
            log.info("d2c_seed_loading", count=len(D2C_SEED_BRANDS))
            brands.extend(D2C_SEED_BRANDS)

        # Source 2: DPIIT Startup India
        if search_query in ("all", "dpiit"):
            log.info("d2c_dpiit_fetch")
            dpiit = self._dpiit_brands()
            brands.extend(dpiit)
            log.info("d2c_dpiit_done", found=len(dpiit))

        # Source 3: Google CSE (optional)
        if search_query in ("all", "cse") and self.use_cse:
            log.info("d2c_cse_fetch")
            cse = self._cse_shopify_search()
            brands.extend(cse)
            log.info("d2c_cse_done", found=len(cse))

        # Deduplicate by URL domain
        seen_domains = set()
        unique_brands = []
        for b in brands:
            domain = urlparse(b.get("url") or "").netloc.lower().replace("www.", "")
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                unique_brands.append(b)
        brands = unique_brands

        if max_pages:
            brands = brands[:max_pages * 10]

        log.info("d2c_total_brands", count=len(brands))

        # Phase 2: platform detection + contact extraction
        leads = []
        for i, brand in enumerate(brands, 1):
            try:
                url = brand.get("url", "")
                html = self._fetch_url(url)
                platform = detect_platform(html or "", url) if html else None

                if platform:
                    self.platform_stats[platform] = self.platform_stats.get(platform, 0) + 1

                contact = {}
                if html:
                    contact = self._contact_from_site(url, html)

                # Fallback: Places API for phone
                phone = contact.get("phone")
                website = url
                if not phone and self.resolve_phones and self.api_key:
                    places = self._places_phone(brand["name"], city or "India")
                    phone = places.get("phone")
                    time.sleep(random.uniform(0.3, 0.8))

                lead = {
                    "company_name": brand["name"],
                    "phone": phone,
                    "email": contact.get("email"),
                    "company_url": website,
                    "industry": f"D2C Brand — {brand.get('category', 'ecommerce')}",
                    "product_category": (
                        f"Platform: {platform or 'unknown'} | {brand.get('category', '')}"
                    )[:200],
                    "location": brand.get("city") or city or "India",
                    "full_name": None,
                    "title": None,
                    "gst_number": None,
                    "company_size": None,
                    "turnover": "",
                }
                leads.append(lead)

                if i % 10 == 0:
                    log.info("d2c_progress", done=i, total=len(brands),
                             leads=len(leads), platforms=self.platform_stats)
                time.sleep(random.uniform(0.8, 1.5))
            except Exception as e:
                log.warning("d2c_brand_error", brand=brand.get("name"), error=str(e)[:80])

        log.info("d2c_final", leads=len(leads), platforms=self.platform_stats)
        return leads
