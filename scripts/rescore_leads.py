"""
Micraft Growth Engine - Batch Rescore
Rescores all leads with the real ICP scoring engine (app/processing/scorer.py)
and advances qualification status per the locked definition.

Skips leads detected as synthetic (see audit_data_integrity.py) so fabricated
data never enters the qualified pipeline.

Usage:
  python scripts/rescore_leads.py            # rescore + report
  python scripts/rescore_leads.py --dry-run  # report only, no DB writes
"""

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead
from app.processing.scorer import score_and_qualify

# Reuse synthetic detection so fakes are never scored/qualified
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audit_data_integrity import detect


def main():
    parser = argparse.ArgumentParser(description="Rescore all leads with the ICP engine")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no DB writes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        tiers = Counter()
        missing_counter = Counter()
        skipped_synthetic = 0
        qualified_count = 0
        changed = 0

        for lead in leads:
            if lead.status == "synthetic" or detect(lead):
                skipped_synthetic += 1
                continue

            result = score_and_qualify(lead)
            tiers[result["tier"]] += 1
            for m in result["missing"]:
                missing_counter[m] += 1

            new_status = lead.status
            if result["qualified"]:
                qualified_count += 1
                if lead.status == "raw":
                    new_status = "qualified"

            if lead.score != result["score"] or lead.status != new_status:
                changed += 1
                if not args.dry_run:
                    lead.score = result["score"]
                    lead.status = new_status

        if not args.dry_run:
            db.commit()

        scored = len(leads) - skipped_synthetic
        print(f"{'DRY RUN — ' if args.dry_run else ''}Rescore complete")
        print(f"  Total leads          : {len(leads)}")
        print(f"  Skipped (synthetic)  : {skipped_synthetic}")
        print(f"  Scored               : {scored}")
        print(f"  Updated              : {changed if not args.dry_run else f'{changed} (would update)'}")
        print()
        print("Tier distribution (real leads):")
        for t in ("hot", "warm", "cold"):
            print(f"  {t:5s} : {tiers.get(t, 0)}")
        print(f"\nQualified (locked bar): {qualified_count} / {scored}")
        print("\nWhy leads fail qualification (top gaps = enrichment priorities):")
        for reason, n in missing_counter.most_common():
            print(f"  {reason:20s} : {n}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
