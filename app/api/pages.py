"""
Micraft Growth Engine - Pages API
Serves HTML templates for the Internal Lead Calling System.
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.models import Lead, User
from app.auth import require_auth, require_admin

router = APIRouter(prefix="/calling", tags=["Pages"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def calling_workboard(
    request: Request, 
    call_status: str = "new", 
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Lead Workboard UI."""
    per_page = 50
    offset = (page - 1) * per_page
    query = db.query(Lead)
    
    # Filter by assigned rep, unless admin
    if current_user.role != "admin":
        query = query.filter(Lead.assigned_to == current_user.id)
        
    if call_status and call_status != "all":
        query = query.filter(Lead.call_status == call_status)
        
    leads = query.order_by(Lead.lead_created_at.desc()).offset(offset).limit(per_page).all()
    
    return templates.TemplateResponse("workboard.html", {
        "request": request, 
        "leads": leads,
        "current_status": call_status,
        "page": page,
        "current_user": current_user
    })

@router.get("/lead/{lead_id}", response_class=HTMLResponse)
async def lead_detail(
    request: Request, 
    lead_id: UUID, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Lead Detail View."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
        
    # Check permissions
    if current_user.role != "admin" and lead.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
        
    return templates.TemplateResponse("lead_detail.html", {
        "request": request,
        "lead": lead,
        "current_user": current_user
    })

@router.get("/follow-ups", response_class=HTMLResponse)
async def follow_ups_page(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Follow-up System UI."""
    query = db.query(Lead).filter(Lead.call_status == "follow_up")
    
    if current_user.role != "admin":
        query = query.filter(Lead.assigned_to == current_user.id)
        
    leads = query.order_by(
        Lead.follow_up_date.asc().nulls_last(),
        Lead.lead_created_at.desc()
    ).all()
    
    return templates.TemplateResponse("follow_ups.html", {
        "request": request,
        "leads": leads,
        "current_user": current_user
    })

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, current_user: User = Depends(require_auth)):
    """Dashboard UI."""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": current_user
    })

@router.get("/import", response_class=HTMLResponse)
async def import_csv_page(request: Request, current_user: User = Depends(require_auth)):
    """CSV Import Integration UI."""
    return templates.TemplateResponse("import_csv.html", {
        "request": request,
        "current_user": current_user
    })

# --- Admin Pages ---

@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard_page(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, 
        "current_user": current_user
    })

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse("admin_users.html", {
        "request": request, 
        "current_user": current_user
    })

@router.get("/admin/assign", response_class=HTMLResponse)
async def admin_assign_page(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    users = db.query(User).filter(User.role == "sales_rep").all()
    return templates.TemplateResponse("admin_assign.html", {
        "request": request, 
        "current_user": current_user,
        "users": users
    })

@router.get("/admin/api", response_class=HTMLResponse)
async def admin_api_page(request: Request, current_user: User = Depends(require_admin)):
    """API Integrations & Explorer UI."""
    return templates.TemplateResponse("admin_api.html", {
        "request": request,
        "current_user": current_user
    })
