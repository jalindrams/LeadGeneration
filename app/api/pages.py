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
from app.models import Lead, User, ManualReviewQueue
from app.products import PRODUCT_PROFILES
from app.auth import require_auth, require_admin

router = APIRouter(prefix="/calling", tags=["Pages"])
templates = Jinja2Templates(directory="app/templates")


def tier_of(score) -> str:
    s = score or 0
    return "hot" if s >= 70 else "warm" if s >= 40 else "cold"


@router.get("/", response_class=HTMLResponse)
async def calling_workboard(
    request: Request,
    call_status: str = "new",
    product: str = "all",
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Lead Workboard UI — best leads first (score desc)."""
    per_page = 50
    offset = (page - 1) * per_page
    query = db.query(Lead).filter(Lead.status != "synthetic")

    # Filter by assigned rep, unless admin
    if current_user.role != "admin":
        query = query.filter(Lead.assigned_to == current_user.id)

    if call_status and call_status != "all":
        query = query.filter(Lead.call_status == call_status)

    if product and product != "all":
        query = query.filter(Lead.target_product == product)

    leads = (query.order_by(Lead.score.desc(), Lead.lead_created_at.desc())
             .offset(offset).limit(per_page).all())

    return templates.TemplateResponse("workboard.html", {
        "request": request,
        "leads": leads,
        "current_status": call_status,
        "current_product": product,
        "products": PRODUCT_PROFILES,
        "tier_of": tier_of,
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
        "tier": tier_of(lead.score),
        "current_user": current_user
    })

@router.get("/follow-ups", response_class=HTMLResponse)
async def follow_ups_page(
    request: Request, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Follow-up System UI."""
    query = db.query(Lead).filter(Lead.call_status == "follow_up",
                                  Lead.status != "synthetic")

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

@router.get("/review-queue", response_class=HTMLResponse)
async def review_queue_page(
    request: Request,
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth)
):
    """Human Intelligence Queue — leads needing manual research (Module 4)."""
    query = (
        db.query(ManualReviewQueue)
        .join(Lead, ManualReviewQueue.lead_id == Lead.id)
        .filter(Lead.status != "synthetic")
    )
    if status != "all":
        query = query.filter(ManualReviewQueue.status == status)

    priority_order = {"high": 0, "medium": 1, "low": 2}
    items = query.order_by(ManualReviewQueue.created_at.asc()).limit(200).all()
    items.sort(key=lambda i: priority_order.get(i.priority, 3))

    return templates.TemplateResponse("review_queue.html", {
        "request": request,
        "items": items,
        "current_status": status,
        "current_user": current_user,
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
