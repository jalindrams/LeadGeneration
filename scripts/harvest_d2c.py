"""
Micraft Growth Engine - D2C Brand Harvester (Ecom / Shiplystic)

Finds Indian D2C brands on Shopify/WooCommerce/Magento and stores them
as ecom leads for the Shiplystic product.

Usage:
  python scripts/harvest_d2c.py                          # full harvest (seed + dpiit)
  python scripts/harvest_d2c.py --source seed            # seed list only (~120 brands)
  python scripts/harvest_d2c.py --source dpiit           # DPIIT Startup India only
  python scripts/harvest_d2c.py --source cse --use-cse   # Google CSE (needs GOOGLE_CSE_ID)
  python scripts/harvest_d2c.py --source seed --no-phones
  python scripts/harvest_d2c.py --source seed --dry-run  # preview only
  python scripts/harvest_d2c.py --source seed --max-brands 20  # smoke test

Setup for Google CSE (optional):
  1. Go to https://programmablesearchengine.google.com/
  2. Create a new search engine, set to search the entire web
  3. Copy the "Search engine ID"
  4. Add to .env: GOOGLE_CSE_ID=your_cse_id_here
  Then run with --use-cse to activate it.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.scrapers.d2c_brands import D2cBrandsScraper
from app.utils.logger import get_logger

log = get_logger("harvest_d2c")


def main():
    parser = argparse.ArgumentParser(description="Harvest D2C brand leads for Shiplystic")
    parser.add_argument("--source", default="all",
                        choices=["all", "seed", "dpiit", "cse"],
                        help="Data source to use (default: all)")
    parser.add_argument("--no-phones", action="store_true",
                        help="Skip phone resolution (faster, uses 0 API quota)")
    parser.add_argument("--use-cse", action="store_true",
                        help="Enable Google Custom Search (needs GOOGLE_CSE_ID in .env)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show extracted leads, do not write to DB")
    parser.add_argument("--max-brands", type=int, default=None,
                        help="Limit number of brands to process (smoke test)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        scraper = D2cBrandsScraper(
            db,
            target_product="ecom",
            resolve_phones=not args.no_phones,
            use_cse=args.use_cse,
        )

        print(f"\nD2C Brand Harvester")
        print(f"  Source     : {args.source}")
        print(f"  Phones     : {'yes' if not args.no_phones else 'no'}")
        print(f"  CSE        : {'yes' if args.use_cse else 'no'}")
        print(f"  Dry run    : {'yes' if args.dry_run else 'no'}")
        print(f"  Max brands : {args.max_brands or 'unlimited'}")

        leads = scraper.scrape(search_query=args.source)

        if args.max_brands:
            leads = leads[:args.max_brands]

        print(f"\nPlatform breakdown:")
        for platform, count in sorted(scraper.platform_stats.items(), key=lambda x: -x[1]):
            print(f"  {platform:<20s} : {count}")

        stored = skipped = 0
        for lead in leads:
            if args.dry_run:
                platform_tag = lead.get("product_category", "")[:40]
                print(f"  [DRY] {lead['company_name'][:45]:<45s} | "
                      f"{lead.get('phone') or 'no phone':<15s} | {platform_tag}")
                stored += 1
            else:
                ok, _ = scraper.store_lead(lead)
                if ok:
                    stored += 1
                else:
                    skipped += 1

        print(f"\nFinal results:")
        print(f"  Leads found: {len(leads)}")
        print(f"  {'Would store' if args.dry_run else 'Stored'}: {stored}")
        if not args.dry_run:
            print(f"  Skipped (dup/error): {skipped}")
        print(f"  Scraper stats: {scraper.stats}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
