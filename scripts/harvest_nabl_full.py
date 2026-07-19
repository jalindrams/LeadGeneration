"""
Micraft Growth Engine - FULL NABL Harvest
Pulls the ENTIRE public NABL accredited-lab directory:
    every state  x  every field (Calibration, Testing, Medical)

Each lab row carries a government-published contact person + direct mobile +
email. This is the highest-credibility source in the whole engine.

Resumable: progress is journaled to exports/nabl_harvest_progress.json, so an
interrupted run continues where it stopped. Safe to re-run.

Usage:
  python scripts/harvest_nabl_full.py                    # all states, all fields
  python scripts/harvest_nabl_full.py --fields calibration
  python scripts/harvest_nabl_full.py --reset            # ignore prior progress
"""

import argparse
import json
import os
import re
import sys
import time
import random
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from bs4 import BeautifulSoup

from app.database import SessionLocal
from app.models import Lead
from app.processing.dedup import compute_dedup_hash, normalize_phone
from app.processing.scorer import score_and_qualify
from app.utils.logger import setup_logging, get_logger

setup_logging()
log = get_logger("nabl_harvest")

BASE_URL = "https://nablwp.qci.org.in/laboratorysearchone"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}
PROGRESS_FILE = "exports/nabl_harvest_progress.json"

FIELD_VALUES = {"testing": "1", "calibration": "2", "medical": "3"}
# Which Micraft product each NABL field maps to
FIELD_PRODUCT = {"calibration": "calibration", "testing": "calibration", "medical": None}


def hidden(html, name):
    m = re.search(rf'id="{name}" value="([^"]*)"', html)
    return m.group(1) if m else ""


def state_options(html):
    m = re.search(r'MainContent_ddlstate".*?</select>', html, re.DOTALL)
    if not m:
        return []
    opts = re.findall(r'value="([^"]*)"[^>]*>([^<]*)<', m.group(0))
    # Drop placeholder + junk duplicate rows (dadar/Dadra typos)
    seen, out = set(), []
    for val, name in opts:
        name = name.strip()
        if val in ("0", "") or not name or name.lower() in ("dadar", "dadra"):
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append((val, name))
    return out


def parse_results(html, field):
    soup = BeautifulSoup(html, "html.parser")
    grid = None
    for table in soup.find_all("table"):
        head = table.find("tr")
        if head and "CAB Name" in head.get_text():
            grid = table
            break
    if grid is None:
        return []

    rows = grid.find_all("tr")
    headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]

    def col(name):
        for i, h in enumerate(headers):
            if name.lower() in h.lower():
                return i
        return None

    idx = {k: col(k) for k in ("CAB Name", "Contact Person", "Email", "Mobile",
                               "Address", "State", "City", "Status", "Discipline",
                               "Certificate Number", "Certificate Valid")}
    leads = []
    for row in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cells) < 10:
            continue

        def val(key):
            i = idx.get(key)
            return cells[i] if i is not None and i < len(cells) else ""

        name = val("CAB Name").title()
        if len(name) < 3:
            continue
        phone = re.sub(r"[^\d]", "", val("Mobile"))
        leads.append({
            "company_name": name,
            "full_name": val("Contact Person").title() or None,
            "phone": phone if len(phone) >= 10 else None,
            "email": (val("Email") or "").lower() or None,
            "location": f"{val('City')}, {val('State')}".strip(", "),
            "industry": f"{field.title()} Laboratory (NABL accredited)",
            "product_category": (val("Discipline") or "")[:290],
            "gst_number": None,
            "_status_text": val("Status"),
            "_cert": val("Certificate Number"),
        })
    return leads


def load_progress(reset):
    if reset or not os.path.exists(PROGRESS_FILE):
        return {"done": []}
    try:
        return json.load(open(PROGRESS_FILE))
    except Exception:
        return {"done": []}


def save_progress(prog):
    os.makedirs("exports", exist_ok=True)
    json.dump(prog, open(PROGRESS_FILE, "w"), indent=1)


