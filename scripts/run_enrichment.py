"""
Micraft Growth Engine - Batch Enrichment Runner
Runs the enrichment waterfall over real leads that are missing decision-maker
or contact data, highest-score first (best prospects enriched first).

Usage:
  python scripts/run_enrichment.py --limit 50            # enrich top 50 candidates
  python scripts/run_enrichment.py --limit 0             # all candidates
  python scripts/run_enrichment.py --limit 20 --delay 2  # slower, gentler
"""

import argparse
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_

from app.database import SessionLocal
from app.models import Lead
from app.enrichment.waterfall import enrich_lead
from app.utils.logger import setup_logging

setup_logging()


def main():
    parser = argparse.ArgumentParser(description="Run enrichment waterfall over leads")
    parser.add_argument("--limit", type=int, default=50, help="Max leads to process (0 = all)")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between leads")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        q = (
            db.query(Lead)
            .filter(Lead.status.notin_(("synthetic", "qualified")))
            .filter(or_(Lead.response_status.is_(None),
                        Lead.response_status != "not_interested"))
            .filter(Lead.company_url.isnot(None), Lead.company_url != "")
            .filter(or_(Lead.title.is_(None), Lead.title == "",
                        Lead.email.is_(None), Lead.email == ""))
            .order_by(Lead.score.desc())
        )
        if args.limit:
            q = q.limit(args.limit)
        leads = q.all()

        print(f"Enriching {len(leads)} leads (waterfall: indiamart profile / website -> manual queue)")
        stats = Counter()
        gained_fields = Counter()

        for i, lead in enumerate(leads, 1):
            try:
                result = enrich_lead(db, lead)
                db.commit()
                if result["gained"]:
                    stats["enriched"] += 1
                    for g in result["gained"]:
                        gained_fields[g] += 1
                elif result.get("error"):
                    stats["failed"] += 1
                else:
                    stats["nothing_new"] += 1
                if result["queued_for_manual"]:
                    stats["queued_manual"] += 1
                if result["evaluation"]["qualified"]:
                    stats["qualified"] += 1
            except Exception as e:
                db.rollback()
                stats["errors"] += 1
                safe_name = (lead.company_name or "").encode("ascii", "replace").decode()
                safe_err = str(e).encode("ascii", "replace").decode()
                print(f"  [{i}] ERROR {safe_name}: {safe_err}")

            if i % 10 == 0:
                print(f"  ... {i}/{len(leads)} done "
                      f"(enriched={stats['enriched']}, qualified={stats['qualified']})")
            time.sleep(args.delay)

        print("\nEnrichment run complete:")
        for k, v in stats.most_common():
            print(f"  {k:15s}: {v}")
        print("\nFields gained:")
        for k, v in gained_fields.most_common():
            print(f"  {k:15s}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
