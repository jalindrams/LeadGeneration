"""
Micraft Growth Engine - Exhibition PDF Exhibitor List Scraper

Trade exhibitions publish exhibitor books as PDFs. This scraper:
  1. Downloads the PDF from a known URL
  2. Extracts company names via pdfplumber (table + text extraction)
  3. Resolves phone/website from the company website contact page first,
     falling back to Google Places (within free-tier budget)
  4. Stores leads with the exhibition as source + target product from config

Confirmed working exhibitions:
  analytica_lab_india_2026  → Calibration MS + DMS targets (lab instruments)
  analytica_lab_india_2025  → same, Hyderabad edition

Config pattern for adding new exhibitions:
  {
      "name": "Exhibition Display Name",
      "pdf_url": "https://...",
      "target_product": "mes|dms|tms|calibration|courier",
      "industry_label": "Industry label for the lead",
      "location_hint": "City, State",   # used when location not in PDF
  }
"""

import io
import re
import time
import random
import tempfile
from pathlib import Path

import requests
import pdfplumber
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils import places_budget
from app.utils.logger import get_logger

log = get_logger("scraper_exhibition_pdf")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/pdf,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
}

# --- Exhibition configs ---
EXHIBITION_CONFIGS = {
    "analytica_lab_india_2026": {
        "name": "Analytica Lab India 2026 (Mumbai)",
        "pdf_url": (
            "https://d2n1n6byqxibyi.cloudfront.net/asset/933560888063/"
            "document_ddik5i29ed38fe5lm792t13f37/"
            "ana%20Lab%20India%20and%20PCI%20Exhibitor%20list%201%20(1).pdf"
        ),
        "target_product": "calibration",
        "industry_label": "Laboratory Instruments / Analytical Equipment (Analytica Lab India Exhibitor)",
        "location_hint": "Mumbai, Maharashtra",
        "also_dms": True,  # these companies also need DMS for ISO 17025 compliance
    },
    "analytica_lab_india_2025": {
        "name": "Analytica Lab India 2025 (Hyderabad)",
        "pdf_url": (
            "https://messemuenchenindia.in/emailers/ali/2025/aug/ali_edm_21aug2025/"
            "ana%20Lab%20India%20and%20PPPE%20exhibitor%20list.pdf"
        ),
        "target_product": "calibration",
        "industry_label": "Laboratory Instruments / Analytical Equipment (Analytica Lab India Exhibitor)",
        "location_hint": "Hyderabad, Telangana",
        "also_dms": True,
    },
    # Add future exhibitions here following the same pattern:
    # "plastindia_2026": {
    #     "name": "PlastIndia 2026",
    #     "pdf_url": "https://...",        # fill when published
    #     "target_product": "mes",
    #     "industry_label": "Plastics Manufacturer/Supplier (PlastIndia Exhibitor)",
    #     "location_hint": "Gandhinagar, Gujarat",
    # },
    # "imtex_2025": {
    #     "name": "IMTEX 2025 (Bangalore)",
    #     "pdf_url": "https://...",        # IMTMA download page
    #     "target_product": "mes",
    #     "industry_label": "Machine Tool / Manufacturing Equipment (IMTEX Exhibitor)",
    #     "location_hint": "Bengaluru, Karnataka",
    # },
}

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

STOPWORDS = {"pvt", "ltd", "private", "limited", "the", "and", "of", "india",
             "co", "company", "corp", "solutions", "systems", "technologies",
             "international", "global", "group"}


def _tokens(name: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in STOPWORDS}