def store_leads(db, leads, field, seen_hashes):
    """Store leads one-by-one so a single dupe/constraint can't abort the batch.
    seen_hashes is a run-level set guarding against the same lab appearing twice
    (multiple certificates, or accredited under both Calibration and Testing)."""
    product = FIELD_PRODUCT.get(field)
    stored = dup = 0
    for ld in leads:
        if not ld.get("phone"):
            continue
        # Only accreditation-approved labs are live businesses
        if "approved" not in (ld.get("_status_text") or "").lower():
            continue

        dedup_hash = compute_dedup_hash(ld["company_name"], ld.get("phone"),
                                        None, ld.get("location"))
        if dedup_hash in seen_hashes:
            dup += 1
            continue
        if db.query(Lead).filter(Lead.dedup_hash == dedup_hash).first():
            seen_hashes.add(dedup_hash)
            dup += 1
            continue

        eval_data = dict(ld, scraped_at=datetime.utcnow(), target_product=product)
        ev = score_and_qualify(eval_data)
        lead = Lead(
            company_name=ld["company_name"], full_name=ld.get("full_name"),
            title=None, phone=ld.get("phone"), email=ld.get("email"),
            location=ld.get("location"), industry=ld.get("industry"),
            product_category=ld.get("product_category"),
            source="nabl", target_product=product,
            status="qualified" if ev["qualified"] else "raw",
            score=ev["score"], dedup_hash=dedup_hash,
            scraped_at=datetime.utcnow(), lead_created_at=datetime.utcnow(),
        )
        db.add(lead)
        try:
            db.commit()
            seen_hashes.add(dedup_hash)
            stored += 1
        except Exception:
            db.rollback()  # lost a race on the unique hash — treat as dup
            seen_hashes.add(dedup_hash)
            dup += 1
    return stored, dup


def main():
    parser = argparse.ArgumentParser(description="Full NABL directory harvest")
    parser.add_argument("--fields", default="calibration,testing,medical",
                        help="Comma list of: calibration,testing,medical")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip() in FIELD_VALUES]
    prog = load_progress(args.reset)
    done = set(tuple(x) for x in prog["done"])

    db = SessionLocal()
    grand_stored = grand_dup = 0
    seen_hashes = set()
    try:
        with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True,
                          verify=False) as client:
            r1 = client.get(BASE_URL)
            states = state_options(r1.text)
            log.info("harvest_start", states=len(states), fields=fields)
            print(f"Harvesting {len(states)} states x {len(fields)} fields "
                  f"= {len(states) * len(fields)} queries")

            for field in fields:
                for state_val, state_name in states:
                    key = (field, state_name)
                    if key in done:
                        continue
                    try:
                        # Fresh tokens each POST (ASP.NET requirement)
                        page = client.get(BASE_URL)
                        payload = {
                            "__VIEWSTATE": hidden(page.text, "__VIEWSTATE"),
                            "__VIEWSTATEGENERATOR": hidden(page.text, "__VIEWSTATEGENERATOR"),
                            "__EVENTVALIDATION": hidden(page.text, "__EVENTVALIDATION"),
                            "ctl00$MainContent$ddlstate": state_val,
                            "ctl00$MainContent$ddlLabType": FIELD_VALUES[field],
                            "ctl00$MainContent$ddlLabStatus": "0",
                            "ctl00$MainContent$btnSearch": "Search",
                        }
                        resp = client.post(BASE_URL, data=payload)
                        leads = parse_results(resp.text, field) if resp.status_code == 200 else []
                        stored, dup = store_leads(db, leads, field, seen_hashes)
                        grand_stored += stored
                        grand_dup += dup
                        print(f"  {field:12s} {state_name:28s} found={len(leads):4d} "
                              f"stored={stored:4d} dup={dup:4d}")
                        log.info("state_done", field=field, state=state_name,
                                 found=len(leads), stored=stored, dup=dup)
                    except Exception as e:
                        print(f"  {field:12s} {state_name:28s} ERROR {str(e)[:60]}")
                        log.error("state_error", field=field, state=state_name, error=str(e))
                        continue

                    done.add(key)
                    prog["done"] = [list(x) for x in done]
                    save_progress(prog)
                    time.sleep(random.uniform(1.5, 3.5))  # be polite to gov servers

        print(f"\nHARVEST COMPLETE: stored={grand_stored} duplicates={grand_dup}")
        total = db.query(Lead).filter(Lead.source == "nabl").count()
        print(f"Total NABL leads in DB: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
