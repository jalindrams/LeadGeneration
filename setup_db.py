"""
Micraft Growth Engine - Database Setup
Creates all tables in the database.
Run this once after setting up PostgreSQL.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base
from app.models import (
    Lead, ScrapeJob, LeadPipelineMetrics,
    LeadFeedback, ManualReviewQueue, SourcePerformance,
)


def create_tables():
    """Create all database tables."""
    print("=" * 50)
    print("Micraft Growth Engine - Database Setup")
    print("=" * 50)

    print(f"\nConnecting to: {engine.url}")
    print("Creating tables...")

    Base.metadata.create_all(bind=engine)

    # List created tables
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print(f"\n[SUCCESS] {len(tables)} tables created:")
    for t in tables:
        cols = inspector.get_columns(t)
        print(f"   - {t} ({len(cols)} columns)")

    print("\n[SUCCESS] Database setup complete!")
    print("=" * 50)


if __name__ == "__main__":
    create_tables()
