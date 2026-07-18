"""
Micraft Growth Engine - Pipeline Metrics API
Exposes yield tracking data (Module 1).
"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import LeadPipelineMetrics, ScrapeJob
from app.schemas import PipelineMetricsResponse, PipelineSummary
from app.utils import yield_tracker

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


@router.get("/pipeline", response_model=list[PipelineMetricsResponse])
def get_pipeline_metrics(
    source: Optional[str] = None,
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Get pipeline metrics for the last N days, optionally filtered by source."""
    start_date = date.today() - timedelta(days=days)

    query = db.query(LeadPipelineMetrics).filter(
        LeadPipelineMetrics.date >= start_date
    )

    if source:
        query = query.filter(LeadPipelineMetrics.source == source)

    rows = query.order_by(LeadPipelineMetrics.date.desc()).all()
    return [PipelineMetricsResponse.model_validate(r) for r in rows]


@router.get("/summary", response_model=PipelineSummary)
def get_pipeline_summary(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """Get aggregated pipeline summary across all sources."""
    start_date = date.today() - timedelta(days=days)

    rows = db.query(LeadPipelineMetrics).filter(
        LeadPipelineMetrics.date >= start_date
    ).all()

    summary = {
        "total_raw": 0,
        "total_enriched": 0,
        "total_verified": 0,
        "total_deduped": 0,
        "total_qualified": 0,
        "total_pushed": 0,
        "total_contacted": 0,
        "total_converted": 0,
        "sources": {},
        "date_range": {
            "start": str(start_date),
            "end": str(date.today()),
        },
    }

    for row in rows:
        summary["total_raw"] += row.raw_leads or 0
        summary["total_enriched"] += row.enriched_leads or 0
        summary["total_verified"] += row.verified_leads or 0
        summary["total_deduped"] += row.deduped_leads or 0
        summary["total_qualified"] += row.final_qualified or 0
        summary["total_pushed"] += row.pushed_to_crm or 0
        summary["total_contacted"] += row.contacted or 0
        summary["total_converted"] += row.converted or 0

        source_total = summary["sources"].get(row.source, 0)
        summary["sources"][row.source] = source_total + (row.raw_leads or 0)

    return PipelineSummary(**summary)


@router.get("/today")
def get_today_metrics(db: Session = Depends(get_db)):
    """Get today's real-time pipeline metrics."""
    return yield_tracker.get_today_summary(db)


@router.get("/jobs", response_model=list)
def get_recent_jobs(
    limit: int = Query(20, ge=1, le=100),
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get recent scrape jobs with their stats."""
    from app.schemas import ScrapeJobResponse

    query = db.query(ScrapeJob)
    if source:
        query = query.filter(ScrapeJob.source == source)

    jobs = query.order_by(ScrapeJob.started_at.desc()).limit(limit).all()
    return [ScrapeJobResponse.model_validate(j) for j in jobs]


@router.get("/speed-to-lead")
def get_speed_to_lead(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)):
    """
    Module 6: time from lead creation to first contact, by tier.
    Targets: hot < 15 min, warm < 4 h, cold < 24 h.
    """
    from datetime import datetime
    from app.models import Lead

    since = datetime.utcnow() - timedelta(days=days)
    leads = (
        db.query(Lead)
        .filter(Lead.status != "synthetic")
        .filter(Lead.first_contacted_at.isnot(None))
        .filter(Lead.lead_created_at >= since)
        .all()
    )

    def tier_of(score):
        return "hot" if (score or 0) >= 70 else "warm" if (score or 0) >= 40 else "cold"

    buckets = {"hot": [], "warm": [], "cold": []}
    for lead in leads:
        delta_min = (lead.first_contacted_at - lead.lead_created_at).total_seconds() / 60
        if delta_min >= 0:
            buckets[tier_of(lead.score)].append(delta_min)

    targets_min = {"hot": 15, "warm": 240, "cold": 1440}
    out = {}
    for tier, values in buckets.items():
        out[tier] = {
            "contacted": len(values),
            "avg_minutes": round(sum(values) / len(values), 1) if values else None,
            "target_minutes": targets_min[tier],
            "within_target_pct": round(
                sum(1 for v in values if v <= targets_min[tier]) / len(values) * 100, 1
            ) if values else None,
        }
    return {"days": days, "tiers": out}


@router.get("/source-performance")
def get_source_performance(
    recompute: bool = Query(False, description="Recompute before returning"),
    period_days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
):
    """Module 7: per-source quality scores + SCALE/MAINTAIN/REDUCE/KILL."""
    from app.revenue.source_scorer import compute_source_performance
    from app.models import SourcePerformance

    if recompute:
        return compute_source_performance(db, period_days=period_days)

    rows = (
        db.query(SourcePerformance)
        .order_by(SourcePerformance.period_start.desc(),
                  SourcePerformance.source_score.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "source": r.source,
            "period": f"{r.period_start} → {r.period_end}",
            "total_raw": r.total_raw,
            "qualified": r.total_qualified,
            "contacted": r.total_contacted,
            "conversion_rate": float(r.conversion_rate or 0),
            "response_rate": float(r.response_rate or 0),
            "data_completeness": float(r.data_completeness or 0),
            "source_score": float(r.source_score or 0),
            "recommendation": r.recommendation,
        }
        for r in rows
    ]
