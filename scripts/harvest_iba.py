"""
IBA approved transport operators harvest (TMS source).

Usage:
  python scripts/harvest_iba.py                  # all 799 operators, phones via Places
  python scripts/harvest_iba.py --max-pages 1    # smoke test (25 operators)
  python scripts/harvest_iba.py --state Maharashtra
  python scripts/harvest_iba.py --no-phones      # list only, store nothing (dry info)

Phone resolution uses the existing GOOGLE_MAPS_API_KEY; lookups are cached in
exports/iba_phone_cache.json so re-runs never re-spend quota.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.scrapers.iba_transporters import IbaTransportersScraper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="all")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--no-phones", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    scraper = IbaTransportersScraper(db, target_product="tms",
                                     resolve_phones=not args.no_phones)
    stats = scraper.run(args.state, city=None, max_pages=args.max_pages)
    print(f"IBA HARVEST RESULT: {stats}")
    print(f"PHONE RESOLUTION: {scraper.resolution}")
    db.close()


if __name__ == "__main__":
    main()
