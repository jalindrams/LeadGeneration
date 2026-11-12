"""
Phase 0 spike S2 - resolve store names to domains (zero-API guessing, verified
against Shopify /meta.json), then measure contact extraction and sizing signals.

Read-only, polite, public pages only. Input: exports/spike_s1_reviews.json
  python scripts/spikes/s2_resolve_and_extract.py
Output: exports/spike_s2_stores.json + printed funnel
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

import requests

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
     "Accept-Language": "en-IN,en;q=0.9"}
TLDS = [".com", ".in", ".co.in", ".co", ".store", ".shop"]
PAGES = ["", "/policies/contact-information", "/pages/contact-us", "/pages/contact",
         "/policies/refund-policy", "/policies/shipping-policy", "/policies/terms-of-service"]
MOBILE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?|0)?([6-9]\d{4}[\s\-]?\d{5})(?!\d)")
GSTIN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
WA = re.compile(r"(?:wa\.me/|api\.whatsapp\.com/send\?phone=|whatsapp://send\?phone=)\+?(\d{10,13})")
TEL = re.compile(r'href=["\']tel:([^"\']+)["\']')
COMPETITORS = ["shiprocket", "shipway", "nimbuspost", "ithinklogistics", "delhivery", "shipmozo",
               "pickrr", "clickpost", "shipyaari", "xpressbees", "ecomexpress", "bluedart", "dtdc"]


def slugs(name: str) -> list[str]:
    base = re.sub(r"\.(com|in|co|co\.in)$", "", name.lower().strip())
    a = re.sub(r"[^a-z0-9]", "", base)
    b = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    out = []
    for s in (a, b):
        if s and s not in out and len(s) >= 3:
            out.append(s)
    return out


def get(url, timeout=9):
    try:
        r = requests.get(url, headers=H, timeout=timeout, allow_redirects=True)
        return r
    except Exception:
        return None


def digits(m):
    return re.sub(r"\D", "", m)


def clean_mobiles(text: str) -> list[str]:
    found = []
    for m in MOBILE.finditer(text):
        d = digits(m.group(1))
        if len(d) == 10 and d not in found and len(set(d)) > 3:
            found.append(d)
    return found


def resolve(name: str):
    for s in slugs(name):
        for tld in TLDS:
            dom = s + tld
            r = get(f"https://{dom}/meta.json", timeout=7)
            if r is None or r.status_code != 200:
                continue
            try:
                meta = r.json()
            except Exception:
                continue
            if not isinstance(meta, dict) or "name" not in meta:
                continue
            sim = SequenceMatcher(None, re.sub(r"[^a-z0-9]", "", name.lower()),
                                  re.sub(r"[^a-z0-9]", "", str(meta.get("name", "")).lower())).ratio()
            if sim >= 0.6 or s in re.sub(r"[^a-z0-9]", "", str(meta.get("myshopify_domain", "")).lower()):
                return dom, meta, round(sim, 2)
    return None, None, 0


def extract(dom: str) -> dict:
    texts, html_all = [], ""
    for p in PAGES:
        r = get(f"https://{dom}{p}")
        if r is not None and r.status_code == 200 and len(r.text) > 500:
            html_all += r.text
            texts.append(re.sub(r"<[^>]+>", " ", r.text))
        time.sleep(0.3)
    plain = " ".join(texts)
    wa = sorted({digits(x)[-10:] for x in WA.findall(html_all)})
    tel = sorted({digits(x)[-10:] for x in TEL.findall(html_all) if len(digits(x)) >= 10})
    mob = [m for m in clean_mobiles(plain) if m not in wa and m not in tel]
    gst = sorted(set(GSTIN.findall(html_all)))
    grievance = bool(re.search(r"grievance\s+officer", plain, re.I))
    comp = sorted({c for c in COMPETITORS if c in html_all.lower()})
    return {"whatsapp": wa, "tel": tel, "text_mobiles": mob[:3], "gstin": gst[:2],
            "grievance_officer_text": grievance, "competitor_hits": comp}


def work(row):
    name = row["name"]
    dom, meta, sim = resolve(name)
    res = {"name": name, "rating": row["rating"], "domain": dom, "match": sim}
    if not dom:
        return res
    res["country"] = meta.get("country")
    res["currency"] = meta.get("currency")
    res["city"] = meta.get("city")
    res["products"] = meta.get("published_products_count")
    res.update(extract(dom))
    return res


def main():
    rows = json.load(open("exports/spike_s1_reviews.json", encoding="utf-8"))
    uniq = {}
    for r in rows:
        uniq.setdefault(r["lines"][0], {"name": r["lines"][0], "rating": r["rating"]})
    items = list(uniq.values())
    with ThreadPoolExecutor(max_workers=8) as ex:
        out = list(ex.map(work, items))
    json.dump(out, open("exports/spike_s2_stores.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    n = len(out)
    res = [o for o in out if o.get("domain")]
    india = [o for o in res if (o.get("country") in ("India", "IN") or o.get("currency") == "INR")]
    anym = [o for o in india if o.get("whatsapp") or o.get("tel") or o.get("text_mobiles")]
    wa = [o for o in india if o.get("whatsapp")]
    mob = [o for o in india if o.get("whatsapp") or o.get("text_mobiles")]
    gst = [o for o in india if o.get("gstin")]
    print(f"names={n} resolved_to_shopify_domain={len(res)} ({len(res)*100//max(n,1)}%)")
    print(f"  india_confirmed={len(india)}")
    print(f"  any phone-like contact={len(anym)}  mobile(whatsapp or text)={len(mob)}  whatsapp={len(wa)}  gstin={len(gst)}")
    print(f"  grievance officer text={sum(1 for o in india if o.get('grievance_officer_text'))}")
    print(f"  competitor script on site={sum(1 for o in india if o.get('competitor_hits'))}")
    prods = sorted(o["products"] for o in india if isinstance(o.get("products"), int))
    if prods:
        print(f"  product count median={prods[len(prods)//2]} min={prods[0]} max={prods[-1]} n={len(prods)}")


if __name__ == "__main__":
    sys.exit(main())
