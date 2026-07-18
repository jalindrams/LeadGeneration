import os
import sys

# Add the parent directory to sys.path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from app.config import settings

def main():
    print(f"Connecting to database: {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE leads ADD COLUMN turnover VARCHAR(200);"))
            conn.commit()
            print("Successfully added 'turnover' column to 'leads' table.")
        except Exception as e:
            if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                print("'turnover' column already exists.")
            else:
                print(f"Error adding column: {e}")

if __name__ == "__main__":
    main()
