"""
Paid discovery: Google results via Serper (replaces the blocked free search, S3).
POST https://google.serper.dev/search, header X-API-KEY, body {q, gl, num, page};
results in response["organic"][i]["link"]. Cost assumption: $1 per 1,000 queries
(~₹0.09/query), set SERPER_COST_PER_QUERY_INR to the price you actually pay.
Enabled only when SERPER_API_KEY and PAID_SERPER_CAP_INR are set.
"""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.pipeline.paid import ledger

SOURCE = "serper_search"
PROVIDER = "serper"
STATE = Path("exports") / "serper_state.json"
SKIP = re.compile(r"(amazon|flipkart|myntra|meesho|ajio|nykaa|instagram|facebook|youtube|"
                  r"justdial|indiamart|tradeindia|linkedin|wikipedia|quora|reddit|pinterest|google)\.")
CATEGORIES = ["handmade jewellery", "ethnic kurti", "ayurvedic skincare", "organic food", "scented candles",
              "home decor", "leather bags", "kids clothing", "pet food", "herbal hair oil", "saree",
              "footwear", "tea", "spices masala", "gifts hampers", "fitness supplements", "phone covers",
              "art prints", "bedsheets", "perfume attar"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Jaipur", "Surat", "Ahmedabad", "Pune", "Hyderabad",
          "Kolkata", "Chennai", "Lucknow", "Indore", "Ludhiana", "Kochi", "Chandigarh"]
TEMPLATES = ['buy {cat} online india "cash on delivery" {city}', '{cat} online store {city} "free shipping"']


def enabled() -> bool:
    return bool(os.getenv("SERPER_API_KEY")) and ledger.provider_cap(PROVIDER) > 0


def _queries():
    for t in TEMPLATES:
        for cat in CATEGORIES:
            for city in CITIES:
                yield t.format(cat=cat, city=city)


def discover(db, limit: int = 200, source: str = SOURCE) -> list[dict]:
    """limit = number of queries this run."""
    if not enabled():
        raise RuntimeError("serper disabled: set SERPER_API_KEY and PAID_SERPER_CAP_INR")
    cost = float(os.getenv("SERPER_COST_PER_QUERY_INR", "0.09"))
    try:
        cursor = json.loads(STATE.read_text()).get("cursor", 0)
    except Exception:
        cursor = 0
    qs = list(_queries())
    found, seen = [], set()
    done = 0
    for q in qs[cursor:cursor + limit]:
        ledger.charge(PROVIDER, 1, cost, db=db)
        r = requests.post("https://google.serper.dev/search", timeout=30,
                          headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"},
                          json={"q": q, "gl": "in", "hl": "en", "num": 20})
        done += 1
        if r.status_code != 200:
            continue
        for item in r.json().get("organic", []):
            host = urlparse(item.get("link", "")).netloc.lower().removeprefix("www.")
            if host and host not in seen and not SKIP.search(host):
                seen.add(host)
                found.append({"domain": host, "name": item.get("title", "")[:200], "source_ref": f"serper: {q}"})
    global _pending
    _pending = {"cursor": (cursor + done) % max(len(qs), 1)}
    return found


_pending: dict | None = None


def commit_state():
    global _pending
    if _pending is not None:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(_pending))
        _pending = None
