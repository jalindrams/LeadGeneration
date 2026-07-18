"""
Micraft Growth Engine - IndiaMART Profile Enricher
Extracts contact person + designation from an IndiaMART company profile page
using plain HTTP (no browser). IndiaMART corporate pages are server-rendered
and usually include a "Contact Person"/"CEO"/"Proprietor" block and GST.
"""

import re

import httpx
from bs4 import BeautifulSoup

from app.utils.logger import get_logger

log = get_logger("indiamart_profile")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://dir.indiamart.com/",
}

GST_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z[A-Z\d]\b")
DESIG_WORDS = ["proprietor", "owner", "director", "partner", "ceo", "founder",
               "manager", "chairman", "md"]


def extract_indiamart_profile(url: str, timeout: float = 12.0) -> dict:
    """
    Returns {contact_name, contact_title, gst_number, email, error}.
    """
    result = {"contact_name": None, "contact_title": None,
              "gst_number": None, "email": None, "error": None}
    if not url or "indiamart.com" not in url:
        result["error"] = "not_indiamart_url"
        return result

    # Strip tracking query params — they can 404 on direct HTTP
    url = url.split("?")[0]

    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                result["error"] = f"http_{resp.status_code}"
                return result
            html = resp.text
    except httpx.HTTPError as e:
        result["error"] = f"fetch_failed: {type(e).__name__}"
        return result

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # GST (shown on most profiles)
    m = GST_RE.search(text)
    if m:
        result["gst_number"] = m.group()

    # Email (rare, but grab if present)
    em = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    if em and "indiamart" not in em.group().lower():
        result["email"] = em.group().lower()

    # Contact person: known selectors first
    for sel in ("p.FM_p29", ".FM_p29", "div.FM_m21 p", ".contact-person-name",
                ".ceoname", "#supp_nm", ".pdinb"):
        el = soup.select_one(sel)
        if el:
            name = re.sub(r"\(.*?\)", "", el.get_text(strip=True)).strip()
            if 2 < len(name) < 60 and "contact" not in name.lower():
                result["contact_name"] = name
                break

    # Designation: pattern "Name (Designation)" anywhere on page
    dm = re.search(
        r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z.]+){0,3})\s*\(\s*(" +
        "|".join(DESIG_WORDS) + r")[^)]*\)", text, re.IGNORECASE)
    if dm:
        if not result["contact_name"]:
            result["contact_name"] = dm.group(1).strip()
        result["contact_title"] = dm.group(2).strip().title()

    # "Managed By" / "CEO" table rows on About sections
    if not result["contact_title"]:
        tm = re.search(r"(CEO|Proprietor|Director|Partner|Owner|Managing Director)\s*[:\-]?\s*"
                       r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z.]+){0,3})", text)
        if tm:
            result["contact_title"] = tm.group(1).title()
            if not result["contact_name"]:
                result["contact_name"] = tm.group(2).strip()

    log.info("indiamart_profile_extracted", url=url,
             person=bool(result["contact_name"]), title=bool(result["contact_title"]))
    return result
