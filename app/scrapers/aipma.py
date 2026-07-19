"""
Micraft Growth Engine - AIPMA Member Directory Scraper (MES source)

The All India Plastics Manufacturers' Association publishes its FULL member
directory publicly at aipma.net/members-directory — and it is unusually rich:

  - Company + full address + city/state/pincode
  - CONTACT TABLE: representative names WITH DESIGNATIONS (Chairman, CEO,
    Proprietor, Director...) and their DIRECT MOBILE numbers
  - Email, website, GST number (validatable), category (MANUFACTURER/TRADER)
  - Product list with HSN codes

Plastics processors (injection molding, films, pipes) are core MES ICP.
Decision-maker name + title + direct mobile = hot-lead material.

Mechanics: plain server-rendered PHP, paginated via ?pageno=N (10 cards/page).
"""

import random
import re
import time

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper_aipma")

BASE_URL = "https://www.aipma.net/members-directory/index.php"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

MOBILE_RE = re.compile(r"(?<!\d)([6-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"^[\w.+\-]+@[\w\-]+\.[a-z]{2,}$", re.I)
# GSTIN: 2-digit state + 10-char PAN + entity + 'Z' + checksum (15 chars)
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]$")


class AipmaScraper(BaseScraper):
    """Harvests the public AIPMA member directory."""

    SOURCE_NAME = "aipma"

    def __init__(self, db: Session, target_product: str = "mes",
                 include_traders: bool = False):
        super().__init__(db, target_product=target_product)
        self.include_traders = include_traders
        self.skipped_traders = 0
        self.client = httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30)

    # ------------------------------------------------------------------
    def _field(self, card, label: str) -> str:
        """Value of a '<strong>LABEL:</strong> value' pair inside a card."""
        for strong in card.select("p strong"):
            if strong.get_text(strip=True).rstrip(":").upper() == label.upper():
                text = strong.parent.get_text(" ", strip=True)
                return re.sub(rf"^{re.escape(strong.get_text(strip=True))}\s*",
                              "", text).strip()
        return ""

    def _contacts(self, card) -> list[dict]:
        """Rows of the Representative/Designation/Mobile table."""
        out = []
        for table in card.select("table"):
            headers = [th.get_text(strip=True).lower() for th in table.select("th")]
            if "representative" not in headers:
                continue
            for tr in table.select("tbody tr"):
                tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
                if len(tds) >= 2 and tds[0]:
                    out.append({
                        "name": tds[0].strip(),
                        "designation": (tds[1] or "").strip().title() if len(tds) > 1 else "",
                        "mobile": MOBILE_RE.search(tds[2]).group(1)
                                  if len(tds) > 2 and MOBILE_RE.search(tds[2]) else "",
                    })
        return out

    def _products(self, card) -> str:
        for table in card.select("table"):
            headers = [th.get_text(strip=True).lower() for th in table.select("th")]
            if any("product" in hh for hh in headers):
                names = [tr.select("td")[0].get_text(" ", strip=True)
                         for tr in table.select("tbody tr") if tr.select("td")]
                return ", ".join(n for n in names if n)[:200]
        return ""

    # ------------------------------------------------------------------
    def _parse_card(self, card) -> dict | None:
        company = (card.get("data-name") or "").strip()
        if not company:
            return None
        city = (card.get("data-city") or "").strip()
        state = (card.get("data-state") or "").strip()
        category = self._field(card, "CATEGORY").upper()

        if category == "TRADER" and not self.include_traders:
            self.skipped_traders += 1
            return None

        contacts = self._contacts(card)
        primary = next((c for c in contacts if c["mobile"]), None)
        head_name = self._field(card, "NAME")
        head_mobile_m = MOBILE_RE.search(self._field(card, "MOBILE"))
        head_mobile = head_mobile_m.group(1) if head_mobile_m else ""
        tel = re.sub(r"[^\d]", "", self._field(card, "TEL NO"))

        if primary:
            full_name, title, phone = primary["name"], primary["designation"], primary["mobile"]
        elif head_mobile:
            full_name, title, phone = head_name, (contacts[0]["designation"]
                                                  if contacts else None), head_mobile
        elif tel and len(tel) >= 10:
            full_name, title, phone = head_name, None, tel
        else:
            return None  # no callable number — quality bar not met

        # Directory cards are occasionally misaligned (values land under the
        # wrong label) — validate every optional field, drop what doesn't parse.
        website = self._field(card, "WEBSITE").strip()
        if website and not website.startswith("http"):
            website = "https://" + website
        if website and not re.search(r"\.[a-z]{2,}", website.lower()):
            website = ""
        email = (self._field(card, "EMAIL") or "").strip().lower()
        if email and not EMAIL_RE.match(email):
            email = ""
        gst = re.sub(r"[^0-9A-Z]", "", self._field(card, "GST NO").upper())
        gst = gst if GSTIN_RE.match(gst) else None
        cat_label = category.title() if category else "Member"

        return {
            "company_name": company,
            "full_name": (full_name or "").title() or None,
            "title": (title or "")[:100] or None,
            "phone": phone,
            "email": email or None,
            "company_url": website[:255] or None,
            "gst_number": gst,
            "industry": f"Plastics {cat_label}",
            "product_category": self._products(card) or "Plastics products",
            "location": ", ".join(p for p in [city, state] if p) or None,
            "company_size": None,
            "turnover": "",
        }

    # ------------------------------------------------------------------
    def parse_page(self, pageno: int) -> list[dict]:
        r = self.client.get(BASE_URL, params={"pageno": str(pageno)})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        leads = []
        for card in soup.select(".main_div"):
            try:
                lead = self._parse_card(card)
                if lead:
                    leads.append(lead)
            except Exception as e:
                self.stats["errors"] += 1
                log.error("aipma_card_error", page=pageno, error=str(e)[:150])
        return leads

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        Walks ?pageno=1..N until two consecutive empty pages.
        search_query/city are accepted for interface parity; filtering is done
        by the scorer downstream (directory filters are unreliable server-side).
        """
        leads, empty_streak, page = [], 0, 0
        while empty_streak < 2:
            page += 1
            if max_pages and page > max_pages:
                break
            try:
                batch = self.parse_page(page)
            except Exception as e:
                log.error("aipma_page_error", page=page, error=str(e)[:150])
                empty_streak += 1
                continue
            if batch:
                empty_streak = 0
                leads.extend(batch)
            else:
                empty_streak += 1
            if page % 20 == 0:
                log.info("aipma_progress", page=page, leads=len(leads),
                         skipped_traders=self.skipped_traders)
            time.sleep(random.uniform(1.0, 2.2))
        log.info("aipma_scrape_done", pages=page, leads=len(leads),
                 skipped_traders=self.skipped_traders)
        return leads
