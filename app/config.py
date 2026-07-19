"""
Micraft Growth Engine - Configuration
Loads settings from .env file and provides typed access.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env from project root
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql://micraft:micraft_pass@localhost:5432/micraft_leads"

    # Google Maps — FREE TIER ONLY (owner rule: never pay).
    # Hard monthly cap on total Places API calls across the whole app;
    # sits safely under Google's smallest per-SKU free tier (5,000/month).
    GOOGLE_MAPS_API_KEY: str = ""
    PLACES_MONTHLY_CALL_CAP: int = 4000

    # Scraper Settings
    SCRAPE_DELAY_MIN: int = 3
    SCRAPE_DELAY_MAX: int = 8
    SCRAPE_MAX_PAGES: int = 5

    # Target Configuration
    TARGET_CITIES: str = "Pune,Mumbai,Chennai,Ahmedabad"
    TARGET_SEARCHES: str = "Automotive Manufacturer, Pharmaceutical Manufacturer, Electronics Manufacturer, Food Beverage Manufacturer, Aerospace Manufacturer"

    # App Settings
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # CSV Export
    CSV_EXPORT_DIR: str = "./exports"

    # --- Phase 3: Revenue Engine ---
    # Hot lead threshold (score >= this triggers instant alerts)
    HOT_LEAD_THRESHOLD: int = 70

    # Twilio WhatsApp alerts (Module 3) — leave blank to disable
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""   # e.g. whatsapp:+14155238886
    ALERT_WHATSAPP_TO: str = ""      # comma-separated, e.g. whatsapp:+9198xxxxxx

    # Slack webhook alerts — leave blank to disable
    SLACK_WEBHOOK_URL: str = ""

    # SMTP email alerts — leave blank to disable
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ALERT_EMAIL_TO: str = ""         # comma-separated

    # HubSpot CRM sync — leave blank to disable
    HUBSPOT_API_KEY: str = ""        # Private App token (pat-...)

    @property
    def cities_list(self) -> list[str]:
        return [c.strip() for c in self.TARGET_CITIES.split(",") if c.strip()]

    @property
    def searches_list(self) -> list[str]:
        return [s.strip() for s in self.TARGET_SEARCHES.split(",") if s.strip()]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
