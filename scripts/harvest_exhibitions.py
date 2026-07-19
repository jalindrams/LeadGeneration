"""
Micraft Growth Engine - Exhibition PDF Harvester

Downloads and processes exhibitor lists from trade shows.
Each exhibition = one PDF with company listings → high-quality verified leads.

Usage:
  python scripts/harvest_exhibitions.py --list                          # show configured exhibitions
  python scripts/harvest_exhibitions.py --exhibition analytica_lab_india_2026
  python scripts/harvest_exhibitions.py --exhibition analytica_lab_india_2025
  python scripts/harvest_exhibitions.py --all                           # run all exhibitions
  python scripts/harvest_exhibitions.py --exhibition analytica_lab_india_2026 --no-phones
  python scripts/harvest_exhibitions.py --exhibition analytica_lab_india_2026 --dry-run
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.scrapers.exhibition_pdf import ExhibitionPdfScraper, EXHIBITION_CONFIGS
from app.utils.logger import get_logger

log = get_logger("harvest_exhibitions")


def run_exhibition(key: str, db, resolve_phones: bool = True, dry_run: bool = False):
    config = EXHIBITION_CONFIGS[key]
    print(f"\n{'='*60}")
    print(f"Exhibition : {config['name']}")
    print(f"Product    : {config['target_product']}")
    print(f"Phones     : {'yes' if resolve_phones else 'no (--no-phones)'}")
    print(f"Dry run    : {'yes' if dry_run else 'no'}")
    print(f"{'='*60}")

    scraper = ExhibitionPdfScraper(db, exhibition_key=key, resolve_phones=resolve_phones)
    leads = scraper.scrape()

    stored = skipped = errors = 0
    for lead in leads:
        if dry_run:
            print(f"  [DRY] {lead['company_name'][:50]} | {lead.get('phone') or 'no phone'}")
            stored += 1
        else:
            ok, _ = scraper.store_lead(lead)
            if ok:
                stored += 1
            else:
                skipped += 1

    print(f"\nResults for {config['name']}:")
    print(f"  Extracted  : {len(leads)}")
    print(f"  {'Would store' if dry_run else 'Stored'}: {stored}")
    if not dry_run:
        print(f"  Skipped    : {skipped}")
    print(f"  Stats      : {scraper.stats}")


def main():
    parser = argparse.ArgumentParser(description="Harvest exhibition PDF exhibitor lists")
    parser.add_argument("--list", action="store_true", help="List configured exhibitions")
    parser.add_argument("--exhibition", help="Exhibition key to harvest")
    parser.add_argument("--all", action="store_true", help="Harvest all configured exhibitions")
    parser.add_argument("--no-phones", action="store_true", help="Skip phone resolution")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()

    if args.list:
        print("\nConfigured exhibitions:")
        for key, config in EXHIBITION_CONFIGS.items():
            print(f"  {key:<35s} → {config['name']} ({config['target_product']})")
        return

    targets = []
    if args.all:
        targets = list(EXHIBITION_CONFIGS.keys())
    elif args.exhibition:
        if args.exhibition not in EXHIBITION_CONFIGS:
            print(f"Unknown exhibition '{args.exhibition}'. Run --list to see options.")
            sys.exit(1)
        targets = [args.exhibition]
    else:
        parser.print_help()
        return

    db = SessionLocal()
    try:
        for key in targets:
            run_exhibition(key, db, resolve_phones=not args.no_phones, dry_run=args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()
