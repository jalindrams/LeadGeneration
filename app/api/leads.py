"""
Micraft Growth Engine - Leads API
CRUD operations, search, filtering, and CSV export.
"""

import csv
import io
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.models import Lead
from app.schemas import LeadResponse, LeadListResponse, LeadCreate

router = APIRouter(prefix="/api/leads", tags=["Leads"])


@router.get("", response_model=LeadListResponse)
def list_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    source: Optional[str] = None,
    call_status: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    industry: Optional[str] = None,
    has_phone: Optional[bool] = None,
    has_email: Optional[bool] = None,
    assigned_to: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = Query("lead_created_at", enum=["lead_created_at", "score", "company_name"]),
    sort_order: str = Query("desc", enum=["asc", "desc"]),
    db: Session = Depends(get_db),
):
    """
    List leads with filtering, search, and pagination.
    """
    query = db.query(Lead).filter(Lead.status != "synthetic")

    # Apply filters
    if source:
        query = query.filter(Lead.source == source)
    if call_status:
        query = query.filter(Lead.call_status == call_status)
    if status:
        query = query.filter(Lead.status == status)
    if city:
        query = query.filter(Lead.location.ilike(f"%{city}%"))
    if industry:
        query = query.filter(Lead.industry.ilike(f"%{industry}%"))
    if has_phone is True:
        query = query.filter(Lead.phone.isnot(None), Lead.phone != "")
    if has_email is True:
        query = query.filter(Lead.email.isnot(None), Lead.email != "")
    if assigned_to == "unassigned":
        query = query.filter(Lead.assigned_to.is_(None))
    elif assigned_to and assigned_to.isdigit():
        query = query.filter(Lead.assigned_to == int(assigned_to))
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            Lead.company_name.ilike(search_filter)
            | Lead.full_name.ilike(search_filter)
            | Lead.product_category.ilike(search_filter)
        )

    # Get total count
    total = query.count()

    # Sort
    sort_col = getattr(Lead, sort_by, Lead.lead_created_at)
    if sort_order == "desc":
        query = query.order_by(desc(sort_col))
    else:
        query = query.order_by(sort_col)

    # Paginate
    offset = (page - 1) * per_page
    leads = query.offset(offset).limit(per_page).all()

    return LeadListResponse(
        leads=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/stats")
def lead_stats(db: Session = Depends(get_db)):
    """Get summary statistics for all leads."""
    real = db.query(Lead).filter(Lead.status != "synthetic")
    total = real.count()
    by_source = dict(
        db.query(Lead.source, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.source)
        .all()
    )
    by_status = dict(
        db.query(Lead.status, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.status)
        .all()
    )
    by_city = dict(
        db.query(Lead.location, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.location)
        .order_by(desc(func.count(Lead.id)))
        .limit(10)
        .all()
    )
    with_phone = real.filter(Lead.phone.isnot(None), Lead.phone != "").count()
    with_email = real.filter(Lead.email.isnot(None), Lead.email != "").count()
    by_call_status = dict(
        db.query(Lead.call_status, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.call_status)
        .all()
    )

    return {
        "total_leads": total,
        "by_source": by_source,
        "by_status": by_status,
        "by_call_status": by_call_status,
        "top_cities": by_city,
        "with_phone": with_phone,
        "with_email": with_email,
        "with_phone_pct": round(with_phone / total * 100, 1) if total > 0 else 0,
        "with_email_pct": round(with_email / total * 100, 1) if total > 0 else 0,
    }


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: UUID, db: Session = Depends(get_db)):
    """Get a single lead by ID."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return LeadResponse.model_validate(lead)


@router.get("/export/csv")
def export_csv(
    source: Optional[str] = None,
    status: Optional[str] = None,
    city: Optional[str] = None,
    has_phone: Optional[bool] = None,
    after_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export leads as CSV file for sales team.
    Filters same as list endpoint.
    """
    query = db.query(Lead).filter(Lead.status != "synthetic")

    if source:
        query = query.filter(Lead.source == source)
    if status:
        query = query.filter(Lead.status == status)
    if city:
        query = query.filter(Lead.location.ilike(f"%{city}%"))
    if has_phone is True:
        query = query.filter(Lead.phone.isnot(None), Lead.phone != "")
        
    if after_date:
        try:
            date_obj = datetime.strptime(after_date, "%Y-%m-%d")
            query = query.filter(Lead.lead_created_at >= date_obj)
        except ValueError:
            pass

    leads = query.order_by(desc(Lead.lead_created_at)).all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Company Name", "Contact Person", "Designation", "Phone", "Email",
        "Location", "Industry", "Product Category", "Company Website",
        "Source", "GST Number", "Status", "Date Collected",
    ])

    # Data rows
    for lead in leads:
        writer.writerow([
            lead.company_name,
            lead.full_name or "",
            lead.title or "",
            lead.phone or "",
            lead.email or "",
            lead.location or "",
            lead.industry or "",
            lead.product_category or "",
            lead.company_url or "",
            lead.source,
            lead.gst_number or "",
            lead.status,
            lead.scraped_at.strftime("%Y-%m-%d") if lead.scraped_at else "",
        ])

    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"micraft_leads_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
