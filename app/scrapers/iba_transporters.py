"""
Micraft Growth Engine - IBA Approved Transport Operators Scraper (TMS source)

The Indian Banks' Association publishes its list of RECOMMENDED transport
operators — companies vetted for handling bank consignments. Why this is
gold for TMS:

  - Bank-grade vetting: every operator passed IBA's approval process
  - Recommendation validity dates = renewal/compliance mindset (intent signal)
  - Full registered address + city + state + routes served

The list has NO phone numbers, so we resolve each operator's phone via
Google Places (Text Search -> Place Details) with a conservative name-match
guard: if Places' best hit doesn't clearly match the operator name, we DROP
the lead rather than store a wrong number. Quality over quantity.

Endpoint (reverse-engineered from checklogin.js):
  POST /iba/ajax/home/gettransporter.jsp
  searchValue=Y&nextValue=<page-1>&search=&codes=&toDate=&state=&ct=&next=n&doDirect=<page-1>
"""

import json
import random
import re
import time
from pathlib import Path

import httpx
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.config import settings
from app.scrapers.base import BaseScraper
from app.utils import places_budget
from app.utils.logger import get_logger

log = get_logger("scraper_iba")

LIST_URL = "https://www.iba.org.in/iba/ajax/home/gettransporter.jsp"
TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

# Cache Places lookups so re-runs never re-spend API quota
PHONE_CACHE = Path(__file__).resolve().parent.parent.parent / "exports" / "iba_phone_cache.json"

STOPWORDS = {"pvt", "ltd", "private", "limited", "the", "and", "&", "of",
             "transport", "transports", "logistics", "carriers", "carrier",
             "roadways", "roadlines", "cargo", "movers", "express", "co",
             "company", "corp", "india", "services", "service"}


def _tokens(name: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", name.lower()) if t not in STOPWORDS}


def name_match(a: str, b: str) -> bool:
    """Conservative overlap check between operator name and Places result name."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    return overlap / min(len(ta), len(tb)) >= 0.6


class IbaTransportersScraper(BaseScraper):
    """Harvests IBA's approved transport operator list + resolves phones."""

    SOURCE_NAME = "iba_transporters"

    def __init__(self, db: Session, target_product: str = "tms",
                 resolve_phones: bool = True):
        super().__init__(db, target_product=target_product)
        self.resolve_phones = resolve_phones
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        self.client = httpx.Client(follow_redirects=True, headers=HEADERS, timeout=30)
        self._cache = json.loads(PHONE_CACHE.read_text()) if PHONE_CACHE.exists() else {}
        self.resolution = {"resolved": 0, "no_match": 0, "no_result": 0, "cached": 0}

    # ------------------------------------------------------------------
    def fetch_page(self, page_index: int) -> str:
        data = {
            "searchValue": "Y", "nextValue": str(page_index), "search": "",
            "codes": "", "toDate": "", "state": "", "ct": "",
            "next": "n" if page_index else "s", "doDirect": str(page_index),
        }
        r = self.client.post(LIST_URL, data=data)
        r.raise_for_status()
        return r.text

    def parse_rows(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for tr in soup.select("tbody#sort_id tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(tds) < 9:
                continue
            rows.append({
                "name": tds[1], "code": tds[2], "address": tds[3],
                "city": tds[4], "pincode": tds[5], "state": tds[6],
                "routes": tds[7], "valid_till": tds[8],
            })
        return rows

    def total_pages(self, html: str) -> int:
        m = re.search(r"name='totalpage'\s+value=(\d+)", html)
        return int(m.group(1)) if m else 1

    # ------------------------------------------------------------------
    def _places_phone(self, name: str, city: str) -> dict:
        """Resolve phone/website via Places with name-match guard. Cached."""
        key = f"{name}|{city}".lower()
        if key in self._cache:
            self.resolution["cached"] += 1
            return self._cache[key]

        result = {"phone": None, "website": None, "matched_name": None}
        if not places_budget.allow(1, kind="text_search"):
            log.warning("places_cap_hit_lookup_skipped", name=name)
            return result  # NOT cached: retryable next month when quota resets
        try:
            r = requests.get(TEXT_SEARCH_URL, params={
                "query": f"{name} {city}", "key": self.api_key,
                "region": "in", "language": "en"}, timeout=15)
            candidates = r.json().get("results", [])[:3]
            best = next((c for c in candidates if name_match(name, c.get("name", ""))), None)
            if not best:
                self.resolution["no_match" if candidates else "no_result"] += 1
            elif not places_budget.allow(1, kind="details"):
                log.warning("places_cap_hit_lookup_skipped", name=name)
                return result
            else:
                d = requests.get(DETAILS_URL, params={
                    "place_id": best["place_id"], "key": self.api_key,
                    "fields": "name,formatted_phone_number,international_phone_number,website",
                }, timeout=15).json().get("result", {})
                phone = d.get("international_phone_number") or d.get("formatted_phone_number")
                if phone:
                    result = {"phone": phone, "website": d.get("website"),
                              "matched_name": best.get("name")}
                    self.resolution["resolved"] += 1
                else:
                    self.resolution["no_result"] += 1
        except Exception as e:
            log.warning("places_lookup_error", name=name, error=str(e)[:120])
            return result  # transient failure: NOT cached, retryable later

        self._cache[key] = result
        if len(self._cache) % 25 == 0:
            self._save_cache()
        return result

    def _save_cache(self):
        PHONE_CACHE.parent.mkdir(exist_ok=True)
        PHONE_CACHE.write_text(json.dumps(self._cache, indent=1))

    # ------------------------------------------------------------------
    def _to_lead(self, row: dict) -> dict | None:
        phone, website = None, None
        if self.resolve_phones and self.api_key:
            res = self._places_phone(row["name"], row["city"])
            phone, website = res["phone"], res["website"]
            time.sleep(random.uniform(0.4, 0.9))
        if not phone:
            return None  # quality bar: no confident phone -> no lead

        return {
            "company_name": row["name"],
            "phone": phone,
            "company_url": website,
            "industry": "Transport Operator (IBA Approved)",
            "product_category": (f"IBA {row['code']} | valid till {row['valid_till']} | "
                                 f"Routes: {row['routes']}")[:200],
            "location": ", ".join(p for p in [row["city"], row["state"]] if p),
            "full_name": None, "title": None, "email": None,
            "gst_number": None, "company_size": None, "turnover": "",
        }

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """search_query: 'all' or a state name filter (client-side)."""
        first = self.fetch_page(0)
        pages = self.total_pages(first)
        if max_pages:
            pages = min(pages, max_pages)
        log.info("iba_total", pages=pages)

        rows = self.parse_rows(first)
        for p in range(1, pages):
            try:
                rows.extend(self.parse_rows(self.fetch_page(p)))
            except Exception as e:
                log.error("iba_page_error", page=p, error=str(e)[:120])
            time.sleep(random.uniform(1.0, 2.0))

        want_state = (search_query or "").strip().lower()
        if want_state and want_state != "all":
            rows = [r for r in rows if want_state in r["state"].lower()]
        if city:
            rows = [r for r in rows if city.strip().lower() in r["city"].lower()]
        log.info("iba_rows", count=len(rows))

        leads = []
        for i, row in enumerate(rows, 1):
            lead = self._to_lead(row)
            if lead:
                leads.append(lead)
            if i % 25 == 0:
                log.info("iba_resolve_progress", done=i, total=len(rows),
                         leads=len(leads), **self.resolution)
        self._save_cache()
        log.info("iba_resolution_final", **self.resolution)
        return leads
