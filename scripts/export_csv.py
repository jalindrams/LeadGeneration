"""
Micraft Growth Engine - CSV Export Script
Exports leads to CSV file for sales team.

Usage:
    python scripts/export_csv.py
    python scripts/export_csv.py --has-phone --city Pune
    python scripts/export_csv.py --source indiamart --output ./exports/pune_leads.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.database import SessionLocal
from app.models import Lead
from sqlalchemy import desc


def export_leads(
    output_path: str,
    source: str = None,
    city: str = None,
    has_phone: bool = False,
    status: str = None,
):
    """Export leads to a CSV file."""
    db = SessionLocal()

    try:
        query = db.query(Lead)

        # Apply filters
        if source:
            query = query.filter(Lead.source == source)
        if city:
            query = query.filter(Lead.location.ilike(f"%{city}%"))
        if has_phone:
            query = query.filter(Lead.phone.isnot(None), Lead.phone != "")
        if status:
            query = query.filter(Lead.status == status)

        leads = query.order_by(desc(Lead.lead_created_at)).all()

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        # Write CSV
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "Company Name", "Contact Person", "Designation", "Phone", "Email",
                "Location", "Industry", "Product Category", "Company Website",
                "Source", "GST Number", "Status", "Date Collected",
            ])

            # Data
            for lead in leads:
                writer.writerow([
                    lead.company_name,
                    lead.full_name or "",
                    lead.title or "",
                    lead.phone or "",
                    lead.email or "",
                    lead.location or "",
                    lead.industry or "",
                    lead.product_category or "",
                    lead.company_url or "",
                    lead.source,
                    lead.gst_number or "",
                    lead.status,
                    lead.scraped_at.strftime("%Y-%m-%d") if lead.scraped_at else "",
                ])

        print(f"✅ Exported {len(leads)} leads to: {output_path}")
        print(f"   Source filter: {source or 'all'}")
        print(f"   City filter:   {city or 'all'}")
        print(f"   Phone filter:  {has_phone}")

        # Quick stats
        with_phone = sum(1 for l in leads if l.phone)
        with_email = sum(1 for l in leads if l.email)
        print(f"\n   📊 Stats:")
        print(f"   With phone: {with_phone}/{len(leads)} ({round(with_phone/max(len(leads),1)*100)}%)")
        print(f"   With email: {with_email}/{len(leads)} ({round(with_email/max(len(leads),1)*100)}%)")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Export leads to CSV")
    parser.add_argument("--output", "-o", default=None,
                        help="Output file path (default: ./exports/leads_YYYYMMDD.csv)")
    parser.add_argument("--source", default=None, help="Filter by source")
    parser.add_argument("--city", default=None, help="Filter by city")
    parser.add_argument("--has-phone", action="store_true", help="Only leads with phone numbers")
    parser.add_argument("--status", default=None, help="Filter by status")

    args = parser.parse_args()

    # Default output path
    if not args.output:
        os.makedirs(settings.CSV_EXPORT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        args.output = os.path.join(settings.CSV_EXPORT_DIR, f"leads_{timestamp}.csv")

    print("=" * 50)
    print("📥 MICRAFT - Lead CSV Export")
    print("=" * 50)

    export_leads(
        output_path=args.output,
        source=args.source,
        city=args.city,
        has_phone=args.has_phone,
        status=args.status,
    )


if __name__ == "__main__":
    main()
