"""
Migration: add leads.target_product column (which Micraft product a lead targets).
Existing real leads were collected for MES — backfill them as 'mes'.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine

with engine.begin() as conn:
    conn.execute(text(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS target_product VARCHAR(30)"))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_leads_target_product ON leads (target_product)"))
    updated = conn.execute(text(
        "UPDATE leads SET target_product = 'mes' "
        "WHERE target_product IS NULL AND status != 'synthetic'")).rowcount
    print(f"Column added. Backfilled {updated} existing real leads as target_product='mes'.")
