"""
Micraft Growth Engine - Sales Feedback API (Module 2)
POST /api/lead-feedback — reps (or HubSpot webhooks) record call outcomes.
Each feedback immediately rescores the lead so bad numbers sink and
interested leads rise.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Lead, LeadFeedback
from app.processing.scorer import score_and_qualify
from app.revenue.hot_trigger import trigger_if_hot

router = APIRouter(prefix="/api", tags=["Feedback"])

VALID_STATUSES = {"interested", "not_interested", "no_response", "wrong_contact", "converted"}

CALL_STATUS_MAP = {
    "interested": "interested",
    "not_interested": "not_interested",
    "wrong_contact": "closed",
    "no_response": "no_answer",
    "converted": "closed",
}

PRECEDENCE = {"converted": 5, "interested": 4, "not_interested": 3,
              "wrong_contact": 2, "no_response": 1}


class FeedbackIn(BaseModel):
    lead_id: str
    status: str
    notes: Optional[str] = None
    channel: Optional[str] = "call"


@router.post("/lead-feedback")
def submit_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    if payload.status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")

    lead = db.query(Lead).filter(Lead.id == payload.lead_id).first()
    if not lead:
        raise HTTPException(404, "lead not found")

    now = datetime.utcnow()
    db.add(LeadFeedback(lead_id=lead.id, status=payload.status,
                        notes=payload.notes, created_at=now))

    # Roll up to the lead (most-informative outcome wins)
    if (not lead.response_status
            or PRECEDENCE.get(payload.status, 0) >= PRECEDENCE.get(lead.response_status, 0)):
        lead.response_status = payload.status
        lead.call_status = CALL_STATUS_MAP[payload.status]
    lead.feedback_count = (lead.feedback_count or 0) + 1
    if not lead.first_contacted_at:
        lead.first_contacted_at = now
    lead.last_contacted_at = now
    lead.outreach_status = "contacted"
    lead.last_outreach_channel = payload.channel

    # Rescore with the new feedback signal
    evaluation = score_and_qualify(lead)
    lead.score = evaluation["score"]
    if evaluation["qualified"] and lead.status in ("raw", "enriched"):
        lead.status = "qualified"

    db.commit()

    # Converted/interested leads crossing the hot bar re-alert the team
    alerted = trigger_if_hot(lead) if payload.status in ("interested", "converted") else False

    return {
        "ok": True,
        "lead_id": str(lead.id),
        "response_status": lead.response_status,
        "new_score": lead.score,
        "tier": evaluation["tier"],
        "qualified": evaluation["qualified"],
        "hot_alert_sent": alerted,
    }
