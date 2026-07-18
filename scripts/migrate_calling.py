"""
Migration script for Phase 1.5 - Lead Calling System.
Adds calling fields to leads table and creates the call_logs table.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base
from sqlalchemy import text
from app.models import CallLog  # Ensures Base knows about the table

def migrate():
    print("Starting migration for Phase 1.5...")
    
    with engine.begin() as conn:
        # Add new columns to leads table
        print("Checking/adding columns to 'leads' table...")
        columns_to_add = [
            ("call_status", "VARCHAR(50) DEFAULT 'new'"),
            ("decision_maker", "VARCHAR(200)"),
            ("pain_point", "TEXT"),
            ("follow_up_date", "DATE"),
            ("remarks", "TEXT"),
            ("call_count", "INTEGER DEFAULT 0")
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col_name} {col_type}"))
                print(f"Added column {col_name}")
            except Exception as e:
                # Catch error if column already exists
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print(f"Column {col_name} already exists, skipping.")
                else:
                    print(f"Error adding column {col_name}: {e}")
                    
        # Create indexes for new columns if possible
        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_leads_call_status ON leads (call_status)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_leads_follow_up ON leads (follow_up_date)"))
            print("Created indexes on 'leads' table.")
        except Exception as e:
            print(f"Index creation error (might already exist): {e}")

    # Create new tables
    print("Creating new tables (e.g., call_logs)...")
    Base.metadata.create_all(bind=engine)
    
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    migrate()
