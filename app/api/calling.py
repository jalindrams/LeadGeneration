"""
Micraft Growth Engine - Calling System API
Endpoints for tracking calls, dashboard stats, and CSV import.
"""
from datetime import date, datetime
import csv
import io
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from pydantic import BaseModel as _BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Lead, CallLog, User, LeadFeedback, LeadAssignment
from app.schemas import CallLogCreate, CallLogResponse, CallUpdateRequest, DashboardStats, LeadResponse
from app.auth import require_auth

router = APIRouter(prefix="/api/calling", tags=["Calling"])

@router.get("/dashboard", response_model=DashboardStats)
def get_dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(require_auth)):
    """Get high-level stats for the calling dashboard."""
    today = date.today()
    
    call_query = db.query(CallLog).filter(func.date(CallLog.called_at) == today)
    lead_query = db.query(Lead)
    
    if current_user.role != "admin":
        call_query = call_query.join(Lead).filter(Lead.assigned_to == current_user.id)
        lead_query = lead_query.filter(Lead.assigned_to == current_user.id)
    
    total_calls = call_query.count()
    connected = call_query.filter(CallLog.call_status != "no_answer").count()
    interested = call_query.filter(CallLog.call_status == "interested").count()
    
    follow_ups = lead_query.filter(
        Lead.call_status == "follow_up",
        Lead.follow_up_date <= today
    ).count()
    
    return DashboardStats(
        total_calls_today=total_calls,
        connected_today=connected,
        interested_today=interested,
        follow_ups_pending=follow_ups
    )

