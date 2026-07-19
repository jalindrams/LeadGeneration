from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel
from datetime import datetime
from fastapi import BackgroundTasks
from fastapi.responses import StreamingResponse
import io
import csv
import subprocess
import os
import threading

from app.database import get_db
from app.models import User, Lead, LeadAssignment, ScrapeJob
from app.schemas import UserCreate, UserResponse, LeadAssignmentCreate
from app.auth import get_password_hash, require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.get("/users", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """List all users (admin only)"""
    return db.query(User).all()

@router.post("/users", response_model=UserResponse)
def create_user(user_in: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Create a new user (admin only)"""
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    user = User(
        username=user_in.username,
        password_hash=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

class UserStatusUpdate(BaseModel):
    is_active: bool

class BulkAssignCriteria(BaseModel):
    source: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    product: Optional[str] = None          # target_product filter
    has_phone: Optional[bool] = None
    min_score: Optional[int] = None        # only assign leads at/above this score
    include_assigned: Optional[bool] = False  # True = reassign already-assigned too
    target_rep_ids: List[int]

@router.post("/users/{user_id}/toggle-status")
def toggle_user_status(user_id: int, status_update: UserStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Toggle a user's active status"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot toggle your own status")
    
    user.is_active = status_update.is_active
    db.commit()
    return {"message": "Status updated"}

@router.post("/assign")
def assign_leads(assignment: LeadAssignmentCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Bulk assign leads to a user"""
    user = db.query(User).filter(User.id == assignment.assigned_to).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    for lead_id in assignment.lead_ids:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead:
            lead.assigned_to = user.id
            lead.assigned_at = func.now()
            
            log_assignment = LeadAssignment(
                lead_id=lead_id,
                assigned_to=user.id,
                assigned_by=current_user.id
            )
            db.add(log_assignment)
            
    db.commit()
    return {"message": f"Assigned {len(assignment.lead_ids)} leads to {user.full_name}"}

@router.post("/assign-bulk")
def assign_leads_bulk(criteria: BulkAssignCriteria, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Bulk assign unassigned leads based on criteria, distributed round-robin across selected reps."""
    if not criteria.target_rep_ids:
        raise HTTPException(status_code=400, detail="No target reps selected")
        
    # Verify reps exist (admins can also self-assign for important leads)
    reps = db.query(User).filter(User.id.in_(criteria.target_rep_ids),
                                 User.is_active == True).all()
    if len(reps) != len(criteria.target_rep_ids):
        raise HTTPException(status_code=400, detail="One or more selected reps are invalid")

    query = db.query(Lead).filter(Lead.status != "synthetic")
    # Reassign mode includes already-assigned leads; default = only unassigned
    if not criteria.include_assigned:
        query = query.filter(Lead.assigned_to.is_(None))

    if criteria.source:
        query = query.filter(Lead.source == criteria.source)
    if criteria.product:
        query = query.filter(Lead.target_product == criteria.product)
    if criteria.industry:
        query = query.filter(Lead.industry.ilike(f"%{criteria.industry}%"))
    if criteria.city:
        query = query.filter(Lead.location.ilike(f"%{criteria.city}%"))
    if criteria.has_phone:
        query = query.filter(Lead.phone.isnot(None), Lead.phone != "")
    if criteria.min_score is not None:
        query = query.filter(Lead.score >= criteria.min_score)

    # Best leads first so they're distributed evenly by quality
    leads = query.order_by(Lead.score.desc()).all()

    if not leads:
        return {"message": "No leads found matching criteria", "assigned_count": 0}

    rep_count = len(reps)
    for i, lead in enumerate(leads):
        rep = reps[i % rep_count]
        lead.assigned_to = rep.id
        lead.assigned_at = func.now()
        db.add(LeadAssignment(lead_id=lead.id, assigned_to=rep.id,
                              assigned_by=current_user.id))

    db.commit()
    verb = "Reassigned" if criteria.include_assigned else "Assigned"
    return {
        "message": f"{verb} {len(leads)} leads across {rep_count} rep(s), highest-score first.",
        "assigned_count": len(leads)
    }

@router.get("/export")
def export_leads(
    source: Optional[str] = None,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    assigned: Optional[str] = None,
    after_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Export leads as CSV with optional filters"""
    query = db.query(Lead).filter(Lead.status != "synthetic")
    if source:
        query = query.filter(Lead.source == source)
    if industry:
        query = query.filter(Lead.industry.ilike(f"%{industry}%"))
    if city:
        query = query.filter(Lead.location.ilike(f"%{city}%"))
    
    if assigned:
        if assigned.lower() == "true":
            query = query.filter(Lead.assigned_to.isnot(None))
        elif assigned.lower() == "false":
            query = query.filter(Lead.assigned_to.is_(None))
            
    if after_date:
        try:
            date_obj = datetime.strptime(after_date, "%Y-%m-%d")
            query = query.filter(Lead.lead_created_at >= date_obj)
        except ValueError:
            pass

    leads = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Company Name", "Contact Person", "Phone", "Email", "Location", "Industry", "Turnover", "Status", "Score", "Source"])
    
    for lead in leads:
        writer.writerow([
            lead.company_name,
            lead.full_name,
            lead.phone,
            lead.email,
            lead.location,
            lead.industry,
            lead.turnover,
            lead.status,
            lead.score,
            lead.source
        ])
        
    output.seek(0)
    response = StreamingResponse(iter([output.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=leads_export.csv"
    return response

class ScrapeRequest(BaseModel):
    source: str = "indiamart"
    cities: List[str]
    industries: List[str]
    turnovers: List[str] = []
    target_leads: int = 50

class ScraperState:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_process = None
        self.halt_flag = False
        self.total_queries = 0
        self.completed_queries = 0
        self.current_query = ""
        self.current_city = ""
        self.is_running = False
        self.target_leads = 50

scraper_state = ScraperState()

@router.get("/scraper-status")
def get_scraper_status(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    """Get the status of running and recently completed scraping jobs"""
    jobs = db.query(ScrapeJob).filter(ScrapeJob.status == "running").all()
    recent = db.query(ScrapeJob).filter(ScrapeJob.status == "completed").order_by(ScrapeJob.completed_at.desc()).limit(5).all()
    
    with scraper_state.lock:
        is_running = scraper_state.is_running
        total_q = scraper_state.total_queries
        completed_q = scraper_state.completed_queries
        curr_city = scraper_state.current_city
        curr_query = scraper_state.current_query
        target_l = scraper_state.target_leads
        halting = scraper_state.halt_flag

    total_running_stored = sum((j.records_stored or 0) for j in jobs)
    
    # Auto-halt if target reached
    if is_running and total_running_stored >= target_l and not halting:
        with scraper_state.lock:
            scraper_state.halt_flag = True
            if scraper_state.current_process:
                try:
                    scraper_state.current_process.terminate()
                except:
                    pass

    return {
        "running": [
            {
                "id": j.id, 
                "source": j.source, 
                "query": j.search_query, 
                "found": j.records_found,
                "stored": j.records_stored,
                "status": j.status
            } for j in jobs
        ],
        "completed": [
            {
                "id": j.id,
                "source": j.source,
                "query": j.search_query,
                "stored": j.records_stored,
                "completed_at": j.completed_at
            } for j in recent
        ],
        "overall_state": {
            "is_running": is_running,
            "halting": halting,
            "total_queries": total_q,
            "completed_queries": completed_q,
            "current_city": curr_city,
            "current_query": curr_query,
            "target_leads": target_l,
            "current_leads": total_running_stored
        }
    }

@router.post("/start-scraper")
def start_scraper(
    request: ScrapeRequest, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin)
):
    """Start the scraper asynchronously with custom industry and turnover parameters"""
    with scraper_state.lock:
        if scraper_state.is_running and not scraper_state.halt_flag:
            raise HTTPException(status_code=400, detail="A scraper job is already running.")

    queries = []
    for ind in request.industries:
        if request.turnovers:
            for t in request.turnovers:
                queries.append(f"{ind} {t} turnover")
        else:
            queries.append(ind)

    with scraper_state.lock:
        scraper_state.total_queries = len(queries) * len(request.cities)
        scraper_state.completed_queries = 0
        scraper_state.halt_flag = False
        scraper_state.is_running = True
        scraper_state.target_leads = request.target_leads

    def run_scraper_task(source: str, cities: List[str], search_queries: List[str]):
        # We set max_pages high, but we'll terminate it externally when target is reached
        max_pages = 20 
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "run_scraper.py")
        try:
            for city in cities:
                for q in search_queries:
                    with scraper_state.lock:
                        if scraper_state.halt_flag:
                            break
                        scraper_state.current_city = city
                        scraper_state.current_query = q
                    
                    cmd = ["python", script_path, "--source", source, "--city", city, "--query", q, "--max-pages", str(max_pages)]
                    try:
                        proc = subprocess.Popen(cmd)
                        with scraper_state.lock:
                            scraper_state.current_process = proc
                        proc.wait()
                    except Exception as e:
                        print(f"Scraper task failed for query '{q}' in city '{city}': {e}")
                        
                    with scraper_state.lock:
                        scraper_state.current_process = None
                        scraper_state.completed_queries += 1
                        if scraper_state.halt_flag:
                            break
                if scraper_state.halt_flag:
                    break
        finally:
            with scraper_state.lock:
                scraper_state.is_running = False
                scraper_state.current_process = None
                scraper_state.halt_flag = False

    background_tasks.add_task(run_scraper_task, request.source, request.cities, queries)
    
    return {
        "message": "Scraper started in background", 
        "queries_count": len(queries) * len(request.cities),
        "target_leads": request.target_leads
    }

@router.post("/halt-scraper")
def halt_scraper(current_user: User = Depends(require_admin)):
    """Halt the currently running scraper"""
    with scraper_state.lock:
        if not scraper_state.is_running:
            return {"message": "No scraper is currently running"}
        scraper_state.halt_flag = True
        if scraper_state.current_process:
            try:
                scraper_state.current_process.terminate()
            except Exception as e:
                print(f"Failed to terminate process: {e}")
    return {"message": "Scraper halt requested"}
