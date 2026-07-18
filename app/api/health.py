"""
Micraft Growth Engine - Health Check API
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import Lead
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Check system health: API status, DB connectivity, lead count."""
    db_status = "disconnected"
    leads_count = 0

    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
        leads_count = db.query(Lead).count()
    except Exception as e:
        db_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        database=db_status,
        timestamp=datetime.utcnow(),
        leads_count=leads_count,
    )
