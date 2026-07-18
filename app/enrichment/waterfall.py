"""
Micraft Growth Engine - Enrichment Waterfall (Module: Step 2)
Zero-cost enrichment chain for a single lead:

  1. IndiaMART profile scrape  (if company_url is an indiamart.com profile)
  2. Company website scrape    (if company_url is a real website)
  3. -> Human Intelligence Queue (if still no decision-maker on a good lead)

After enrichment the lead is rescored and its status advanced:
  raw -> enriched -> qualified (when the locked bar is met)
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Lead, ManualReviewQueue
from app.enrichment.website_extractor import extract_website_contacts
from app.enrichment.indiamart_profile import extract_indiamart_profile
from app.processing.scorer import score_and_qualify, has_valid_email, has_valid_phone
from app.utils.logger import get_logger
from app.utils import yield_tracker

log = get_logger("enrichment_waterfall")


def _is_indiamart(url: str) -> bool:
    return bool(url) and "indiamart.com" in url


def _is_website(url: str) -> bool:
    return bool(url) and url.startswith("http") and "indiamart.com" not in url


def enrich_lead(db: Session, lead: Lead) -> dict:
    """
    Run the waterfall on one lead. Mutates the lead in-session (caller commits).

    Returns summary: {source_used, gained: [fields], queued_for_manual, evaluation}
    """
    gained = []
    source_used = None

    url = (lead.company_url or "").strip()

    extracted = {}
    if _is_indiamart(url):
        source_used = "indiamart_profile"
        extracted = extract_indiamart_profile(url)
    elif _is_website(url):
        source_used = "website"
        extracted = extract_website_contacts(url)

    if extracted and not extracted.get("error"):
        # Decision-maker (never overwrite existing data with weaker data)
        if extracted.get("contact_name") and not lead.full_name:
            lead.full_name = extracted["contact_name"]
            lead.decision_maker = extracted["contact_name"]
            gained.append("contact_name")
        if extracted.get("contact_title") and not lead.title:
            lead.title = extracted["contact_title"]
            gained.append("title")
        if extracted.get("email") and not lead.email and has_valid_email(extracted["email"]):
            lead.email = extracted["email"]
            gained.append("email")
        if extracted.get("phone") and not lead.phone and has_valid_phone(extracted["phone"]):
            lead.phone = extracted["phone"]
            gained.append("phone")
        if extracted.get("gst_number") and not lead.gst_number:
            lead.gst_number = extracted["gst_number"]
            gained.append("gst_number")

    # Rescore with whatever we now have
    evaluation = score_and_qualify(lead)
    lead.score = evaluation["score"]

    if evaluation["qualified"]:
        lead.status = "qualified"
        yield_tracker.increment(db, lead.source, "final_qualified")
        # Module 3: enrichment can push a lead over the hot bar
        try:
            from app.revenue.hot_trigger import trigger_if_hot
            trigger_if_hot(lead)
        except Exception as e:
            log.error("hot_trigger_error", error=str(e))
    elif gained:
        lead.status = "enriched"
        yield_tracker.increment(db, lead.source, "enriched_leads")
    # else: keep current status

    # Human queue: good company but automation couldn't find a decision-maker
    queued = False
    if "decision_maker" in evaluation["missing"] and evaluation["score"] >= 40:
        already = db.query(ManualReviewQueue).filter(
            ManualReviewQueue.lead_id == lead.id,
            ManualReviewQueue.status.in_(("pending", "in_progress")),
        ).first()
        if not already:
            db.add(ManualReviewQueue(
                lead_id=lead.id,
                reason="missing_decision_maker",
                priority="high" if evaluation["score"] >= 55 else "medium",
                status="pending",
                notes=f"Auto-queued by enrichment waterfall ({source_used or 'no source'}). "
                      f"Score {evaluation['score']}. Find Plant/Factory/IT Manager or Owner.",
                created_at=datetime.utcnow(),
            ))
            queued = True

    log.info("lead_enriched", company=lead.company_name, source_used=source_used,
             gained=gained, score=evaluation["score"], qualified=evaluation["qualified"],
             queued=queued)

    return {
        "source_used": source_used,
        "gained": gained,
        "queued_for_manual": queued,
        "evaluation": evaluation,
        "error": extracted.get("error") if extracted else "no_url",
    }
