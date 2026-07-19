"""
Micraft Growth Engine - Lead Scoring & Qualification Engine
Implements the locked v1 rule-based scoring model from system_analysis.md.

Scoring Model (max 100):
    Industry = Automotive Parts / Plastics / Fabrication   +20
    Title = Owner                                          +15
    Title = Plant Head / Director                          +12
    Title = Production Manager                             +10
    Company size 20-200 employees                          +10
    Has verified phone number                              +15
    Has verified email                                     +5
    Location = Manufacturing hub city                      +5
    Has GST number (verified business)                     +5
    Multiple sources confirm data                          +3
    Data freshness < 14 days                               +5

Tiers: Hot >= 70 | Warm 40-69 | Cold < 40

Qualification (ALL three required):
    1. ICP match (target industry + India)
    2. Decision-maker identified (Owner / Plant Head / Production Manager / Director)
    3. At least one verified contact method (phone preferred)
"""

import re
from datetime import datetime, timedelta

from app.utils.logger import get_logger

log = get_logger("scorer")

# Directory sources: the registered contact IS the verified decision-maker for that org
DIRECTORY_SOURCES = {"nabl", "iba_transporters", "aipma"}

# --- ICP industry keywords (target verticals from locked spec) ---
ICP_INDUSTRY_KEYWORDS = [
    # Automotive parts
    "automotive", "auto part", "auto component", "auto ancillary", "autoparts",
    "auto parts", "seating", "axle", "gear", "brake", "clutch", "piston",
    # Plastic molding
    "plastic", "mould", "mold", "injection", "polymer", "pvc",
    # Fabrication
    "fabrication", "sheet metal", "forging", "casting", "machining",
    "precision engineering", "press part", "stamping", "cnc",
]

# Generic manufacturing (weaker signal, half points)
GENERIC_MFG_KEYWORDS = ["manufactur", "industri", "engineering", "factory", "production"]

# --- Decision-maker titles ---
# v1.1: sales team targets Plant/Factory/IT Managers specifically (per call feedback July 2026)
OWNER_TITLES = ["owner", "proprietor", "founder", "managing director", "md", "ceo", "chairman"]
SENIOR_TITLES = ["plant head", "director", "vp", "president", "coo", "general manager", "gm"]
MANAGER_TITLES = [
    "production manager", "operations manager", "works manager", "factory manager",
    "plant manager", "it manager", "it head", "head of it", "cio", "systems manager",
]

# --- Target + manufacturing hub cities ---
HUB_CITIES = [
    "pune", "mumbai", "thane", "navi mumbai", "pimpri", "chinchwad", "chakan",
    "chennai", "ahmedabad", "aurangabad", "nashik", "coimbatore", "ludhiana",
    "faridabad", "gurgaon", "gurugram", "rajkot", "vadodara", "hosur",
]

# Indian GST format: 2-digit state + 10-char PAN + entity + Z + checksum
GST_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]Z?[A-Z\d]$")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gst_checksum_valid(gstin: str) -> bool:
    """
    Validate a GSTIN's check digit (official mod-36 algorithm).
    A GSTIN that fails this is fabricated or mistyped — Apollo-style databases
    don't do this; we verify authenticity offline, for free.
    """
    g = (gstin or "").strip().upper()
    if len(g) != 15 or not GST_RE.match(g):
        return False
    total = 0
    for i, ch in enumerate(g[:14]):
        if ch not in _GST_CHARS:
            return False
        val = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += val // 36 + val % 36
    check = _GST_CHARS[(36 - total % 36) % 36]
    return g[14] == check


def parse_turnover_crore(text: str) -> tuple[float, float] | None:
    """
    Parse turnover strings like '100-500 Crore', 'Rs. 5 - 10 Cr',
    'Above 1000 Crore', '50 Lakh - 1 Crore' into a (min, max) crore range.
    Returns None when unparseable.
    """
    if not text:
        return None
    t = text.lower().replace(",", "")
    # Each number takes the unit that follows it ("50 lakh - 1 crore" -> 0.5, 1.0);
    # numbers with no unit default to crore.
    nums = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|cr\b)?", t):
        if not m.group(1):
            continue
        val = float(m.group(1))
        unit = m.group(2) or ""
        if unit.startswith(("lakh", "lac")):
            val /= 100
        nums.append(val)
    if not nums:
        return None
    if "above" in t or "more than" in t or "+" in t:
        return (nums[0], float("inf"))
    if "upto" in t or "up to" in t or "below" in t or "less than" in t:
        return (0.0, nums[0])
    if len(nums) >= 2:
        return (min(nums[0], nums[1]), max(nums[0], nums[1]))
    return (nums[0], nums[0])


