"""
Micraft Growth Engine - Website Contact Extractor (Enrichment Step 2)
Given a company website URL, extract:
  - email addresses (mailto links + text)
  - phone numbers (Indian formats)
  - decision-maker: person name + designation (Owner/Director/Plant Manager/IT Manager...)

Fetches the homepage plus likely contact/about pages. Pure httpx + BeautifulSoup —
no browser needed for typical SME sites.
"""

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.utils.logger import get_logger

log = get_logger("website_extractor")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

# Candidate subpages that usually hold contact info
CONTACT_PATHS = [
    "contact", "contact-us", "contactus", "contact.html", "contact-us.html",
    "about", "about-us", "aboutus", "about.html", "about-us.html", "team",
    "our-team", "management",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Indian phone: +91/0 prefix, 10 digits possibly spaced/dashed
PHONE_RE = re.compile(r"(?:\+91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}")

JUNK_EMAIL_PATTERNS = [
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    "example.com", "domain.com", "email.com", "yourmail", "sentry", "wixpress",
    "godaddy", "@2x", "no-reply", "noreply",
]

# Designations we care about (ordered — first match on a page wins)
DESIGNATIONS = [
    "managing director", "plant head", "plant manager", "factory manager",
    "production manager", "operations manager", "works manager", "it manager",
    "it head", "general manager", "proprietor", "founder", "chairman",
    "director", "partner", "owner", "ceo",
]

# "Name — Designation" or "Designation: Name" patterns
NAME = r"((?:Mr\.?|Mrs\.?|Ms\.?|Shri|Smt\.?)\s+)?([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z.]+){1,3})"
_desig_alt = "|".join(re.escape(d) for d in DESIGNATIONS)
NAME_DESIG_RE = re.compile(
    rf"{NAME}\s*[\(,:–—-]\s*({_desig_alt})", re.IGNORECASE)
DESIG_NAME_RE = re.compile(
    rf"({_desig_alt})\s*[\):,–—-]?\s*{NAME}", re.IGNORECASE)

# Words that disqualify a "name" match (nav labels, headings etc.)
NOT_A_NAME = {
    "contact", "about", "home", "our", "the", "quality", "products", "services",
    "welcome", "read", "more", "view", "all", "get", "in", "touch", "quick",
    "links", "company", "profile", "india", "private", "limited", "pvt",
    "with", "and", "of", "for", "your", "app", "chat", "marketing", "group",
    "chief", "executive", "director", "manager", "owner", "partner", "founder",
    "mr", "mrs", "ms", "shri", "smt", "team", "tier", "oems", "years", "since",
    "best", "leading", "brilliant", "absolutely", "call", "email", "phone",
}

# Every word of a real name: capitalized, alphabetic (allows initials + CamelCase)
NAME_WORD_RE = re.compile(r"^[A-Z][a-zA-Z.']+$")


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def _valid_name(name: str) -> bool:
    words = name.split()
    if not 2 <= len(words) <= 4:
        return False
    if not all(NAME_WORD_RE.match(w) for w in words):
        return False
    return not any(w.lower().strip(".'") in NOT_A_NAME for w in words)


def _extract_from_html(html: str, base_domain: str) -> dict:
    """Extract contacts from one page's HTML."""
    found = {"emails": set(), "phones": set(), "people": []}
    soup = BeautifulSoup(html, "html.parser")

    # Emails: mailto links first (highest confidence)
    for a in soup.select("a[href^='mailto:']"):
        email = a.get("href", "")[7:].split("?")[0].strip().lower()
        if email and not any(j in email for j in JUNK_EMAIL_PATTERNS):
            found["emails"].add(email)

    text = soup.get_text(" ", strip=True)

    for m in EMAIL_RE.finditer(text):
        email = m.group().lower()
        if not any(j in email for j in JUNK_EMAIL_PATTERNS):
            found["emails"].add(email)

    for m in PHONE_RE.finditer(text):
        p = _clean_phone(m.group())
        if p:
            found["phones"].add(p)

    # Person + designation
    for m in NAME_DESIG_RE.finditer(text):
        name, desig = m.group(2).strip(), m.group(3).strip().title()
        if _valid_name(name):
            found["people"].append({"name": name, "title": desig})
    for m in DESIG_NAME_RE.finditer(text):
        desig, name = m.group(1).strip().title(), m.group(3).strip()
        if _valid_name(name):
            found["people"].append({"name": name, "title": desig})

    return found


def _rank_email(email: str, domain: str) -> int:
    """Prefer company-domain and named emails over generic gmail."""
    score = 0
    if domain and domain in email:
        score += 10
    local = email.split("@")[0]
    if local in ("info", "sales", "enquiry", "contact", "admin", "mail"):
        score += 1
    else:
        score += 3  # personal mailbox — more valuable
    return score


def extract_website_contacts(url: str, timeout: float = 12.0, max_pages: int = 4) -> dict:
    """
    Crawl homepage + contact/about pages of a company site.

    Returns:
        {email, phone, contact_name, contact_title, pages_fetched, error}
    """
    result = {"email": None, "phone": None, "contact_name": None,
              "contact_title": None, "pages_fetched": 0, "error": None}
    if not url:
        result["error"] = "no_url"
        return result
    if not url.startswith("http"):
        url = "http://" + url

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    domain = parsed.netloc.replace("www.", "")

    emails, phones, people = set(), set(), []

    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True,
                          verify=False) as client:
            # Homepage
            resp = client.get(url)
            result["pages_fetched"] += 1
            homepage_html = resp.text if resp.status_code == 200 else ""
            if homepage_html:
                f = _extract_from_html(homepage_html, domain)
                emails |= f["emails"]; phones |= f["phones"]; people += f["people"]

            # Find real contact/about links on the homepage, else guess paths
            candidates = []
            if homepage_html:
                soup = BeautifulSoup(homepage_html, "html.parser")
                for a in soup.select("a[href]"):
                    href = a.get("href", "")
                    label = (a.get_text() or "").lower()
                    if any(k in href.lower() or k in label
                           for k in ("contact", "about", "team", "management")):
                        candidates.append(urljoin(base + "/", href))
            candidates += [f"{base}/{p}" for p in CONTACT_PATHS]

            seen = {url}
            for cand in candidates:
                if result["pages_fetched"] >= max_pages:
                    break
                if cand in seen or urlparse(cand).netloc != parsed.netloc:
                    continue
                seen.add(cand)
                try:
                    r = client.get(cand)
                    result["pages_fetched"] += 1
                    if r.status_code == 200:
                        f = _extract_from_html(r.text, domain)
                        emails |= f["emails"]; phones |= f["phones"]; people += f["people"]
                except httpx.HTTPError:
                    continue

    except httpx.HTTPError as e:
        result["error"] = f"fetch_failed: {type(e).__name__}"
        return result
    except Exception as e:  # bad SSL, weird encodings, etc.
        result["error"] = f"error: {type(e).__name__}"
        return result

    if emails:
        result["email"] = sorted(emails, key=lambda e: -_rank_email(e, domain))[0]
    if phones:
        result["phone"] = sorted(phones)[0]
    if people:
        # Prefer the highest-priority designation found
        def prio(p):
            t = p["title"].lower()
            for i, d in enumerate(DESIGNATIONS):
                if d in t:
                    return i
            return len(DESIGNATIONS)
        best = sorted(people, key=prio)[0]
        result["contact_name"] = best["name"]
        result["contact_title"] = best["title"]

    log.info("website_extracted", url=url, email=bool(result["email"]),
             person=bool(result["contact_name"]), pages=result["pages_fetched"])
    return result
