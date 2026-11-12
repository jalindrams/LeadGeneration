"""
Contact extraction from a store's own pages. Indian e-commerce rules require
sellers to publish contact details and a grievance officer, so these pages are
the authoritative source. Every contact keeps the URL it was read from.
"""
import json
import re

from app.pipeline.verify import normalize_mobile
from app.processing.scorer import gst_checksum_valid

WA_RE = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|whatsapp://send\?phone=)\+?(\d{10,13})", re.I)
TEL_RE = re.compile(r"""href=["']tel:([^"']+)["']""", re.I)
TEXT_MOBILE_RE = re.compile(r"(?<![\d.])(?:\+?91[\s\-]?|0)?[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}(?![\d])")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
GRIEVANCE_RE = re.compile(
    r"grievance\s+officer\s*[:\-–]?\s*(?:name\s*[:\-]?\s*)?(?:mr\.?|ms\.?|mrs\.?|dr\.?|shri)?\s*"
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.I)
JUNK_EMAIL = ("example.com", "sentry", "wixpress", "domain.com", "email.com", ".png", ".jpg", ".webp", "shopify.com")


def _strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    return re.sub(r"<[^>]+>", " ", html)


def _jsonld_phones(html: str) -> list[str]:
    out = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, dict):
                for k, v in x.items():
                    if k.lower() == "telephone" and isinstance(v, str):
                        out.append(v)
                    elif isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(x, list):
                stack.extend(x)
    return out


def grievance_officer_name(html: str) -> str | None:
    m = GRIEVANCE_RE.search(_strip_tags(html))
    if not m:
        return None
    stop = {"email", "e-mail", "contact", "phone", "mobile", "tel", "address", "designation", "the", "our",
            "at", "for", "and", "can", "is", "on", "via", "number", "mail", "id", "who", "details"}
    words = []
    for w in m.group(1).split():
        if w.lower().strip(".:,") in stop:
            break
        words.append(w)
    if len(words) < 2:      # a real name has at least two words; one word is usually a heading
        return None
    return " ".join(words)


def extract_gstin(html: str) -> str | None:
    for g in GSTIN_RE.findall(html.upper()):
        if gst_checksum_valid(g):
            return g
    return None


def extract_contacts(html: str, url: str) -> list[dict]:
    """Return contacts ranked whatsapp > tel_link > jsonld > page_text, then emails."""
    seen, out = set(), []

    def add_phone(raw, kind):
        p = normalize_mobile(raw)
        if p and p not in seen:
            seen.add(p)
            out.append({"phone": p, "phone_type": kind, "source_url": url})

    for raw in WA_RE.findall(html):
        add_phone(raw, "whatsapp")
    for raw in TEL_RE.findall(html):
        add_phone(raw, "tel_link")
    for raw in _jsonld_phones(html):
        add_phone(raw, "jsonld")
    text = _strip_tags(html)
    for m in TEXT_MOBILE_RE.finditer(text):
        add_phone(m.group(0), "page_text")

    officer = grievance_officer_name(html)
    emails = []
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".")
        if e not in emails and not any(j in e for j in JUNK_EMAIL):
            emails.append(e)
    for e in emails[:3]:
        c = {"email": e, "source_url": url}
        if officer and "grievance" in e:
            c.update(name=officer, role="grievance_officer")
        out.append(c)
    if officer and not any(c.get("name") for c in out):
        out.append({"name": officer, "role": "grievance_officer", "source_url": url})
    return out