def _norm_phone_digits(phone: str) -> str:
    """Strip to digits, remove country code / STD prefix, return last 10."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    return digits[-10:] if len(digits) >= 10 else digits


def has_valid_phone(phone: str) -> bool:
    """Valid Indian phone: 10 digits, mobile starts 6-9, landline allowed with area code."""
    d = _norm_phone_digits(phone)
    if len(d) != 10:
        return False
    # Reject obviously bogus sequences
    if len(set(d)) == 1:  # 9999999999 etc.
        return False
    return d[0] in "6789" or d[0] in "12345"  # mobile or landline w/ STD


def has_valid_email(email: str) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        return False
    # Reject scraped platform emails (not the company's own)
    junk_domains = ["indiamart.com", "justdial.com", "example.com", "email.com"]
    return not any(email.endswith("@" + d) for d in junk_domains)


def _industry_text(lead: dict) -> str:
    return " ".join(
        str(lead.get(f) or "") for f in ("industry", "product_category", "company_name")
    ).lower()


def _product_profile(lead: dict) -> dict | None:
    """Load the product profile for a lead's target_product, if set."""
    key = (lead.get("target_product") or "").strip().lower()
    if not key:
        return None
    try:
        from app.products import get_profile
        return get_profile(key)
    except KeyError:
        return None


def industry_points(lead: dict, profile: dict | None = None) -> int:
    text = _industry_text(lead)
    keywords = (profile or {}).get("icp_keywords") or ICP_INDUSTRY_KEYWORDS
    if any(k in text for k in keywords):
        return 20
    if any(k in text for k in GENERIC_MFG_KEYWORDS):
        return 10  # adjacent — partial credit
    return 0


def title_points(title: str, profile: dict | None = None) -> int:
    if not title:
        return 0
    t = title.lower().strip()
    # Owners/founders are decision-makers for every product
    if any(k in t for k in OWNER_TITLES):
        return 15
    senior = (profile or {}).get("decision_makers", {}).get("senior") or SENIOR_TITLES
    manager = (profile or {}).get("decision_makers", {}).get("manager") or MANAGER_TITLES
    if any(k in t for k in senior):
        return 12
    if any(k in t for k in manager):
        return 10
    # Fall back to the global lists so cross-product titles still register
    if any(k in t for k in SENIOR_TITLES):
        return 12
    if any(k in t for k in MANAGER_TITLES):
        return 10
    return 0


def turnover_points(turnover: str, profile: dict | None = None) -> int:
    """+5 when known turnover overlaps the product's target band."""
    if not profile or not turnover:
        return 0
    parsed = parse_turnover_crore(turnover)
    if not parsed:
        return 0
    low, high = parsed
    band_low, band_high = profile.get("turnover_band_crore", (0, float("inf")))
    return 5 if low <= band_high and high >= band_low else 0


def size_points(company_size: str) -> int:
    """+10 if employee range overlaps the 20-200 ICP band."""
    if not company_size:
        return 0
    nums = [int(n) for n in re.findall(r"\d+", company_size)]
    if not nums:
        return 0
    low = min(nums)
    high = max(nums)
    # Overlap with [20, 200]
    return 10 if low <= 200 and high >= 20 else 0


def location_points(location: str) -> int:
    if not location:
        return 0
    loc = location.lower()
    return 5 if any(city in loc for city in HUB_CITIES) else 0


def gst_points(gst: str) -> int:
    """+5 only for a GSTIN whose check digit verifies — proves a real registered business."""
    if not gst:
        return 0
    return 5 if gst_checksum_valid(gst) else 0


