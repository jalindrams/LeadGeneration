import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Lead

def reset_leads():
    db = SessionLocal()
    try:
        count = db.query(Lead).delete()
        db.commit()
        print(f"Successfully deleted {count} leads.")
    except Exception as e:
        db.rollback()
        print(f"Error deleting leads: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_leads()