def _name_match(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / min(len(ta), len(tb)) >= 0.5


class ExhibitionPdfScraper(BaseScraper):
    """Downloads exhibition PDF and extracts exhibitor company leads."""

    SOURCE_NAME = "exhibition_pdf"

    def __init__(self, db: Session, exhibition_key: str, target_product: str = None,
                 resolve_phones: bool = True):
        config = EXHIBITION_CONFIGS.get(exhibition_key)
        if not config:
            raise ValueError(f"Unknown exhibition '{exhibition_key}'. Known: {list(EXHIBITION_CONFIGS)}")
        self.config = config
        self.exhibition_key = exhibition_key
        effective_product = target_product or config["target_product"]
        super().__init__(db, target_product=effective_product)
        self.resolve_phones = resolve_phones
        self.api_key = settings.GOOGLE_MAPS_API_KEY

    # ------------------------------------------------------------------
    def _download_pdf(self) -> bytes:
        url = self.config["pdf_url"]
        log.info("exhibition_pdf_download", exhibition=self.config["name"], url=url[:80])
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return r.content

    # Pattern: booth references like "7 D78", "4 C04", "Hall 5", "• " bullets
    _BOOTH_RE = re.compile(r"\b\d+\s+[A-Z]\d+\b|\bHall\s+\d+\b|\bStall\s+\d+\b|\s*•\s*")
    # Split on booth patterns to separate companies in merged multi-column text
    _SPLIT_RE = re.compile(r"\s+\d+\s+[A-Z]\d+\s+")

    def _clean_name(self, raw: str) -> str:
        """Remove booth numbers and stray bullets from a company name."""
        name = self._BOOTH_RE.sub(" ", raw).strip()
        # Truncate at booth-like pattern: "Acme Corp 7 D78" → "Acme Corp"
        name = re.sub(r"\s+\d+\s+[A-Z]\d+.*$", "", name).strip()
        name = re.sub(r"\s{2,}", " ", name)
        return name.strip(" .,;•")

    def _is_valid_name(self, name: str) -> bool:
        """Filter out booth numbers, headers, and junk lines."""
        if not name or len(name) < 4:
            return False
        # Pure numbers or very short abbreviations
        if re.match(r"^[\d\s\.\-]+$", name):
            return False
        # Column headers
        if name.lower() in ("company", "exhibitor", "name", "exhibitors", "s.no", "sr no",
                            "hall", "stand", "booth", "product", "country",
                            "company name hall no. booth no", "company name"):
            return False
        if re.match(r"^(page|sr\.?\s*no|sl\.?\s*no)\b", name.lower()):
            return False
        # Too many digits relative to letters (booth refs)
        digits = sum(1 for c in name if c.isdigit())
        letters = sum(1 for c in name if c.isalpha())
        if letters > 0 and digits / (digits + letters) > 0.5:
            return False
        return True

    def _extract_companies(self, pdf_bytes: bytes) -> list[dict]:
        """
        Extract company entries from PDF — handles:
          Format A: Proper tables (pdfplumber table extraction)
          Format B: Multi-column text grid (word-cluster extraction by x-position)
          Format C: Single-column numbered list
        """
        companies = []
        seen = set()

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):

                # --- Strategy A: Table extraction ---
                tables = page.extract_tables()
                found_table = False
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        cells = [c.strip() if c else "" for c in row]
                        name_raw = next((c for c in cells if c and len(c) > 4), "")
                        name = self._clean_name(name_raw)
                        if not self._is_valid_name(name):
                            continue
                        hall_stand = next(
                            (c for c in cells if re.search(r"\b[A-Z]\d+|\d+[A-Z]", c or "")), ""
                        )
                        key = name.lower()
                        if key not in seen:
                            seen.add(key)
                            companies.append({
                                "name": name,
                                "country": "",
                                "hall_stand": hall_stand,
                            })
                            found_table = True

                if found_table:
                    continue  # Table extraction succeeded for this page

                # --- Strategy B: Column-aware word extraction ---
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                if words:
                    # Determine page columns by clustering x0 positions
                    page_width = page.width
                    mid = page_width / 2

                    # Group words by approximate row (y0 within 5px tolerance)
                    rows_by_y = {}
                    for w in words:
                        y_bucket = round(w["top"] / 5) * 5
                        rows_by_y.setdefault(y_bucket, []).append(w)

                    for y_bucket in sorted(rows_by_y):
                        row_words = sorted(rows_by_y[y_bucket], key=lambda w: w["x0"])

                        # Split into left and right column
                        left_words = [w["text"] for w in row_words if w["x0"] < mid]
                        right_words = [w["text"] for w in row_words if w["x0"] >= mid]

                        for word_group in (left_words, right_words):
                            if not word_group:
                                continue
                            raw = " ".join(word_group)
                            # Split on booth pattern within the text
                            parts = self._SPLIT_RE.split(raw)
                            for part in parts:
                                name = self._clean_name(part)
                                if self._is_valid_name(name):
                                    key = name.lower()
                                    if key not in seen:
                                        seen.add(key)
                                        companies.append({
                                            "name": name,
                                            "country": "",
                                            "hall_stand": "",
                                        })
                else:
                    # --- Strategy C: Plain text fallback ---
                    text = page.extract_text() or ""
                    for line in text.split("\n"):
                        line = line.strip()
                        m = re.match(r"^\d+\.?\s+(.+)", line)
                        if m:
                            line = m.group(1).strip()
                        # Split merged multi-company lines
                        parts = self._SPLIT_RE.split(line)
                        for part in parts:
                            name = self._clean_name(part)
                            if self._is_valid_name(name):
                                key = name.lower()
                                if key not in seen:
                                    seen.add(key)
                                    companies.append({
                                        "name": name,
                                        "country": "",
                                        "hall_stand": "",
                                    })

        log.info("exhibition_pdf_extracted", count=len(companies), exhibition=self.config["name"])
        return companies

    # ------------------------------------------------------------------
    def _contact_from_website(self, website: str) -> dict:
        """Scrape /contact page for phone and email."""
        result = {"phone": None, "email": None}
        if not website:
            return result
        try:
            base = website.rstrip("/")
            for path in ("/contact", "/contact-us", "/contact.html", "/about"):
                try:
                    r = requests.get(f"{base}{path}", headers=HEADERS, timeout=10)
                    if r.status_code != 200:
                        continue
                    soup = BeautifulSoup(r.text, "html.parser")
                    text = soup.get_text(" ")
                    phones = re.findall(r"(?<!\d)(\+?91[-.\s]?)?([6-9]\d{9})(?!\d)", text)
                    if phones:
                        p = phones[0]
                        result["phone"] = f"+91{p[1]}" if not p[0] else f"{p[0].strip()}{p[1]}"
                    emails = re.findall(
                        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
                    if emails:
                        result["email"] = emails[0].lower()
                    if result["phone"] or result["email"]:
                        break
                except Exception:
                    continue
        except Exception as e:
            log.debug("contact_page_error", error=str(e)[:80])
        return result

    def _places_lookup(self, name: str, city: str) -> dict:
        """Google Places fallback for phone resolution."""
        result = {"phone": None, "website": None}
        if not places_budget.allow(1, kind="text_search"):
            return result
        try:
            r = requests.get(TEXT_SEARCH_URL, params={
                "query": f"{name} {city}", "key": self.api_key,
                "region": "in", "language": "en",
            }, timeout=15)
            candidates = r.json().get("results", [])[:3]
            best = next((c for c in candidates if _name_match(name, c.get("name", ""))), None)
            if best and places_budget.allow(1, kind="details"):
                d = requests.get(DETAILS_URL, params={
                    "place_id": best["place_id"], "key": self.api_key,
                    "fields": "formatted_phone_number,international_phone_number,website",
                }, timeout=15).json().get("result", {})
                result["phone"] = d.get("international_phone_number") or d.get("formatted_phone_number")
                result["website"] = d.get("website")
        except Exception as e:
            log.warning("exhibition_places_error", name=name, error=str(e)[:100])
        return result

    # ------------------------------------------------------------------
    def _to_lead(self, company: dict) -> dict | None:
        name = company["name"].strip()
        location = self.config.get("location_hint", "India")

        phone = website = email = None

        if self.resolve_phones and self.api_key:
            places = self._places_lookup(name, location.split(",")[0])
            phone = places.get("phone")
            website = places.get("website")
            if website:
                contact = self._contact_from_website(website)
                phone = phone or contact.get("phone")
                email = contact.get("email")
            time.sleep(random.uniform(0.5, 1.2))

        return {
            "company_name": name,
            "phone": phone,
            "email": email,
            "company_url": website,
            "industry": self.config["industry_label"],
            "product_category": (
                f"{self.config['name']} exhibitor"
                + (f" | {company['hall_stand']}" if company.get("hall_stand") else "")
            )[:200],
            "location": location,
            "full_name": None,
            "title": None,
            "gst_number": None,
            "company_size": None,
            "turnover": "",
        }

    def scrape(self, search_query: str = "all", city: str = "", max_pages: int = None) -> list[dict]:
        pdf_bytes = self._download_pdf()
        companies = self._extract_companies(pdf_bytes)

        # Optional city filter
        if city:
            city_lc = city.lower()
            companies = [c for c in companies
                         if city_lc in (self.config.get("location_hint") or "").lower()
                         or city_lc in c.get("country", "").lower()]

        if max_pages:
            companies = companies[:max_pages * 20]  # treat max_pages as approx batch size

        log.info("exhibition_resolving", count=len(companies), exhibition=self.config["name"])
        leads = []
        for i, company in enumerate(companies, 1):
            lead = self._to_lead(company)
            if lead:
                leads.append(lead)
            if i % 20 == 0:
                log.info("exhibition_progress", done=i, total=len(companies), leads=len(leads))
        return leads


def list_exhibitions() -> dict:
    """Return all configured exhibitions for CLI display."""
    return {k: v["name"] for k, v in EXHIBITION_CONFIGS.items()}
