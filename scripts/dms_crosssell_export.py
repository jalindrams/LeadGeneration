"""
Micraft Growth Engine - DMS Cross-Sell List Export

Extracts existing DB leads that are prime DMS (Document Management System) prospects
from two pools already in the database — zero new scraping needed:

Pool 1: NABL-accredited labs
  ISO 17025 mandates document control for every accredited lab.
  Lab-specific records: controlled procedures, calibration certs, audit trails.
  These are MUST-BUY DMS customers the moment they expand or digitize.

Pool 2: AIPMA certified manufacturers
  ISO 9001 / IATF 16949 certified plastic processors.
  Quality management certification = mandatory document control infrastructure.

Output: exports/dms_crosssell_leads.csv

Usage:
  python scripts/dms_crosssell_export.py
  python scripts/dms_crosssell_export.py --min-score 0   # include all
"""

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead
from app.processing.scorer import score_and_qualify, lead_to_dict

EXPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
EXPORT_FILE = os.path.join(EXPORT_DIR, "dms_crosssell_leads.csv")


def _pool_reason(lead: Lead) -> str:
    if lead.source == "nabl":
        return "NABL lab — ISO 17025 mandates document control"
    if lead.source == "aipma":
        return "AIPMA certified manufacturer — quality cert = document control need"
    return "other"


def main():
    parser = argparse.ArgumentParser(description="Export DMS cross-sell lead list")
    parser.add_argument("--min-score", type=int, default=30,
                        help="Minimum score to include (default 30)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        candidates = (
            db.query(Lead)
            .filter(Lead.source.in_(["nabl", "aipma"]))
            .filter(Lead.phone.isnot(None))
            .order_by(Lead.source, Lead.score.desc())
            .all()
        )

        rows = []
        score_dist = {"hot": 0, "warm": 0, "cold": 0}
        for lead in candidates:
            d = lead_to_dict(lead)
            # Force DMS product context for scoring
            d["target_product"] = "dms"
            result = score_and_qualify(d)
            if result["score"] < args.min_score:
                continue
            score_dist[result["tier"]] += 1
            rows.append({
                "company_name": lead.company_name,
                "phone": lead.phone or "",
                "email": lead.email or "",
                "location": lead.location or "",
                "source": lead.source,
                "pool_reason": _pool_reason(lead),
                "dms_score": result["score"],
                "tier": result["tier"],
                "gst_number": lead.gst_number or "",
                "industry": lead.industry or "",
                "current_target_product": lead.target_product or "",
                "original_score": lead.score,
            })

        os.makedirs(EXPORT_DIR, exist_ok=True)
        fieldnames = [
            "company_name", "phone", "email", "location", "source",
            "pool_reason", "dms_score", "tier", "gst_number", "industry",
            "current_target_product", "original_score",
        ]
        with open(EXPORT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\nDMS Cross-Sell Export — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"  Source pools         : NABL + AIPMA (existing DB, no new scraping)")
        print(f"  Total exported       : {len(rows)}")
        print(f"  Tier distribution    : hot={score_dist['hot']}  warm={score_dist['warm']}  cold={score_dist['cold']}")
        print(f"  Output               : {EXPORT_FILE}")
        print(f"\nBreakdown by source:")
        nabl = sum(1 for r in rows if r["source"] == "nabl")
        aipma = sum(1 for r in rows if r["source"] == "aipma")
        print(f"  NABL labs            : {nabl}")
        print(f"  AIPMA manufacturers  : {aipma}")
        print(f"\nTop 10 leads:")
        for r in sorted(rows, key=lambda x: x["dms_score"], reverse=True)[:10]:
            print(f"  [{r['tier']:4s} {r['dms_score']:3d}] {r['company_name'][:45]:<45s} | {r['location'][:25]}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
