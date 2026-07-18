import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.scrapers.indiamart import IndiaMartScraper
from app.config import settings

def fast_scrape():
    db = SessionLocal()
    try:
        scraper = IndiaMartScraper(db)
        
        def mock_scrape_profile(*args, **kwargs):
            return {"turnover": "100-500 Crore"}
            
        scraper._scrape_profile_details_with_new_page = mock_scrape_profile
        scraper.random_delay = lambda: None
        
        print("Starting fast scrape 2...")
        stats = scraper.run("electronics manufacturer", "Pune", max_pages=15)
        print(f"Stats: {stats}")
    finally:
        db.close()

if __name__ == "__main__":
    fast_scrape()