@router.put("/leads/{lead_id}/update-call", response_model=CallLogResponse)
def update_lead_call(
    lead_id: UUID,
    request: CallUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Log a call and update the lead's status."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    # Update lead
    lead.call_status = request.call_status
    if request.decision_maker:
        lead.decision_maker = request.decision_maker
    if request.pain_point:
        lead.pain_point = request.pain_point
    if request.follow_up_date:
        lead.follow_up_date = request.follow_up_date
    if request.remarks:
        lead.remarks = request.remarks
    
    lead.call_count += 1

    # --- Wire into the Sales Feedback Loop (Module 2) ---
    # Map the calling UI's status to a canonical response_status.
    CALL_TO_RESPONSE = {
        "interested": "interested",
        "not_interested": "not_interested",
        "no_answer": "no_response",
        "closed": "wrong_contact",   # "closed / dead" usually means bad contact
        "follow_up": None,           # still in play; don't set a terminal response
        "new": None,
    }
    canonical = CALL_TO_RESPONSE.get(request.call_status)
    now = datetime.utcnow()
    if canonical:
        lead.response_status = canonical
        db.add(LeadFeedback(lead_id=lead.id, status=canonical,
                            notes=request.remarks, created_at=now))
        lead.feedback_count = (lead.feedback_count or 0) + 1
    if not lead.first_contacted_at:
        lead.first_contacted_at = now
    lead.last_contacted_at = now
    lead.outreach_status = "contacted"
    lead.last_outreach_channel = "call"

    # Rescore so bad numbers sink and interested leads rise
    from app.processing.scorer import score_and_qualify
    evaluation = score_and_qualify(lead)
    lead.score = evaluation["score"]
    if evaluation["qualified"] and lead.status in ("raw", "enriched"):
        lead.status = "qualified"

    # Create call log entry
    call_log = CallLog(
        lead_id=lead.id,
        duration_note=request.duration_note,
        call_status=request.call_status,
        response_type=request.response_type,
        remarks=request.remarks,
        called_by=current_user.full_name
    )

    db.add(call_log)
    db.commit()
    db.refresh(call_log)

    return call_log


# --- Lead transfer (rep -> rep) + quick one-tap logging ---

class TransferRequest(_BaseModel):
    to_user_id: int
    note: Optional[str] = None


@router.post("/leads/{lead_id}/transfer")
def transfer_lead(
    lead_id: UUID,
    payload: TransferRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Hand a lead to another rep. Reps can transfer their own leads; admin any."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(404, "Lead not found")
    if current_user.role != "admin" and lead.assigned_to != current_user.id:
        raise HTTPException(403, "You can only transfer leads assigned to you")

    target = db.query(User).filter(User.id == payload.to_user_id,
                                   User.is_active == True).first()
    if not target:
        raise HTTPException(404, "Target rep not found or inactive")

    lead.assigned_to = target.id
    lead.assigned_at = datetime.utcnow()
    db.add(LeadAssignment(lead_id=lead.id, assigned_to=target.id,
                          assigned_by=current_user.id))
    note = f"Transferred to {target.full_name} by {current_user.full_name}"
    if payload.note:
        note += f": {payload.note}"
    lead.remarks = ((lead.remarks or "") + f"\n{note}").strip()
    db.commit()
    return {"ok": True, "assigned_to": target.full_name}


@router.get("/reps")
def list_reps(db: Session = Depends(get_db), current_user: User = Depends(require_auth)):
    """Active users a lead can be transferred to (for the transfer picker)."""
    reps = db.query(User).filter(User.is_active == True).order_by(User.full_name).all()
    return [{"id": u.id, "full_name": u.full_name, "role": u.role}
            for u in reps if u.id != current_user.id]

@router.get("/follow-ups", response_model=list[LeadResponse])
def get_follow_ups(db: Session = Depends(get_db)):
    """Get all leads requesting follow-up, ordered by date."""
    leads = db.query(Lead).filter(
        Lead.call_status == "follow_up"
    ).order_by(
        Lead.follow_up_date.asc().nulls_last(),
        Lead.lead_created_at.desc()
    ).all()
    
    return [LeadResponse.model_validate(l) for l in leads]

@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import leads from CSV."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(400, "Invalid file format. Upload a CSV.")
    
    contents = await file.read()
    decoded = contents.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    
    imported_count = 0
    duplicate_count = 0
    
    for row in reader:
        # Basic mapping - expecting standard headers
        company_name = row.get("Company Name", "").strip()
        if not company_name:
            continue
            
        full_name = row.get("Contact Person", "").strip()
        phone = row.get("Phone", "").strip()
        email = row.get("Email", "").strip()
        
        # Check if company already exists
        existing = db.query(Lead).filter(Lead.company_name == company_name).first()
        if existing:
            duplicate_count += 1
            continue
            
        new_lead = Lead(
            company_name=company_name,
            full_name=full_name,
            phone=phone,
            email=email,
            location=row.get("Location", "").strip(),
            industry=row.get("Industry", "").strip(),
            source=row.get("Source", "csv_import").strip() or "csv_import",
            call_status="new"
        )
        db.add(new_lead)
        imported_count += 1
        
    db.commit()
    return {
        "success": True, 
        "imported": imported_count, 
        "skipped": duplicate_count,
        "message": f"Successfully imported {imported_count} leads. Skipped {duplicate_count} duplicates."
    }


# --- Human Intelligence Queue (Module 4) ---

from app.models import ManualReviewQueue


class ReviewResolveRequest(_BaseModel):
    status: str  # resolved | skipped | in_progress
    notes: Optional[str] = None


@router.post("/review/{item_id}/resolve")
def resolve_review_item(
    item_id: int,
    payload: ReviewResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    """Mark a manual-review queue item resolved/skipped (rescores the lead)."""
    if payload.status not in ("resolved", "skipped", "in_progress"):
        raise HTTPException(400, "status must be resolved, skipped or in_progress")

    item = db.query(ManualReviewQueue).filter(ManualReviewQueue.id == item_id).first()
    if not item:
        raise HTTPException(404, "queue item not found")

    item.status = payload.status
    if payload.notes:
        item.notes = ((item.notes or "") + f"\n[{current_user.full_name}] {payload.notes}").strip()
    if payload.status in ("resolved", "skipped"):
        item.resolved_at = datetime.utcnow()

    # Rescore the lead — the researcher may have just filled title/phone/email
    lead = db.query(Lead).filter(Lead.id == item.lead_id).first()
    result = None
    if lead:
        from app.processing.scorer import score_and_qualify
        evaluation = score_and_qualify(lead)
        lead.score = evaluation["score"]
        if evaluation["qualified"] and lead.status in ("raw", "enriched"):
            lead.status = "qualified"
        result = {"score": lead.score, "qualified": evaluation["qualified"]}

    db.commit()
    return {"ok": True, "item_status": item.status, "lead": result}
