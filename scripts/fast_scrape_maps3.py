import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.scrapers.google_maps import GoogleMapsScraper

def fast_scrape_maps3():
    db = SessionLocal()
    try:
        scraper = GoogleMapsScraper(db)
        scraper.random_delay = lambda: None
        print("Starting fast scrape maps 3...")
        stats = scraper.run("aerospace manufacturer", "Ahmedabad", max_pages=3)
        print(f"Stats: {stats}")
    finally:
        db.close()

if __name__ == "__main__":
    fast_scrape_maps3()
