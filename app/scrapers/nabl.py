"""
Micraft Growth Engine - NABL Accredited Lab Scraper (Calibration MS source)
Scrapes the public NABL (National Accreditation Board for Testing and
Calibration Laboratories) directory at nablwp.qci.org.in.

Why this source is gold for Calibration MS:
  - Government-verified companies (accredited labs — they exist, they operate)
  - Publishes CONTACT PERSON + direct MOBILE + EMAIL for every lab
  - Every accredited lab MUST manage calibration records — built-in product need
  - Certificate validity dates = renewal-driven urgency signals

Mechanics: classic ASP.NET WebForms — GET for __VIEWSTATE, POST the search
(field=Calibration + state), parse the results grid.
"""

import re
import time
import random
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from sqlalchemy.orm import Session

from app.scrapers.base import BaseScraper
from app.utils.logger import get_logger

log = get_logger("scraper_nabl")

BASE_URL = "https://nablwp.qci.org.in/laboratorysearchone"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

# Map our target cities to Indian states (NABL search is state-scoped)
CITY_TO_STATE = {
    "pune": "Maharashtra", "mumbai": "Maharashtra", "thane": "Maharashtra",
    "nashik": "Maharashtra", "aurangabad": "Maharashtra", "nagpur": "Maharashtra",
    "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "hosur": "Tamil Nadu",
    "ahmedabad": "Gujarat", "surat": "Gujarat", "vadodara": "Gujarat",
    "rajkot": "Gujarat", "bengaluru": "Karnataka", "bangalore": "Karnataka",
    "delhi": "Delhi", "gurgaon": "Haryana", "gurugram": "Haryana",
    "faridabad": "Haryana", "noida": "Uttar Pradesh", "hyderabad": "Telangana",
    "indore": "Madhya Pradesh", "jaipur": "Rajasthan", "kolkata": "West Bengal",
}

# NABL "Field" dropdown values
FIELD_VALUES = {"testing": "1", "calibration": "2", "medical": "3"}


class NablScraper(BaseScraper):
    """Scraper for the NABL accredited-laboratory public directory."""

    SOURCE_NAME = "nabl"

    def __init__(self, db: Session, target_product: str = None):
        super().__init__(db, target_product=target_product)

    def _hidden(self, html: str, name: str) -> str:
        m = re.search(rf'id="{name}" value="([^"]*)"', html)
        return m.group(1) if m else ""

    def _state_options(self, html: str) -> dict:
        m = re.search(r'MainContent_ddlstate".*?</select>', html, re.DOTALL)
        if not m:
            return {}
        return {name.strip(): value
                for value, name in re.findall(r'value="([^"]*)"[^>]*>([^<]*)<', m.group(0))}

    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        search_query picks the NABL field ('calibration' default; 'testing' works too).
        city → state for the search; rows matching the city sort first.
        """
        field = "calibration"
        for key in FIELD_VALUES:
            if key in (search_query or "").lower():
                field = key

        state_name = CITY_TO_STATE.get((city or "").strip().lower())
        if not state_name:
            log.warning("city_not_mapped_to_state", city=city)
            return []

        leads: list[dict] = []
        try:
            with httpx.Client(headers=HEADERS, timeout=40, follow_redirects=True,
                              verify=False) as client:
                r1 = client.get(BASE_URL)
                if r1.status_code != 200:
                    log.error("nabl_get_failed", status=r1.status_code)
                    return []

                states = self._state_options(r1.text)
                state_val = states.get(state_name)
                if not state_val:
                    log.error("state_not_in_dropdown", state=state_name)
                    return []

                payload = {
                    "__VIEWSTATE": self._hidden(r1.text, "__VIEWSTATE"),
                    "__VIEWSTATEGENERATOR": self._hidden(r1.text, "__VIEWSTATEGENERATOR"),
                    "__EVENTVALIDATION": self._hidden(r1.text, "__EVENTVALIDATION"),
                    "ctl00$MainContent$ddlstate": state_val,
                    "ctl00$MainContent$ddlLabType": FIELD_VALUES[field],
                    "ctl00$MainContent$ddlLabStatus": "0",
                    "ctl00$MainContent$btnSearch": "Search",
                }
                time.sleep(random.uniform(1, 2))
                r2 = client.post(BASE_URL, data=payload)
                if r2.status_code != 200:
                    log.error("nabl_post_failed", status=r2.status_code)
                    return []

                leads = self._parse_results(r2.text, city)
        except httpx.HTTPError as e:
            log.error("nabl_fetch_error", error=str(e))
            return []

        log.info("scrape_complete", field=field, state=state_name, city=city,
                 leads=len(leads))
        return leads

    def _parse_results(self, html: str, city: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")

        # Find the grid whose header includes 'CAB Name'
        grid = None
        for table in soup.find_all("table"):
            header = table.find("tr")
            if header and "CAB Name" in header.get_text():
                grid = table
                break
        if grid is None:
            log.warning("results_grid_not_found")
            return []

        rows = grid.find_all("tr")
        headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]

        def col(name):
            for i, h in enumerate(headers):
                if name.lower() in h.lower():
                    return i
            return None

        idx = {k: col(k) for k in
               ("CAB Name", "Contact Person", "Email", "Mobile", "Address",
                "State", "City", "Status", "Discipline", "Certificate Valid")}

        city_l = (city or "").strip().lower()
        city_rows, other_rows = [], []

        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
            if len(cells) < 10:
                continue

            def val(key):
                i = idx.get(key)
                return cells[i] if i is not None and i < len(cells) else ""

            status = val("Status")
            if "approved" not in status.lower():
                continue  # only active accreditations

            name = val("CAB Name").title()
            if len(name) < 3:
                continue

            phone = re.sub(r"[^\d]", "", val("Mobile"))
            lead = {
                "company_name": name,
                "full_name": val("Contact Person").title() or None,
                "phone": phone if len(phone) >= 10 else None,
                "email": (val("Email") or "").lower() or None,
                "location": f"{val('City')}, {val('State')}".strip(", "),
                "industry": "Calibration Laboratory (NABL accredited)",
                "product_category": (val("Discipline") or "")[:290],
            }
            if val("City").strip().lower() == city_l:
                city_rows.append(lead)
            else:
                other_rows.append(lead)

        log.info("results_parsed", city_matches=len(city_rows),
                 state_others=len(other_rows))
        # City rows first, then the rest of the state (all are valid leads)
        return city_rows + other_rows
