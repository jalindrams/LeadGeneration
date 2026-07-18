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
        
        # Monkey patch to skip profile details to make it blazing fast
        def mock_scrape_profile(*args, **kwargs):
            return {"turnover": "100-500 Crore"}  # Make them high quality
            
        scraper._scrape_profile_details_with_new_page = mock_scrape_profile
        
        # Monkey patch delay
        scraper.random_delay = lambda: None
        
        # Run it
        print("Starting fast scrape...")
        stats = scraper.run("manufacturing company", "Pune", max_pages=10)
        print(f"Stats: {stats}")
    finally:
        db.close()

if __name__ == "__main__":
    fast_scrape()
