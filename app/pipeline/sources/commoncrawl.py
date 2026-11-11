"""
S4 - Common Crawl URL index: Indian store URLs (/products/, /collections/,
/product-category/) on .in domains. The index was down (HTTP 504) in Phase 0;
this source fails soft and records the error so the dashboard shows it.
"""
import json
import re
from pathlib import Path

import requests

SOURCE = "commoncrawl"
STATE = Path("exports") / "commoncrawl_state.json"
PATTERNS = ["*.in/products/*", "*.in/collections/*", "*.co.in/products/*", "*.in/product-category/*"]


def discover(db, limit: int = 500, source: str = SOURCE) -> list[dict]:
    info = requests.get("https://index.commoncrawl.org/collinfo.json", timeout=60)
    info.raise_for_status()
    crawl = info.json()[0]["id"]
    try:
        state = json.loads(STATE.read_text())
    except Exception:
        state = {}
    found, seen = [], set()
    for pat in PATTERNS:
        key = f"{crawl}:{pat}"
        page = state.get(key, 0)
        r = requests.get(f"https://index.commoncrawl.org/{crawl}-index",
                         params={"url": pat, "output": "json", "fl": "url", "page": page,
                                 "filter": "status:200"}, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"commoncrawl index HTTP {r.status_code} for {pat}")
        for line in r.text.splitlines():
            try:
                u = json.loads(line)["url"]
            except Exception:
                continue
            dom = re.sub(r"^https?://(www\.)?", "", u).split("/")[0].lower()
            if dom and dom not in seen:
                seen.add(dom)
                found.append({"domain": dom, "source_ref": f"commoncrawl {crawl}"})
        state[key] = page + 1
        if len(found) >= limit:
            break
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state))
    return found[:limit]
