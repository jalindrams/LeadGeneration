"""
S4b - Tranco top-1M domain list (free, refreshed daily upstream).
.in/.co.in domains: ~10% are Indian Shopify stores (Phase 0).
.com domains: probed in daily slices; only INR Shopify stores are kept.
Progress cursor persists so each run continues where the last stopped.
"""
import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from app.pipeline import fetch

SOURCE_IN = "tranco_in"
SOURCE_COM = "tranco_com"
LIST_URL = "https://tranco-list.eu/top-1m.csv.zip"
CACHE = Path("exports") / "tranco_top1m.csv"
STATE = Path("exports") / "tranco_state.json"
MAX_AGE_DAYS = 7


def _domains() -> list[str]:
    if not CACHE.exists() or time.time() - CACHE.stat().st_mtime > MAX_AGE_DAYS * 86400:
        r = requests.get(LIST_URL, timeout=180)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_bytes(z.read(z.namelist()[0]))
    return [line.split(",", 1)[1].strip() for line in CACHE.read_text().splitlines() if "," in line]


def _probe(domain: str) -> dict | None:
    meta = fetch.get_json(f"https://{domain}/meta.json", timeout=7)
    if isinstance(meta, dict) and "myshopify_domain" in meta and meta.get("currency") == "INR":
        return {"domain": domain, "name": meta.get("name"), "platform": "shopify",
                "source_ref": "tranco top-1m"}
    return None


def discover(db, limit: int = 1500, source: str = SOURCE_IN) -> list[dict]:
    """limit = number of domains PROBED this run (not stores returned)."""
    doms = _domains()
    if source == SOURCE_IN:
        pool = [d for d in doms if d.endswith((".in", ".co.in"))]
    else:
        pool = [d for d in doms if d.endswith(".com")]
    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {}
    cursor = state.get(source, 0)
    if cursor >= len(pool):
        return []
    chunk = pool[cursor:cursor + limit]
    with ThreadPoolExecutor(16) as ex:
        found = [x for x in ex.map(_probe, chunk) if x]
    state[source] = cursor + len(chunk)
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state))
    return found
