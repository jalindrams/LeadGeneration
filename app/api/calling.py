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
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Lead, CallLog, User
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
