"""
Micraft Growth Engine - Outreach Runner

Sends WhatsApp / email outreach to eligible leads using the smart template engine.

Usage:
  # Dry run — see what WOULD be sent, nothing actually sent
  python scripts/run_outreach.py --dry-run

  # Send to hot calibration leads (up to 30)
  python scripts/run_outreach.py --product calibration --tier hot --limit 30

  # Send to all warm leads across all products
  python scripts/run_outreach.py --tier warm --limit 50

  # All hot leads, all products
  python scripts/run_outreach.py --tier hot

  # Preview templates for a product (no DB needed)
  python scripts/run_outreach.py --preview-templates --product calibration

Setup checklist:
  WhatsApp: WHATSAPP_ACCESS_TOKEN + WHATSAPP_PHONE_NUMBER_ID in .env
            Template names approved in Meta WhatsApp Manager
  Email:    SMTP_HOST + SMTP_USER + SMTP_PASSWORD in .env
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.outreach import cadence
from app.outreach.templates import TEMPLATES, select_template, render
from app.utils.logger import get_logger

log = get_logger("run_outreach")

PRODUCTS = ["all", "mes", "dms", "tms", "courier", "calibration", "ecom"]
TIERS = ["all", "hot", "warm"]


def preview_templates(product: str):
    """Print all templates for a product to stdout."""
    print(f"\n{'='*60}")
    print(f"  Template preview — product: {product or 'all'}")
    print(f"{'='*60}")

    sample_lead = {
        "full_name": "Rajesh Kumar",
        "company_name": "ABC Instruments Pvt Ltd",
        "target_product": product if product != "all" else "calibration",
        "source": "nabl",
    }

    for step in (0, 1, 2):
        tkey = select_template(sample_lead, step=step)
        rendered = render(tkey, sample_lead)
        print(f"\n[Step {step}] Template key: {tkey}")
        print(f"  WA template name : {rendered['wa_name']}")
        print(f"  WA params        : {rendered['wa_params']}")
        print(f"  Email subject    : {rendered['email_subject']}")
        print(f"\n  WhatsApp preview:\n{'─'*50}")
        for line in rendered["wa_preview"].split("\n"):
            print(f"  {line}")
        print(f"{'─'*50}")


def main():
    parser = argparse.ArgumentParser(description="Micraft Outreach Runner")
    parser.add_argument("--product", default="all", choices=PRODUCTS,
                        help="Product to target (default: all)")
    parser.add_argument("--tier", default="hot", choices=TIERS,
                        help="Score tier: hot(≥70), warm(40-69), all (default: hot)")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max leads to contact in this run (default: 50)")
    parser.add_argument("--cooldown", type=int, default=3,
                        help="Min days since last contact (default: 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be sent — no actual messages sent")
    parser.add_argument("--preview-templates", action="store_true",
                        help="Print template previews and exit (no DB needed)")
    args = parser.parse_args()

    if args.preview_templates:
        preview_templates(args.product)
        return

    db = SessionLocal()
    try:
        print(f"\nMicraft Outreach Runner")
        print(f"  Product  : {args.product}")
        print(f"  Tier     : {args.tier}")
        print(f"  Limit    : {args.limit}")
        print(f"  Cooldown : {args.cooldown} days")
        print(f"  Dry run  : {'YES — no messages will be sent' if args.dry_run else 'NO — sending live'}")
        print()

        if not args.dry_run:
            confirm = input("Confirm live send? [y/N] ").strip().lower()
            if confirm != "y":
                print("Aborted.")
                return

        summary = cadence.run_batch(
            db=db,
            product=args.product,
            tier=args.tier,
            limit=args.limit,
            cooldown_days=args.cooldown,
            dry_run=args.dry_run,
        )

        print(f"\nResults:")
        print(f"  Eligible leads : {summary['eligible']}")
        print(f"  WhatsApp sent  : {summary['sent_whatsapp']}")
        print(f"  Email sent     : {summary['sent_email']}")
        print(f"  Failed         : {summary['failed']}")

        if args.dry_run:
            print(f"\nDry-run preview (first 15):")
            for r in summary["results"][:15]:
                status = "OK" if r["success"] else "SKIP"
                ch = (r.get("channel") or "?")[:6].upper()
                preview = (r.get("preview") or "")[:70]
                tkey = r.get("template_key", "?")
                print(f"  [{status}] {ch:<7} | {tkey:<30} | {preview}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
