"""
S1 - Shopify App Store reviews. Reviewers of Indian shipping/COD/checkout apps
are Indian sellers; 1-3 star reviews of a competitor are the hottest leads.
Global apps are included but only Indian reviewers are kept.
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy import select

from app.pipeline import fetch
from app.pipeline.models import Store
from app.pipeline.sources.name_to_domain import resolve

SOURCE = "shopify_app_reviews"
# (slug, max_pages, is_shipping_competitor). Slugs verified reachable 2026-11-11.
APPS = [
    ("nimbuspost", 20, True), ("ithink-logistics", 20, True), ("shipmozo", 10, True),
    ("xpressbees", 5, True), ("shiprocket-engage", 5, True), ("vamaship", 5, True),
    ("kwikpass", 15, False), ("cod-order-confirmation", 5, False),
    ("cashfree-payments", 3, False), ("payu-india", 3, False), ("phonepe-payment-gateway", 3, False),
    ("parcelpanel", 120, True), ("trackingmore", 40, True),
]
STATE_FILE = Path("exports") / "app_reviews_state.json"


def _state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


_pending: dict | None = None


def _save_state(s: dict):
    """Deferred: the runner calls commit_state() only after the candidates are stored."""
    global _pending
    _pending = s


def commit_state():
    global _pending
    if _pending is not None:
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(json.dumps(_pending, indent=1))
        _pending = None


def parse_reviews(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for rev in soup.select("[data-merchant-review]"):
        stars = rev.select_one("[aria-label$='stars']")
        m = re.match(r"(\d)", stars.get("aria-label", "")) if stars else None
        side = rev.select_one("div.lg\\:tw-order-1") or rev
        lines = [t.strip() for t in side.stripped_strings if t.strip()]
        body = rev.select_one("[data-truncate-content-copy]") or rev.select_one("p")
        out.append({"id": rev.get("data-review-content-id"), "rating": int(m.group(1)) if m else None,
                    "store": lines[0] if lines else None,
                    "country": lines[1] if len(lines) > 1 else None,
                    "text": (body.get_text(" ", strip=True) if body else "")[:400]})
    return out


def discover(db, limit: int = 200, source: str = SOURCE) -> list[dict]:
    state = _state()
    seen_ids = set(state.get("seen_review_ids", []))
    known = {n for (n,) in db.execute(select(Store.name).where(Store.source == SOURCE))}
    found = []
    for slug, max_pages, competitor in APPS:
        for page in range(1, max_pages + 1):
            url = f"https://apps.shopify.com/{slug}/reviews?page={page}"
            status, html, _ = fetch.get(url, timeout=20)
            revs = parse_reviews(html) if status == 200 else []
            if not revs:
                break
            fresh = [r for r in revs if r["id"] not in seen_ids]
            for r in fresh:
                seen_ids.add(r["id"])
                if r["country"] != "India" or not r["store"] or r["store"] in known:
                    continue
                known.add(r["store"])
                dom, meta = resolve(r["store"])
                if not dom:
                    continue
                note = f"Reviewed {slug} ({r['rating']}*): {r['text']}"
                found.append({"domain": dom, "name": meta.get("name") or r["store"], "platform": "shopify",
                              "source_ref": url, "note": note,
                              "rating": r["rating"] if competitor else None})
                if len(found) >= limit:
                    state["seen_review_ids"] = sorted(seen_ids)
                    _save_state(state)
                    return found
            if not fresh:      # reached reviews we already processed
                break
    state["seen_review_ids"] = sorted(seen_ids)
    _save_state(state)
    return found
