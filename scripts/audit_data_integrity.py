"""
Micraft Growth Engine - Data Integrity Audit
Detects synthetic (generator-created) leads in the database.

The generate_*.py scripts fabricated leads with deterministic patterns:
  - company_name  = "<Prefix> <Industry> Pvt Ltd" from fixed word lists
  - company_url   = "https://www.<name-without-'pvt ltd'>.co.in" (derived from name)
  - email         = "<first>.<last>@<name-squashed>.com"          (derived from name)
  - phone         = "+919#########" (random digits — may be a real stranger's number!)
  - sources 'linkedin' / 'tradeindia' have NO scrapers — always synthetic

Usage:
  python scripts/audit_data_integrity.py            # dry-run report (no changes)
  python scripts/audit_data_integrity.py --apply    # quarantine detected leads
                                                    # (sets status='synthetic', exports audit CSV first)
"""

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead

# Sources that never had a scraper — anything from them is fabricated
SOURCES_WITHOUT_SCRAPERS = {"linkedin", "tradeindia"}

# Word lists copied from the generator scripts (superset across all versions)
GEN_PREFIXES = {
    "precision", "supreme", "galaxy", "apex", "nova", "standard", "elite", "prime",
    "universal", "classic", "vector", "sigma", "delta", "matrix", "alpha", "beta",
    "dynamic", "pioneer", "global", "national", "smart", "advanced", "tech", "modern",
    "united", "reliance", "star", "super", "mega", "sunrise", "golden", "diamond",
    "infinity", "aura", "zenith", "quantum", "omega", "excel", "pro", "max", "ultra",
}
GEN_INDUSTRIES = {
    "engineering", "plastics", "auto parts", "components", "industries", "forge",
    "cast", "systems", "technologies", "tools", "moulds", "fab", "manufacturing",
    "metal", "steel", "aluminium", "electric", "electronic", "mechanic", "machines",
    "equipment", "motors", "valves", "packaging", "chemicals", "polymers", "solutions",
}


def derived_url(company_name: str) -> str:
    """Recompute the URL exactly as the generators did."""
    return f"https://www.{company_name.lower().replace(' ', '').replace('pvtltd', '')}.co.in"


def derived_email_domain(company_name: str) -> str:
    """Recompute the email domain exactly as the generators did."""
    return company_name.lower().replace(" ", "") + ".com"


def name_matches_template(company_name: str) -> bool:
    """Does the name match '<Prefix> <Industry> Pvt Ltd' from the generator word lists?"""
    name = (company_name or "").strip().lower()
    if not name.endswith(" pvt ltd"):
        return False
    core = name[: -len(" pvt ltd")]
    for prefix in GEN_PREFIXES:
        if core.startswith(prefix + " "):
            rest = core[len(prefix) + 1:]
            if rest in GEN_INDUSTRIES:
                return True
    return False


def detect(lead: Lead) -> list[str]:
    """Return list of fingerprints matched (empty = looks real)."""
    hits = []
    name = lead.company_name or ""

    if (lead.source or "").lower() in SOURCES_WITHOUT_SCRAPERS:
        hits.append("source_has_no_scraper")

    template = name_matches_template(name)
    url_derived = bool(lead.company_url) and lead.company_url.strip() == derived_url(name)
    email_derived = bool(lead.email) and lead.email.strip().lower().endswith(
        "@" + derived_email_domain(name)
    )

    if template and (url_derived or email_derived):
        hits.append("templated_name_with_derived_contact")
    elif url_derived and email_derived:
        hits.append("derived_url_and_email")

    return hits


def main():
    parser = argparse.ArgumentParser(description="Audit database for synthetic leads")
    parser.add_argument("--apply", action="store_true",
                        help="Quarantine detected leads (status='synthetic') after exporting audit CSV")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        leads = db.query(Lead).all()
        flagged = []
        for lead in leads:
            hits = detect(lead)
            if hits:
                flagged.append((lead, hits))

        # --- Report ---
        print(f"Total leads scanned : {len(leads)}")
        print(f"Synthetic detected  : {len(flagged)}")
        print(f"Looks real          : {len(leads) - len(flagged)}")
        print()

        by_source = {}
        by_reason = {}
        for lead, hits in flagged:
            by_source[lead.source] = by_source.get(lead.source, 0) + 1
            for h in hits:
                by_reason[h] = by_reason.get(h, 0) + 1

        print("Synthetic by (claimed) source:")
        for src, n in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"  {src:20s} {n}")
        print("\nBy fingerprint:")
        for reason, n in sorted(by_reason.items(), key=lambda x: -x[1]):
            print(f"  {reason:40s} {n}")

        if not flagged:
            return

        if args.apply:
            # Audit trail first
            os.makedirs("exports", exist_ok=True)
            path = f"exports/synthetic_leads_audit_{datetime.now():%Y%m%d_%H%M}.csv"
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["id", "company_name", "source", "phone", "email",
                            "prev_status", "fingerprints", "scraped_at"])
                for lead, hits in flagged:
                    w.writerow([lead.id, lead.company_name, lead.source, lead.phone,
                                lead.email, lead.status, ";".join(hits), lead.scraped_at])
            print(f"\nAudit trail written: {path}")

            for lead, _ in flagged:
                lead.status = "synthetic"
            db.commit()
            print(f"Quarantined {len(flagged)} leads (status='synthetic').")
            print("They are excluded from scoring, export, and calling lists.")
            print("To restore: UPDATE leads SET status='raw' WHERE status='synthetic';")
        else:
            print("\nDRY RUN — no changes made. Re-run with --apply to quarantine.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
