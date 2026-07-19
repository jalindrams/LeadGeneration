"""
Micraft Growth Engine - NABL Labs → Calibration MS Retag

All NABL-sourced leads are accredited testing/calibration labs.
They are the primary ICP for Calibration MS (instrument scheduling,
certificate management, NABL compliance) — mandatory by their accreditation terms.

Tags all NABL leads without a target_product to 'calibration'.

Usage:
  python scripts/retag_nabl_calibration.py            # apply
  python scripts/retag_nabl_calibration.py --dry-run  # preview only
"""

import argparse
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead


def main():
    parser = argparse.ArgumentParser(description="Retag NABL leads → calibration")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        nabl_leads = db.query(Lead).filter(Lead.source == "nabl").all()

        already_tagged = [l for l in nabl_leads if l.target_product]
        untagged = [l for l in nabl_leads if not l.target_product]

        print(f"NABL leads in DB       : {len(nabl_leads)}")
        print(f"  already tagged       : {len(already_tagged)}")
        print(f"  untagged (to retag)  : {len(untagged)}")

        if already_tagged:
            tag_counts = Counter(l.target_product for l in already_tagged)
            print(f"  existing tags        : {dict(tag_counts)}")

        if not untagged:
            print("\nNothing to retag.")
            return

        if not args.dry_run:
            for lead in untagged:
                lead.target_product = "calibration"
            db.commit()
            print(f"\n[APPLIED] {len(untagged)} NABL leads tagged → calibration")
        else:
            print(f"\n[DRY RUN] Would tag {len(untagged)} NABL leads → calibration")

        # Sample preview
        sample = untagged[:5]
        print("\nSample leads:")
        for l in sample:
            print(f"  {l.company_name[:50]:<50s} | {(l.location or '')[:30]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
