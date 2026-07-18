"""
Micraft Growth Engine - Seed Data
Inserts sample test data for development and testing.
Run this after setup_db.py to populate the database with realistic test leads.

Usage:
    python scripts/seed_data.py
"""

import sys
import os
import uuid
from datetime import datetime, timedelta
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead, LeadPipelineMetrics
from app.processing.dedup import compute_dedup_hash
from app.utils.logger import setup_logging

setup_logging()

# Realistic sample data matching our ICP
SAMPLE_LEADS = [
    {
        "company_name": "Sharma Auto Components Pvt Ltd",
        "full_name": "Rajesh Sharma",
        "title": "Plant Head",
        "phone": "+919876543210",
        "email": "rajesh@sharmaauto.com",
        "location": "Pune, Maharashtra",
        "industry": "Manufacturing",
        "product_category": "Automotive steering components",
        "company_url": "https://www.sharmaauto.com",
        "gst_number": "27AAACS1234R1ZY",
        "company_size": "80-120 employees",
    },
    {
        "company_name": "Precision Plastics India",
        "full_name": "Amit Patel",
        "title": "Owner",
        "phone": "+919812345678",
        "location": "Ahmedabad, Gujarat",
        "industry": "Manufacturing",
        "product_category": "Plastic injection molding - automotive parts",
        "company_size": "30-50 employees",
        "gst_number": "24AABCP5678R1ZX",
    },
    {
        "company_name": "Chennai Metal Fabricators",
        "full_name": "K. Venkatesh",
        "title": "Production Manager",
        "phone": "+919944556677",
        "location": "Chennai, Tamil Nadu",
        "industry": "Manufacturing",
        "product_category": "Sheet metal fabrication, CNC machining",
        "company_size": "50-80 employees",
    },
    {
        "company_name": "Supreme Die Cast Industries",
        "full_name": "Mahesh Kumar",
        "title": "Owner",
        "phone": "+919823456789",
        "email": "mahesh@supremedie.co.in",
        "location": "Pune, Maharashtra",
        "industry": "Manufacturing",
        "product_category": "Aluminium die casting - automotive",
        "company_url": "https://www.supremedie.co.in",
        "company_size": "100-200 employees",
    },
    {
        "company_name": "Mumbai Polymers & Moulding",
        "full_name": "Ravi Deshmukh",
        "title": "Plant Head",
        "phone": "+919876123456",
        "location": "Mumbai, Maharashtra",
        "industry": "Manufacturing",
        "product_category": "Plastic molding - consumer goods",
        "company_size": "40-60 employees",
    },
    {
        "company_name": "Ankit Engineering Works",
        "full_name": "Ankit Jain",
        "title": "Owner",
        "phone": "+919712345678",
        "location": "Ahmedabad, Gujarat",
        "industry": "Manufacturing",
        "product_category": "Precision machined components",
        "company_size": "20-30 employees",
    },
    {
        "company_name": "Sri Balaji Auto Parts",
        "full_name": "P. Balasubramanian",
        "title": "Production Manager",
        "phone": "+919845678901",
        "location": "Chennai, Tamil Nadu",
        "industry": "Manufacturing",
        "product_category": "Two-wheeler spare parts manufacturing",
        "company_size": "60-80 employees",
    },
    {
        "company_name": "Reliable Rubber Mouldings",
        "full_name": "Suresh Patil",
        "title": "Owner",
        "phone": "+919823001234",
        "location": "Pune, Maharashtra",
        "industry": "Manufacturing",
        "product_category": "Rubber moulded parts for automotive",
        "company_size": "25-40 employees",
    },
    {
        "company_name": "Galaxy Fabrication Systems",
        "full_name": "Hitesh Shah",
        "title": "Plant Head",
        "phone": "+919898765432",
        "email": "hitesh@galaxyfab.com",
        "location": "Ahmedabad, Gujarat",
        "industry": "Manufacturing",
        "product_category": "Steel fabrication, structural steel",
        "company_url": "https://www.galaxyfab.com",
        "company_size": "150-200 employees",
    },
    {
        "company_name": "Karthik Plastics Engineering",
        "full_name": "S. Karthik",
        "title": "Owner",
        "phone": "+919677889900",
        "location": "Chennai, Tamil Nadu",
        "industry": "Manufacturing",
        "product_category": "Engineering plastics, HDPE molding",
        "company_size": "35-50 employees",
    },
]

SOURCES = ["indiamart", "google_maps"]


def seed_leads():
    """Insert sample leads into the database."""
    db = SessionLocal()
    inserted = 0

    try:
        for i, data in enumerate(SAMPLE_LEADS):
            source = SOURCES[i % len(SOURCES)]
            dedup_hash = compute_dedup_hash(
                data["company_name"],
                data.get("phone"),
                data.get("gst_number"),
                data.get("location"),
            )

            # Check if already exists
            existing = db.query(Lead).filter(Lead.dedup_hash == dedup_hash).first()
            if existing:
                print(f"   ⏭️  Skipping (already exists): {data['company_name']}")
                continue

            lead = Lead(
                company_name=data["company_name"],
                full_name=data.get("full_name"),
                title=data.get("title"),
                phone=data.get("phone"),
                email=data.get("email"),
                location=data.get("location"),
                industry=data.get("industry", "Manufacturing"),
                product_category=data.get("product_category"),
                company_url=data.get("company_url"),
                company_size=data.get("company_size"),
                gst_number=data.get("gst_number"),
                source=source,
                status="raw",
                dedup_hash=dedup_hash,
                scraped_at=datetime.utcnow() - timedelta(hours=random.randint(0, 48)),
            )
            db.add(lead)
            inserted += 1
            print(f"   ✅ Inserted: {data['company_name']} ({source})")

        # Also seed some pipeline metrics
        from datetime import date
        for source in SOURCES:
            metrics = LeadPipelineMetrics(
                source=source,
                date=date.today(),
                raw_leads=len([l for i, l in enumerate(SAMPLE_LEADS) if SOURCES[i % len(SOURCES)] == source]),
            )
            db.merge(metrics)

        db.commit()
        print(f"\n✅ Seeded {inserted} leads + pipeline metrics")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


def main():
    print("=" * 50)
    print("🌱 MICRAFT - Seeding Test Data")
    print("=" * 50)
    seed_leads()
    print("=" * 50)


if __name__ == "__main__":
    main()
