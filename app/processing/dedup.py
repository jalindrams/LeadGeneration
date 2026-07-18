"""
Micraft Growth Engine - Deduplication Engine
Multi-level dedup: GST → Phone+Company → Company+Location hash.
"""

import hashlib
import re
from typing import Optional
from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.models import Lead
from app.utils.logger import get_logger

log = get_logger("dedup")


def normalize_phone(phone: str) -> str:
    """
    Normalize Indian phone numbers to a consistent format.
    Strips spaces, dashes, country code prefix.
    Returns last 10 digits (Indian mobile/landline).
    """
    if not phone:
        return ""
    # Remove all non-digit characters
    digits = re.sub(r"[^\d]", "", phone)
    # Remove leading 91 (India country code) if present
    if len(digits) > 10 and digits.startswith("91"):
        digits = digits[2:]
    # Remove leading 0 (STD code prefix)
    if len(digits) > 10 and digits.startswith("0"):
        digits = digits[1:]
    # Return last 10 digits
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for comparison.
    Lowercase, strip common suffixes, remove extra spaces.
    """
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in ["pvt ltd", "pvt. ltd.", "private limited", "limited", "ltd", "ltd.",
                   "llp", "inc", "inc.", "corporation", "corp", "corp."]:
        name = re.sub(rf"\s*{re.escape(suffix)}\s*$", "", name)
    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def compute_dedup_hash(company_name: str, phone: str = None, gst: str = None, location: str = None) -> str:
    """
    Compute a deduplication hash for a lead.
    Priority: GST (strongest) → Phone+Company → Company+Location.
    """
    if gst and gst.strip():
        # GST is globally unique for Indian businesses
        key = f"gst:{gst.strip().upper()}"
    elif phone and phone.strip():
        norm_phone = normalize_phone(phone)
        norm_company = normalize_company_name(company_name)
        key = f"phone_company:{norm_phone}:{norm_company}"
    else:
        norm_company = normalize_company_name(company_name)
        norm_location = (location or "").lower().strip()
        key = f"company_location:{norm_company}:{norm_location}"

    return hashlib.sha256(key.encode()).hexdigest()


def check_duplicate(db: Session, company_name: str, phone: str = None,
                    gst: str = None, location: str = None) -> Optional[Lead]:
    """
    Check if a lead already exists in the database.
    Returns the existing Lead if duplicate found, None otherwise.

    Checks in order:
    1. GST number exact match (strongest signal)
    2. Dedup hash match
    3. Fuzzy company name match in same location (threshold >= 90)
    """
    # Level 1: GST exact match
    if gst and gst.strip():
        existing = db.query(Lead).filter(Lead.gst_number == gst.strip().upper()).first()
        if existing:
            log.info("duplicate_found", method="gst", gst=gst, company=company_name)
            return existing

    # Level 2: Hash match
    dedup_hash = compute_dedup_hash(company_name, phone, gst, location)
    existing = db.query(Lead).filter(Lead.dedup_hash == dedup_hash).first()
    if existing:
        log.info("duplicate_found", method="hash", company=company_name)
        return existing

    # Level 3: Fuzzy company name match in same city
    if location:
        norm_location = location.lower().strip()
        # Get leads in same city for fuzzy comparison
        candidates = db.query(Lead).filter(
            Lead.location.ilike(f"%{norm_location}%")
        ).limit(500).all()

        norm_name = normalize_company_name(company_name)
        for candidate in candidates:
            candidate_name = normalize_company_name(candidate.company_name)
            score = fuzz.ratio(norm_name, candidate_name)
            if score >= 90:
                log.info("duplicate_found", method="fuzzy", score=score,
                         new=company_name, existing=candidate.company_name)
                return candidate

    return None


def deduplicate_lead(db: Session, lead_data: dict) -> tuple[bool, Optional[Lead], str]:
    """
    Full dedup pipeline for a single lead.

    Args:
        db: Database session
        lead_data: Dict with at least 'company_name', optionally 'phone', 'gst_number', 'location'

    Returns:
        (is_duplicate, existing_lead_or_none, dedup_hash)
    """
    company = lead_data.get("company_name", "")
    phone = lead_data.get("phone")
    gst = lead_data.get("gst_number")
    location = lead_data.get("location")

    dedup_hash = compute_dedup_hash(company, phone, gst, location)
    existing = check_duplicate(db, company, phone, gst, location)

    return (existing is not None, existing, dedup_hash)
