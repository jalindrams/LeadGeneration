"""
S6 - Amazon.in marketplace sellers (owner approved 2026-11-11, LOW VOLUME, owner
accepts the terms-of-service risk). Amazon must display each seller's business
name and address; we read that, then the pipeline finds a phone via the seller's
own website or the free-tier Places lookup.

Guardrails:
  - at most MAX_PAGES page fetches per run, 4-8 s apart
  - if Amazon returns a CAPTCHA or robot check, the run stops immediately
    (CAPTCHAs are never solved or bypassed)
"""
import random
import re
import time

from app.pipeline import fetch

SOURCE = "amazon_sellers"
MAX_PAGES = 40
CATEGORIES = ["handmade jewellery", "kurti for women", "ayurvedic hair oil", "scented candles",
              "organic honey", "home decor handicraft", "leather wallet men", "kids wooden toys",
              "herbal face pack", "masala spices", "dog treats", "printed bedsheet cotton"]


class Blocked(RuntimeError):
    pass


def _get(url: str) -> str:
    time.sleep(random.uniform(4, 8))
    status, html, _ = fetch.get(url, timeout=20)
    low = html.lower()
    challenge = status == 200 and len(html) < 10_000   # tiny interstitial = bot challenge page
    if (status in (503, 429) or challenge or "captcha" in low or "robot check" in low
            or "api-services-support@amazon" in low):
        raise Blocked(f"Amazon blocked the request (HTTP {status}); stopping S6 run")
    return html if status == 200 else ""


def parse_seller(html: str) -> dict | None:
    text = re.sub(r"<[^>]+>", "\n", html)
    text = re.sub(r"\n\s*\n+", "\n", text)
    name = re.search(r"Business Name:\s*\n?\s*([^\n]+)", text)
    if not name:
        return None
    addr = re.search(r"Business Address:\s*\n((?:[^\n]+\n){1,6})", text)
    lines = [l.strip() for l in (addr.group(1).splitlines() if addr else []) if l.strip()]
    pin = next((re.search(r"\b\d{6}\b", l).group(0) for l in lines if re.search(r"\b\d{6}\b", l)), None)
    city = lines[-3] if len(lines) >= 3 else (lines[0] if lines else None)
    return {"business_name": name.group(1).strip(), "address": ", ".join(lines),
            "pincode": pin, "city": city}


def discover(db, limit: int = 30, source: str = SOURCE) -> list[dict]:
    pages, found, seen = 0, [], set()
    try:
        for cat in random.sample(CATEGORIES, len(CATEGORIES)):
            if pages >= MAX_PAGES or len(found) >= limit:
                break
            html = _get("https://www.amazon.in/s?k=" + cat.replace(" ", "+"))
            pages += 1
            asins = list(dict.fromkeys(re.findall(r'data-asin="([A-Z0-9]{10})"', html)))[:6]
            for asin in asins:
                if pages >= MAX_PAGES or len(found) >= limit:
                    break
                prod = _get(f"https://www.amazon.in/dp/{asin}")
                pages += 1
                m = re.search(r"[?&]seller=([A-Z0-9]{10,16})", prod)
                if not m or m.group(1) in seen:
                    continue
                seen.add(m.group(1))
                sp = _get(f"https://www.amazon.in/sp?seller={m.group(1)}")
                pages += 1
                info = parse_seller(sp)
                if not info:
                    continue
                found.append({
                    "domain": f"amazon-seller-{m.group(1).lower()}.marketplace",
                    "name": info["business_name"], "platform": "marketplace",
                    "source_ref": f"https://www.amazon.in/sp?seller={m.group(1)}",
                    "note": f"Amazon.in seller in '{cat}'. Address: {info['address']}",
                    "city": info["city"],
                })
    except Blocked as e:
        if not found:          # surface it as a failed run on the dashboard
            raise
        return found
    return found
