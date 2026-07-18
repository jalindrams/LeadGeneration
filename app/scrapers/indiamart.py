"""
Micraft Growth Engine - IndiaMART Scraper
Primary lead source for Indian manufacturing companies.

Scrapes IndiaMART search results using Playwright (headless browser).
Extracts: company name, contact person, phone, location, product category.

Note: IndiaMART has anti-scraping measures. This scraper uses:
- Stealth browser settings
- Random delays (3-8 seconds)
- Realistic User-Agent strings
- Session cookie persistence
"""

import re
import random
from typing import Optional
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PWTimeout

from sqlalchemy.orm import Session

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper_indiamart")

# Realistic user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]


class IndiaMartScraper(BaseScraper):
    """Scraper for IndiaMART manufacturer listings."""

    SOURCE_NAME = "indiamart"

    def __init__(self, db: Session, target_product: str = None):
        super().__init__(db, target_product=target_product)
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None

    def _build_search_url(self, query: str, city: str, page: int = 1) -> str:
        """Build IndiaMART search URL."""
        query_encoded = query.replace(" ", "+")
        city_encoded = city.replace(" ", "+")
        # IndiaMART directory search URL
        url = f"https://dir.indiamart.com/search.mp?ss={query_encoded}&prdsrc=1&res=RC4&cx={city_encoded}"
        if page > 1:
            url += f"&pg={page}"
        return url

    def _setup_browser(self, pw):
        """Launch a stealth browser instance."""
        ua = random.choice(USER_AGENTS)
        self.browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        self.context = self.browser.new_context(
            user_agent=ua,
            viewport={"width": 1366, "height": 768},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        # Remove webdriver flag
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-US', 'en'] });
        """)
        self.page = self.context.new_page()
        log.info("browser_launched", user_agent=ua[:50])

    def _close_browser(self):
        """Close the browser instance."""
        if self.browser:
            self.browser.close()
            self.browser = None
            self.context = None
            self.page = None

    def _dismiss_popups(self):
        """Close any popups/modals that IndiaMART shows."""
        try:
            # Common popup close selectors
            popup_selectors = [
                "button.close",
                ".popup-close",
                "#closePopup",
                "[data-dismiss='modal']",
                ".modal .close",
                "#wzrkImageOnlyDiv .close",  # WebEngage popup
            ]
            for sel in popup_selectors:
                el = self.page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    log.debug("popup_dismissed", selector=sel)
        except Exception:
            pass  # Popups are non-critical

    def _extract_listings_from_page(self) -> list[dict]:
        """
        Extract company listings from the current search results page.
        Returns list of raw lead data dicts.
        """
        leads = []

        # IndiaMART uses various card structures. We try multiple selector strategies.
        # Strategy 1: Standard search result cards
        card_selectors = [
            ".card",            # New card format
            ".lst-cl",          # Listing card
            ".flx-cl",          # Flex card layout
            ".bx-lst",          # Box listing
            "[data-entry]",     # Data entry cards
        ]

        cards = []
        for selector in card_selectors:
            cards = self.page.query_selector_all(selector)
            if cards:
                log.debug("cards_found", selector=selector, count=len(cards))
                break

        if not cards:
            # Fallback: try to get any company-looking elements
            log.warning("no_cards_found", url=self.page.url)
            # Try extracting from page content directly
            return self._extract_from_page_content()

        for card in cards:
            try:
                lead = self._parse_card(card)
                if lead and lead.get("company_name"):
                    leads.append(lead)
            except Exception as e:
                log.debug("card_parse_error", error=str(e))
                self.stats["errors"] += 1

        return leads

    def _parse_card(self, card) -> Optional[dict]:
        """Parse a single listing card into a lead dict."""
        lead = {}

        # Company name - try multiple selectors
        name_selectors = [
            "a.cardlinks.elps.elps1", ".lcname a", ".companyname", 
            ".company-name", "a.fs16", ".lst-nm a", "h2 a",
        ]
        for sel in name_selectors:
            el = card.query_selector(sel)
            if el:
                lead["company_name"] = el.inner_text().strip()
                href = el.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        if href.startswith("//"):
                            href = "https:" + href
                        else:
                            href = "https://dir.indiamart.com" + href
                    lead["company_url"] = href
                break

        if not lead.get("company_name"):
            return None

        # Location - city/state
        loc_selectors = [
            ".newLocationUi", ".lcity", ".city-seo", ".location",
            ".adr", "[class*='city']", "[class*='loc']",
        ]
        for sel in loc_selectors:
            el = card.query_selector(sel)
            if el:
                lead["location"] = el.inner_text().strip()
                break

        # Product category
        prod_selectors = [
            ".prod-desc", ".product-name", ".prd-desc",
            ".lstdesc", "p.fs13",
        ]
        for sel in prod_selectors:
            el = card.query_selector(sel)
            if el:
                lead["product_category"] = el.inner_text().strip()[:300]
                break

        # Contact person name
        contact_selectors = [
            ".cntnm", ".contact-person", ".pername",
            "[class*='contact']",
        ]
        for sel in contact_selectors:
            el = card.query_selector(sel)
            if el:
                name = el.inner_text().strip()
                if name and len(name) > 2:
                    lead["full_name"] = name
                break

        # Phone number
        phone_selectors = [
            ".phn-no", ".phone", ".mob-no",
            "[class*='phone']", "[class*='mobile']",
            "a[href^='tel:']",
        ]
        for sel in phone_selectors:
            el = card.query_selector(sel)
            if el:
                phone_text = el.inner_text().strip()
                href = el.get_attribute("href") or ""
                if href.startswith("tel:"):
                    phone_text = href.replace("tel:", "").strip()
                # Extract digits
                phone_digits = re.sub(r"[^\d+]", "", phone_text)
                if len(phone_digits) >= 10:
                    lead["phone"] = phone_digits
                break

        # GST number (sometimes shown on IndiaMART)
        gst_selectors = [".gst-no", "[class*='gst']"]
        for sel in gst_selectors:
            el = card.query_selector(sel)
            if el:
                gst = el.inner_text().strip()
                # Indian GST format: 15 chars, e.g. 27AAACI1681R1ZY
                gst_match = re.search(r"\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2}", gst)
                if gst_match:
                    lead["gst_number"] = gst_match.group()
                break

        # Turnover (sometimes available on card)
        turnover_selectors = [".turnover", "[class*='turnover']", ".ann_turn"]
        for sel in turnover_selectors:
            try:
                el = card.query_selector(sel)
                if el:
                    t_text = el.inner_text().strip()
                    if "crore" in t_text.lower() or "lakh" in t_text.lower() or "turnover" in t_text.lower():
                        lead["turnover"] = t_text
                        break
            except Exception:
                pass

        # Set industry based on search context
        lead["industry"] = "Manufacturing"

        return lead

    def _scrape_profile_details(self, url: str) -> dict:
        """
        Navigate to a company's profile page to extract deeper contact info.
        """
        details = {}
        if not url:
            return details

        log.info("scraping_profile", url=url)
        try:
            # We use the same page to avoid overhead, but this requires care
            self.page.goto(url, timeout=20000, wait_until="domcontentloaded")
            self.page.wait_for_timeout(1500)

            # 1. Phone number from data attributes (more reliable than text)
            phone_selectors = [
                "#header_pnsno", "#footerPNS",
                ".pns_number", "[data-pnsno]",
            ]
            for sel in phone_selectors:
                el = self.page.query_selector(sel)
                if el:
                    pns = el.get_attribute("data-pnsno")
                    if pns:
                        details["phone"] = re.sub(r"[^\d+]", "", pns)
                        log.debug("phone_found_in_attr", phone=details["phone"])
                        break
            
            # Fallback for phone if data attribute fails
            if not details.get("phone"):
                el = self.page.query_selector("a[href^='tel:']")
                if el:
                    details["phone"] = re.sub(r"[^\d+]", "", el.get_attribute("href").replace("tel:", ""))

            # 2. Contact Person Name
            contact_selectors = [
                "p.FM_p29", "div.FM_m21 p", ".FM_p29",
                ".contact-person-name", ".ceoname",
            ]
            for sel in contact_selectors:
                el = self.page.query_selector(sel)
                if el:
                    name = el.inner_text().strip()
                    # Clean up common suffixes like (CEO) or (Proprietor)
                    name = re.sub(r"\(.*?\)", "", name).strip()
                    if name and len(name) > 2:
                        details["full_name"] = name
                        log.debug("contact_person_found", name=name)
                        break

            # 3. Email (rare but possible)
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", self.page.content())
            if email_match:
                details["email"] = email_match.group(0)
                log.debug("email_found", email=details["email"])

        except Exception as e:
            log.warning("profile_scrape_error", url=url, error=str(e))
        
        return details

    def _scrape_profile_details_with_new_page(self, url: str) -> dict:
        """
        Navigate to a company's profile page using a fresh page to avoid disrupting main flow.
        """
        details = {}
        if not url or not self.context:
            return details

        log.info("scraping_profile", url=url)
        temp_page = self.context.new_page()
        try:
            temp_page.goto(url, timeout=20000, wait_until="domcontentloaded")
            temp_page.wait_for_timeout(1000)

            # Phone number from data attributes
            pns_el = temp_page.query_selector("#header_pnsno, #footerPNS, [data-pnsno]")
            if pns_el:
                pns = pns_el.get_attribute("data-pnsno")
                if pns:
                    details["phone"] = re.sub(r"[^\d+]", "", pns)

            # Contact Person Name
            contact_el = temp_page.query_selector("p.FM_p29, div.FM_m21 p, .FM_p29, .contact-person-name")
            if contact_el:
                name = contact_el.inner_text().strip()
                # Clean up common suffixes like (CEO) or (Proprietor)
                name = re.sub(r"\(.*?\)", "", name).strip()
                # Skip generic placeholders
                if name and len(name) > 2 and "Contact" not in name:
                    details["full_name"] = name

            # Email
            email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", temp_page.content())
            if email_match:
                details["email"] = email_match.group(0)

            # Turnover
            try:
                # Basic lookup for Annual Turnover
                cells = temp_page.query_selector_all("td, th, span, div")
                for cell in cells:
                    text = cell.inner_text().strip()
                    if "Annual Turnover" in text:
                        parent = cell.evaluate_handle("el => el.parentElement")
                        if parent:
                            parent_text = parent.evaluate("el => el.innerText")
                            if "Crore" in parent_text or "Lakh" in parent_text:
                                val = parent_text.replace("Annual Turnover", "").strip()
                                details["turnover"] = val
                                break
            except Exception:
                pass

        except Exception as e:
            log.warning("profile_scrape_error", url=url, error=str(e))
        finally:
            temp_page.close()
        
        return details

    def _extract_from_page_content(self) -> list[dict]:
        """
        Fallback extraction from raw page content when card selectors fail.
        Extracts company names and phone numbers from the full page text.
        """
        leads = []
        try:
            content = self.page.content()

            # Look for links that seem like company pages
            company_links = self.page.query_selector_all('a[href*="/company/"], a[href*="indiamart.com/"]')
            for link in company_links[:30]:  # Limit to avoid noise
                try:
                    text = link.inner_text().strip()
                    href = link.get_attribute("href") or ""
                    if text and len(text) > 3 and "indiamart" not in text.lower():
                        lead = {
                            "company_name": text,
                            "company_url": href,
                            "industry": "Manufacturing",
                        }
                        leads.append(lead)
                except Exception:
                    continue
        except Exception as e:
            log.error("fallback_extraction_failed", error=str(e))

        return leads

    def _scroll_page(self):
        """Scroll down the page to trigger lazy loading."""
        try:
            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                self.page.wait_for_timeout(random.randint(800, 1500))
        except Exception:
            pass

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        Scrape IndiaMART search results for a given query and city.

        Args:
            search_query: e.g., "automotive parts manufacturer"
            city: e.g., "Pune"
            max_pages: Number of result pages to scrape

        Returns:
            List of raw lead dicts
        """
        if max_pages is None:
            max_pages = settings.SCRAPE_MAX_PAGES

        all_leads = []

        with sync_playwright() as pw:
            self._setup_browser(pw)
            try:
                for page_num in range(1, max_pages + 1):
                    url = self._build_search_url(search_query, city, page_num)
                    log.info("scraping_page", url=url, page=page_num)

                    try:
                        self.page.goto(url, timeout=30000, wait_until="domcontentloaded")
                        self.page.wait_for_timeout(2000)  # Let JS render

                        self._dismiss_popups()
                        self._scroll_page()

                        leads = self._extract_listings_from_page()
                        log.info("page_results", page=page_num, leads_found=len(leads))

                        if not leads:
                            log.info("no_more_results", page=page_num)
                            break
                        
                        # Deep-scrape profiles for missing contact info
                        for lead in leads:
                            if not lead.get("phone") or not lead.get("full_name"):
                                profile_url = lead.get("company_url")
                                # Strict filtering for company profiles
                                if profile_url and ("indiamart.com" in profile_url or "m.indiamart.com" in profile_url):
                                    # Exclude ads and generic indiamart domains
                                    exclude_patterns = ["seller.indiamart.com", "help.indiamart.com", "export.indiamart.com"]
                                    if any(p in profile_url for p in exclude_patterns):
                                        continue
                                        
                                    profile_info = self._scrape_profile_details_with_new_page(profile_url)
                                    lead.update(profile_info)
                                    # Anti-scraping delay between profile visits
                                    self.page.wait_for_timeout(random.randint(2000, 4000))

                        all_leads.extend(leads)

                        # Add location context if not already set
                        for lead in leads:
                            if not lead.get("location"):
                                lead["location"] = city

                    except PWTimeout:
                        log.warning("page_timeout", page=page_num, url=url)
                        continue
                    except Exception as e:
                        log.error("page_error", page=page_num, error=str(e))
                        continue

                    # Human-like delay between pages
                    if page_num < max_pages:
                        self.random_delay()

            finally:
                self._close_browser()

        log.info("scrape_complete", query=search_query, city=city, total_leads=len(all_leads))
        return all_leads
