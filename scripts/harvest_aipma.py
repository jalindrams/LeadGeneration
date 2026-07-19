"""
Full AIPMA member-directory harvest (MES source).

Usage:
  python scripts/harvest_aipma.py                    # full directory, manufacturers only
  python scripts/harvest_aipma.py --max-pages 2      # smoke test
  python scripts/harvest_aipma.py --include-traders  # also store TRADER category

Re-runs are cheap: dedup skips existing members.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.scrapers.aipma import AipmaScraper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--include-traders", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    scraper = AipmaScraper(db, target_product="mes",
                           include_traders=args.include_traders)
    stats = scraper.run("all", city=None, max_pages=args.max_pages)
    print(f"AIPMA HARVEST RESULT: {stats} | traders skipped: {scraper.skipped_traders}")
    db.close()


if __name__ == "__main__":
    main()
