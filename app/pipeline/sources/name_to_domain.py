"""
Zero-API store-name -> domain resolution (Phase 0: 79% hit rate on Shopify
reviewers). Guess common domain forms and accept only when Shopify's own
/meta.json on that domain reports a matching store name.
"""
import re
from difflib import SequenceMatcher

from app.pipeline import fetch

TLDS = (".com", ".in", ".co.in", ".co", ".store", ".shop")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def slugs(name: str) -> list[str]:
    base = re.sub(r"\.(com|in|co|co\.in|store|shop)$", "", (name or "").lower().strip())
    base = re.sub(r"\s*[-|–].*$", "", base) or base
    out = []
    for s in (re.sub(r"[^a-z0-9]", "", base), re.sub(r"[^a-z0-9]+", "-", base).strip("-"),
              re.sub(r"[^a-z0-9]", "", re.sub(r"\b(the|store|shop|india|official)\b", "", base))):
        if s and len(s) >= 3 and s not in out:
            out.append(s)
    return out


def resolve(name: str) -> tuple[str | None, dict | None]:
    if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", (name or "").lower().strip()):
        candidates = [name.lower().strip()]
    else:
        candidates = [s + t for s in slugs(name) for t in TLDS]
    for dom in candidates:
        meta = fetch.get_json(f"https://{dom}/meta.json", timeout=7)
        if not isinstance(meta, dict) or "myshopify_domain" not in meta:
            continue
        sim = SequenceMatcher(None, _norm(name), _norm(meta.get("name"))).ratio()
        slug = dom.split(".")[0].replace("-", "")
        if sim >= 0.6 or slug in _norm(meta.get("myshopify_domain")):
            return dom, meta
    return None, None