def freshness_points(scraped_at) -> int:
    if not scraped_at:
        return 0
    if isinstance(scraped_at, str):
        try:
            scraped_at = datetime.fromisoformat(scraped_at)
        except ValueError:
            return 0
    return 5 if datetime.utcnow() - scraped_at < timedelta(days=14) else 0


def score_lead(lead: dict) -> tuple[int, dict]:
    """
    Score a lead dict (or Lead ORM object via lead_to_dict).

    v1.1 feedback signals (Sales Feedback Loop, Module 2):
      - response_status 'wrong_contact'  -> phone points zeroed (number is bad)
      - response_status 'not_interested' -> -40 (don't resurface as hot)
      - response_status 'interested'     -> +10 (priority follow-up)

    Returns:
        (score 0-100, breakdown dict of signal -> points)
    """
    response = (lead.get("response_status") or "").lower()
    profile = _product_profile(lead)

    _raw_title = lead.get("title") or lead.get("full_name_title") or ""
    _title_pts = title_points(_raw_title, profile)
    # Directory contacts (NABL/IBA/AIPMA) are verified org representatives — give manager credit
    if not _title_pts and lead.get("source") in DIRECTORY_SOURCES:
        _title_pts = 10

    phone_ok = has_valid_phone(lead.get("phone") or "") and response != "wrong_contact"
    breakdown = {
        "industry": industry_points(lead, profile),
        "title": _title_pts,
        "company_size": size_points(lead.get("company_size") or ""),
        "phone": 15 if phone_ok else 0,
        "email": 5 if has_valid_email(lead.get("email") or "") else 0,
        "location": location_points(lead.get("location") or ""),
        "gst": gst_points(lead.get("gst_number") or ""),
        "turnover_band": turnover_points(lead.get("turnover") or "", profile),
        "multi_source": 3 if lead.get("multi_source_confirmed") else 0,
        "freshness": freshness_points(lead.get("scraped_at")),
    }
    if response == "not_interested":
        breakdown["feedback"] = -40
    elif response in ("interested", "converted"):
        breakdown["feedback"] = 10

    return max(0, min(sum(breakdown.values()), 100)), breakdown


def tier(score: int) -> str:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def is_qualified(lead: dict) -> tuple[bool, list[str]]:
    """
    Locked qualification bar — ALL three must hold.
    Returns (qualified, list of missing criteria).
    """
    missing = []
    profile = _product_profile(lead)

    # 1. ICP match: target/adjacent industry, located in India (all sources are India-scoped)
    if industry_points(lead, profile) < 10:
        missing.append("icp_industry")

    # 2. Decision-maker identified
    _t = title_points(lead.get("title") or "", profile)
    if not _t and lead.get("source") not in DIRECTORY_SOURCES:
        missing.append("decision_maker")

    # 3. Verified contact method (phone preferred; a wrong_contact phone doesn't count)
    response = (lead.get("response_status") or "").lower()
    phone_ok = has_valid_phone(lead.get("phone") or "") and response != "wrong_contact"
    if not (phone_ok or has_valid_email(lead.get("email") or "")):
        missing.append("verified_contact")

    return (len(missing) == 0, missing)


def lead_to_dict(lead) -> dict:
    """Convert a Lead ORM object to the dict shape score_lead expects."""
    return {
        "company_name": lead.company_name,
        "industry": lead.industry,
        "product_category": lead.product_category,
        "title": lead.title,
        "company_size": lead.company_size,
        "phone": lead.phone,
        "email": lead.email,
        "location": lead.location,
        "gst_number": lead.gst_number,
        "scraped_at": lead.scraped_at,
        "response_status": lead.response_status,
        "turnover": lead.turnover,
        "target_product": getattr(lead, "target_product", None),
        "source": getattr(lead, "source", None),
    }


def score_and_qualify(lead) -> dict:
    """
    Full evaluation of a Lead ORM object or dict.
    Returns {score, tier, breakdown, qualified, missing}.
    """
    data = lead if isinstance(lead, dict) else lead_to_dict(lead)
    score, breakdown = score_lead(data)
    qualified, missing = is_qualified(data)
    return {
        "score": score,
        "tier": tier(score),
        "breakdown": breakdown,
        "qualified": qualified,
        "missing": missing,
    }
