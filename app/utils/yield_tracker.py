"""
Micraft Growth Engine - Yield Tracker (Module 1)
Tracks lead counts at each pipeline stage per source per day.
Auto-increments counters in lead_pipeline_metrics table.
"""

from datetime import date
from sqlalchemy.orm import Session
from app.models import LeadPipelineMetrics
from app.utils.logger import get_logger

log = get_logger("yield_tracker")

# Valid pipeline stages that can be incremented
STAGES = [
    "raw_leads",
    "enriched_leads",
    "verified_leads",
    "deduped_leads",
    "final_qualified",
    "pushed_to_crm",
    "contacted",
    "converted",
]


def _get_or_create_metrics(db: Session, source: str, target_date: date = None) -> LeadPipelineMetrics:
    """Get or create a metrics row for a given source and date."""
    if target_date is None:
        target_date = date.today()

    metrics = db.query(LeadPipelineMetrics).filter(
        LeadPipelineMetrics.source == source,
        LeadPipelineMetrics.date == target_date,
    ).first()

    if not metrics:
        metrics = LeadPipelineMetrics(source=source, date=target_date)
        db.add(metrics)
        db.flush()
        log.info("created_metrics_row", source=source, date=str(target_date))

    return metrics


def increment(db: Session, source: str, stage: str, count: int = 1):
    """
    Increment a pipeline stage counter for a source on today's date.

    Args:
        db: Database session
        source: Lead source name (e.g., 'indiamart', 'google_maps')
        stage: Pipeline stage (e.g., 'raw_leads', 'deduped_leads')
        count: Number to increment by (default 1)
    """
    if stage not in STAGES:
        log.warning("invalid_stage", stage=stage, valid_stages=STAGES)
        return

    metrics = _get_or_create_metrics(db, source)
    current = getattr(metrics, stage, 0) or 0
    setattr(metrics, stage, current + count)
    db.commit()

    log.info("yield_incremented", source=source, stage=stage, count=count, new_total=current + count)


def get_today_summary(db: Session) -> dict:
    """Get today's pipeline metrics summary across all sources."""
    today = date.today()
    rows = db.query(LeadPipelineMetrics).filter(
        LeadPipelineMetrics.date == today
    ).all()

    summary = {
        "date": str(today),
        "sources": {},
        "totals": {stage: 0 for stage in STAGES},
    }

    for row in rows:
        source_data = {}
        for stage in STAGES:
            val = getattr(row, stage, 0) or 0
            source_data[stage] = val
            summary["totals"][stage] += val
        summary["sources"][row.source] = source_data

    return summary
