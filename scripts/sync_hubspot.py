"""
Micraft Growth Engine - HubSpot Batch Sync (Phase 3)
Pushes qualified (and optionally enriched) leads to HubSpot.
Run 2x/day via cron / Task Scheduler, or manually.

Requires HUBSPOT_API_KEY in .env — see app/integrations/hubspot.py for setup.

Usage:
  python scripts/sync_hubspot.py                 # qualified leads only
  python scripts/sync_hubspot.py --include-enriched
  python scripts/sync_hubspot.py --resync        # also update already-pushed leads
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead
from app.integrations import hubspot
from app.utils.logger import setup_logging

setup_logging()


def main():
    parser = argparse.ArgumentParser(description="Sync leads to HubSpot")
    parser.add_argument("--include-enriched", action="store_true")
    parser.add_argument("--resync", action="store_true",
                        help="Also update leads already in HubSpot")
    args = parser.parse_args()

    if not hubspot.is_configured():
        print("HUBSPOT_API_KEY is not set in .env — nothing to do.")
        print("Create a HubSpot Private App (contacts read+write) and add its token.")
        sys.exit(1)

    statuses = ["qualified"]
    if args.include_enriched:
        statuses.append("enriched")
    if args.resync:
        statuses.append("pushed")

    db = SessionLocal()
    try:
        leads = db.query(Lead).filter(Lead.status.in_(statuses)).all()
        print(f"Syncing {len(leads)} leads (statuses: {statuses}) to HubSpot...")
        stats = hubspot.sync_leads(db, leads)
        print(f"Done: created={stats['created']} updated={stats['updated']} "
              f"failed={stats['failed']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
