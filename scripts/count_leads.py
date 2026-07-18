import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead

def count_leads():
    db = SessionLocal()
    try:
        count = db.query(Lead).count()
        print(f"Total leads: {count}")
    finally:
        db.close()

if __name__ == "__main__":
    count_leads()
