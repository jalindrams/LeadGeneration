"""
Micraft Growth Engine - Base Scraper
Abstract interface that all scrapers must implement.
Provides common functionality: rate limiting, logging, metrics tracking.
"""

import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generator

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead, ScrapeJob
from app.processing.dedup import deduplicate_lead
from app.processing.scorer import score_and_qualify
from app.utils.logger import get_logger
from app.utils import yield_tracker

log = get_logger("scraper_base")


class BaseScraper(ABC):
    """Base class for all lead scrapers."""

    SOURCE_NAME: str = "unknown"  # Override in subclass

    def __init__(self, db: Session, target_product: str = None):
        self.db = db
        self.job: ScrapeJob = None
        self.target_product = (target_product or "").strip().lower() or None
        self._bad_phones: set = None  # lazy-loaded wrong_contact blacklist
        self.stats = {
            "found": 0,
            "stored": 0,
            "duplicate": 0,
            "errors": 0,
        }

    def _load_bad_phones(self) -> set:
        """
        Institutional memory: phone numbers reps marked wrong_contact never
        re-enter the pipeline, no matter which source resurfaces them.
        """
        if self._bad_phones is None:
            from app.processing.dedup import normalize_phone
            rows = (
                self.db.query(Lead.phone)
                .filter(Lead.response_status == "wrong_contact",
                        Lead.phone.isnot(None))
                .all()
            )
            self._bad_phones = {normalize_phone(r[0]) for r in rows if r[0]}
            log.info("bad_phone_blacklist_loaded", count=len(self._bad_phones))
        return self._bad_phones

    def random_delay(self):
        """Human-like delay between requests."""
        delay = random.uniform(settings.SCRAPE_DELAY_MIN, settings.SCRAPE_DELAY_MAX)
        log.debug("sleeping", seconds=round(delay, 1))
        time.sleep(delay)

    def start_job(self, search_query: str, city: str) -> ScrapeJob:
        """Create a scrape job record in the database."""
        self.job = ScrapeJob(
            source=self.SOURCE_NAME,
            search_query=search_query,
            city=city,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(self.job)
        self.db.commit()
        log.info("job_started", source=self.SOURCE_NAME, query=search_query, city=city, job_id=self.job.id)
        return self.job

    def complete_job(self, error: str = None):
        """Mark the scrape job as completed or failed."""
        if not self.job:
            return

        now = datetime.utcnow()
        self.job.completed_at = now
        self.job.records_found = self.stats["found"]
        self.job.records_stored = self.stats["stored"]
        self.job.records_duplicate = self.stats["duplicate"]

        if self.job.started_at:
            self.job.duration_seconds = int((now - self.job.started_at).total_seconds())

        if error:
            self.job.status = "failed"
            self.job.error_log = error
            log.error("job_failed", source=self.SOURCE_NAME, error=error, **self.stats)
        else:
            self.job.status = "completed"
            log.info("job_completed", source=self.SOURCE_NAME, **self.stats)

        self.db.commit()

    def store_lead(self, lead_data: dict) -> tuple[bool, Lead]:
        """
        Deduplicate and store a single lead.

        Returns:
            (was_new, lead_object) - True if new lead stored, False if duplicate
        """
        self.stats["found"] += 1

        # Ensure source is set
        lead_data["source"] = self.SOURCE_NAME

        # Skip leads that do not have a phone number
        if not lead_data.get("phone"):
            self.stats["errors"] += 1
            log.debug("lead_rejected_no_phone", company=lead_data.get("company_name"))
            return False, None

        # Skip phones the sales team already proved wrong (institutional memory)
        from app.processing.dedup import normalize_phone
        if normalize_phone(lead_data["phone"]) in self._load_bad_phones():
            self.stats["errors"] += 1
            log.info("lead_rejected_known_bad_phone",
                     company=lead_data.get("company_name"), phone=lead_data["phone"])
            return False, None

        # Filter out common junk company names
        bad_names = ["contact us", "about us", "home", "feedback", "help", "login", "register", "jobs & careers", "complaints", "customer care"]
        company_name_lower = lead_data.get("company_name", "").lower().strip()
        if any(bad == company_name_lower for bad in bad_names) or len(company_name_lower) < 3:
            self.stats["errors"] += 1
            log.debug("lead_rejected_bad_name", company=lead_data.get("company_name"))
            return False, None

        # Run dedup check
        is_dup, existing, dedup_hash = deduplicate_lead(self.db, lead_data)

        if is_dup:
            self.stats["duplicate"] += 1
            log.debug("lead_duplicate", company=lead_data.get("company_name"))
            return False, existing

        # Score + qualify with the ICP engine (freshness applies: just scraped)
        turnover = lead_data.get("turnover", "")
        eval_data = dict(lead_data)
        eval_data["scraped_at"] = datetime.utcnow()
        eval_data["target_product"] = self.target_product
        evaluation = score_and_qualify(eval_data)
        score = evaluation["score"]
        status = "qualified" if evaluation["qualified"] else "raw"

        # Create new lead
        lead = Lead(
            company_name=lead_data.get("company_name", ""),
            full_name=lead_data.get("full_name"),
            first_name=lead_data.get("first_name"),
            last_name=lead_data.get("last_name"),
            title=lead_data.get("title"),
            email=lead_data.get("email"),
            phone=lead_data.get("phone"),
            company_url=lead_data.get("company_url"),
            industry=lead_data.get("industry"),
            company_size=lead_data.get("company_size"),
            location=lead_data.get("location"),
            source=self.SOURCE_NAME,
            gst_number=lead_data.get("gst_number"),
            product_category=lead_data.get("product_category"),
            turnover=turnover,
            target_product=self.target_product,
            status=status,
            score=score,
            dedup_hash=dedup_hash,
        )

        self.db.add(lead)
        try:
            self.db.commit()
        except Exception as e:
            # One bad row (oversize value, unique collision, encoding) must
            # never poison the session and kill the whole harvest.
            self.db.rollback()
            self.stats["errors"] += 1
            log.error("lead_commit_failed", company=lead_data.get("company_name"),
                      error=str(e)[:200])
            return False, None

        self.stats["stored"] += 1

        # Update job in real-time for progress tracking
        if self.job:
            self.job.records_stored = self.stats["stored"]
            self.db.commit()

        # Track in yield metrics
        yield_tracker.increment(self.db, self.SOURCE_NAME, "raw_leads")
        if status == "qualified":
            yield_tracker.increment(self.db, self.SOURCE_NAME, "final_qualified")

        # Module 3: instant alert if this lead is hot
        try:
            from app.revenue.hot_trigger import trigger_if_hot
            trigger_if_hot(lead)
        except Exception as e:
            log.error("hot_trigger_error", error=str(e))

        log.info("lead_stored", company=lead.company_name, location=lead.location, phone=bool(lead.phone))
        return True, lead

    @abstractmethod
    def scrape(self, search_query: str, city: str, max_pages: int = None) -> list[dict]:
        """
        Run the scraper for a given search query and city.

        Args:
            search_query: What to search for (e.g., "automotive parts manufacturer")
            city: Target city (e.g., "Pune")
            max_pages: Max pages to scrape (default from settings)

        Returns:
            List of raw lead dicts extracted from the source
        """
        pass

    def run(self, search_query: str, city: str, max_pages: int = None) -> dict:
        """
        Full scrape pipeline: start job → scrape → store → complete job.
        Returns stats dict.
        """
        self.stats = {"found": 0, "stored": 0, "duplicate": 0, "errors": 0}

        self.start_job(search_query, city)
        try:
            leads_data = self.scrape(search_query, city, max_pages)
            for lead_data in leads_data:
                try:
                    self.store_lead(lead_data)
                except Exception as e:
                    self.stats["errors"] += 1
                    log.error("lead_store_error", error=str(e), company=lead_data.get("company_name"))

            self.complete_job()
        except Exception as e:
            self.complete_job(error=str(e))
            raise

        return self.stats
