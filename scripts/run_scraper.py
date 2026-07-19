"""
Micraft Growth Engine - Campaign Scraper Runner
Every scrape is a PRODUCT CAMPAIGN: pick the Micraft product, and the product's
ICP profile drives search queries, cities, decision-maker titles, turnover band,
and scoring. Leads are tagged with target_product for per-product funnels.

Usage:
    python scripts/run_scraper.py                          # interactive: asks product, target, cities
    python scripts/run_scraper.py --product mes            # MES campaign, profile defaults
    python scripts/run_scraper.py --product tms --target 50 --city Mumbai
    python scripts/run_scraper.py --product dms --source google_maps --max-pages 3
    python scripts/run_scraper.py --product mes --query "forging company"   # override queries
"""

import argparse
import sys
import os
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal
from app.products import PRODUCT_PROFILES, get_profile, product_menu
from app.utils.logger import setup_logging, get_logger

setup_logging()
log = get_logger("run_scraper")


def run_source(db, source: str, product: str, city: str, queries: list[str],
               max_pages: int, remaining_target) -> dict:
    """Run one scraper for one city. Stops early once remaining_target hits 0."""
    if source == "indiamart":
        from app.scrapers.indiamart import IndiaMartScraper
        scraper = IndiaMartScraper(db, target_product=product)
        icon = "[IM]"
    elif source == "tradeindia":
        from app.scrapers.tradeindia import TradeIndiaScraper
        scraper = TradeIndiaScraper(db, target_product=product)
        icon = "[TI]"
    elif source == "nabl":
        from app.scrapers.nabl import NablScraper
        scraper = NablScraper(db, target_product=product)
        icon = "[NABL]"
    elif source == "oem_dealers":
        from app.scrapers.oem_dealers import OemDealerScraper
        scraper = OemDealerScraper(db, target_product=product)
        icon = "[OEM]"
    elif source == "aipma":
        from app.scrapers.aipma import AipmaScraper
        scraper = AipmaScraper(db, target_product=product)
        icon = "[AIPMA]"
    elif source == "iba_transporters":
        from app.scrapers.iba_transporters import IbaTransportersScraper
        scraper = IbaTransportersScraper(db, target_product=product)
        icon = "[IBA]"
    else:
        from app.scrapers.google_maps import GoogleMapsScraper
        scraper = GoogleMapsScraper(db, target_product=product)
        icon = "[GM]"

    total = {"found": 0, "stored": 0, "duplicate": 0, "errors": 0}
    if source == "nabl":
        queries = ["calibration"]  # one state-wide directory pull per city
    elif source == "oem_dealers":
        queries = ["all"]  # sitemap pull; city arg filters the URL segment
    elif source in ("aipma", "iba_transporters"):
        queries = ["all"]  # full-directory pulls; scorer segments downstream
    for query in queries:
        if remaining_target is not None and remaining_target - total["stored"] <= 0:
            break
        print(f"\n{icon} '{query}' in {city}")
        print("-" * 50)
        try:
            stats = scraper.run(query, city, max_pages)
            for key in total:
                total[key] += stats.get(key, 0)
            print(f"   Found: {stats['found']} | Stored: {stats['stored']} | "
                  f"Duplicates: {stats['duplicate']} | Errors: {stats['errors']}")
        except Exception as e:
            print(f"   ERROR: {str(e)[:200]}")
            log.error("scrape_run_error", source=source, city=city, query=query, error=str(e))
        time.sleep(5 if source == "indiamart" else 3)
    return total


def main():
    parser = argparse.ArgumentParser(description="Micraft Growth Engine - Campaign Scraper")
    parser.add_argument("--product", choices=list(PRODUCT_PROFILES), default=None,
                        help="Which Micraft product this campaign targets (asked interactively if omitted)")
    parser.add_argument("--source",
                        choices=["indiamart", "google_maps", "tradeindia", "nabl",
                                 "oem_dealers", "aipma", "iba_transporters",
                                 "exhibition_pdf", "d2c_brands", "all"],
                        default="all")
    parser.add_argument("--city", default=None,
                        help="Target city, 'all' for the product's cities (default: product profile cities)")
    parser.add_argument("--query", default=None, help="Override the product's search queries")
    parser.add_argument("--target", type=int, default=None,
                        help="Stop after storing ~N new leads (default: product's daily target)")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--yes", action="store_true", help="Non-interactive: accept all defaults")
    args = parser.parse_args()

    # --- Product selection (the campaign) ---
    product_key = args.product
    if not product_key:
        if args.yes or not sys.stdin.isatty():
            product_key = "mes"  # core product default for unattended runs
        else:
            product_key = product_menu()
    profile = get_profile(product_key)

    # --- Campaign parameters from profile, overridable ---
    if args.city and args.city.lower() != "all":
        cities = [args.city]
    else:
        cities = profile["cities"]

    queries = [args.query] if args.query else profile["search_queries"]
    target = args.target if args.target is not None else profile["daily_target"]
    max_pages = args.max_pages or settings.SCRAPE_MAX_PAGES
    band = profile["turnover_band_crore"]

    print("=" * 64)
    print("MICRAFT GROWTH ENGINE - Product Campaign")
    print("=" * 64)
    print(f"Product:   {profile['name']}")
    print(f"Pitch:     {profile['pitch']}")
    print(f"Turnover:  Rs.{band[0]}-{band[1]} Cr sweet spot (scored, not hard-filtered)")
    print(f"Decision-makers: Owner + {', '.join(profile['decision_makers']['senior'] + profile['decision_makers']['manager'])}")
    print(f"Cities:    {', '.join(cities)}")
    print(f"Queries:   {len(queries)}")
    print(f"Target:    ~{target} new leads this run")
    print(f"Source:    {args.source} | Max pages/query: {max_pages}")
    print(f"Started:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    if not args.yes and sys.stdin.isatty():
        go = input("\nProceed? [Y/n]: ").strip().lower()
        if go == "n":
            print("Cancelled.")
            return

    db = SessionLocal()
    grand = {"found": 0, "stored": 0, "duplicate": 0, "errors": 0}
    try:
        for city in cities:
            remaining = None if not target else target - grand["stored"]
            if remaining is not None and remaining <= 0:
                print(f"\nTarget of {target} stored leads reached — stopping.")
                break
            print(f"\n{'='*64}\nCITY: {city}\n{'='*64}")

            if args.source == "all":
                sources = ["indiamart", "google_maps", "tradeindia"]
                # NABL only makes sense for calibration campaigns
                if product_key == "calibration":
                    sources.insert(0, "nabl")
            else:
                sources = [args.source]
            for src in sources:
                remaining = None if not target else target - grand["stored"]
                if remaining is not None and remaining <= 0:
                    break
                stats = run_source(db, src, product_key, city, queries, max_pages, remaining)
                for key in grand:
                    grand[key] += stats.get(key, 0)
    finally:
        db.close()

    print(f"\n{'='*64}")
    print(f"CAMPAIGN SUMMARY — {profile['name']}")
    print(f"{'='*64}")
    print(f"Total Found:      {grand['found']}")
    print(f"Total Stored:     {grand['stored']}  (tagged target_product='{product_key}')")
    print(f"Total Duplicates: {grand['duplicate']}")
    print(f"Total Rejected:   {grand['errors']}  (no phone / known-bad phone / junk name)")
    print(f"Completed:        {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nNext: python scripts/run_enrichment.py --limit {max(50, grand['stored'])}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
