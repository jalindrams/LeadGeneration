"""
Phase 0 spike S1 - Shopify App Store reviews of Indian shipping apps.

Measures: how many reviewing merchants are Indian stores, and how many
resolve to a domain. Read-only, polite (1.2s delay), public pages only.

  python scripts/spikes/s1_shopify_reviews.py --pages 6
Output: exports/spike_s1_reviews.json
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
APPS = ["nimbuspost", "ithink-logistics", "shipmozo", "xpressbees", "shiprocket-engage"]


def parse_page(html: str, app: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for rev in soup.select("[data-merchant-review]"):
        stars = rev.select_one("[aria-label$='stars']")
        rating = None
        if stars:
            m = re.match(r"(\d)", stars.get("aria-label", ""))
            rating = int(m.group(1)) if m else None
        # sidebar column holds: store name, country, time using app
        side = rev.select_one("div.lg\\:tw-order-1") or rev
        lines = [t.strip() for t in side.stripped_strings if t.strip()]
        out.append({"app": app, "rating": rating, "lines": lines[:6],
                    "id": rev.get("data-review-content-id")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=6)
    args = ap.parse_args()
    rows = []
    for app in APPS:
        for p in range(1, args.pages + 1):
            r = requests.get(f"https://apps.shopify.com/{app}/reviews?page={p}",
                             headers=HEADERS, timeout=25)
            if r.status_code != 200:
                break
            page_rows = parse_page(r.text, app)
            if not page_rows:
                break
            rows.extend(page_rows)
            time.sleep(1.2)
        print(f"{app}: {sum(1 for x in rows if x['app'] == app)} reviews")
    os.makedirs("exports", exist_ok=True)
    with open("exports/spike_s1_reviews.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    print("total", len(rows))
    for x in rows[:8]:
        print(x["app"], x["rating"], x["lines"])


if __name__ == "__main__":
    sys.exit(main())
