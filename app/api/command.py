"""
Micraft Growth Engine - Command Deck API

GET /api/command/deck    All data for the daily ops dashboard in one call
"""

from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Lead, ScrapeJob, OutreachLog, LeadFeedback

router = APIRouter(prefix="/api/command", tags=["command"])

PRODUCT_LABELS = {
    "calibration": "Calibration MS",
    "dms": "DMS",
    "mes": "MES",
    "tms": "TMS",
    "courier": "Courier MS",
    "ecom": "Ecom / Shiplystic",
}


@router.get("/deck")
def command_deck(db: Session = Depends(get_db), user=Depends(require_admin)):
    """
    Single endpoint powering the Command Deck dashboard.

    Returns today_stats, morning_calls, hot_alerts, pipeline_health,
    harvest_status, outreach_snapshot, recent_activity.
    """
    now = datetime.utcnow()
    today_start = datetime.combine(date.today(), datetime.min.time())
    week_ago = now - timedelta(days=7)
    thirty_ago = now - timedelta(days=30)

    # ── Today's Stats ─────────────────────────────────────────────────────
    leads_today = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.lead_created_at >= today_start,
    ).count()

    hot_count = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.score >= 70,
    ).count()

    calls_today = db.query(LeadFeedback).filter(
        LeadFeedback.created_at >= today_start,
    ).count()

    try:
        outreach_today = db.query(OutreachLog).filter(
            OutreachLog.created_at >= today_start,
            OutreachLog.status == "sent",
        ).count()
    except Exception:
        outreach_today = 0

    # New leads this week
    leads_week = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.lead_created_at >= week_ago,
    ).count()

    # Interested / converted
    interested = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.response_status == "interested",
    ).count()
    converted = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.response_status == "converted",
    ).count()

    today_stats = {
        "leads_added_today": leads_today,
        "leads_added_week":  leads_week,
        "calls_logged_today": calls_today,
        "outreach_sent_today": outreach_today,
        "hot_leads_total": hot_count,
        "interested": interested,
        "converted": converted,
    }

    # ── Morning Call List ─────────────────────────────────────────────────
    # Hot + warm leads with phone, never called or follow-up overdue
    call_q = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.phone.isnot(None),
        Lead.call_status.in_(["new", "follow_up"]),
        Lead.score >= 40,
    ).order_by(
        Lead.score.desc(),
        Lead.follow_up_date.asc().nullslast(),
        Lead.lead_created_at.desc(),
    ).limit(15)

    morning_calls = [
        {
            "id":             str(l.id),
            "full_name":      l.full_name,
            "company_name":   l.company_name,
            "target_product": l.target_product,
            "phone":          l.phone,
            "score":          l.score,
            "call_status":    l.call_status,
            "follow_up_date": l.follow_up_date.isoformat() if l.follow_up_date else None,
            "source":         l.source,
        }
        for l in call_q.all()
    ]

    # ── Hot Alerts — new hot leads this week ─────────────────────────────
    hot_new = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.score >= 70,
        Lead.lead_created_at >= week_ago,
    ).order_by(Lead.score.desc(), Lead.lead_created_at.desc()).limit(10).all()

    hot_alerts = [
        {
            "id":             str(l.id),
            "full_name":      l.full_name,
            "company_name":   l.company_name,
            "target_product": l.target_product,
            "score":          l.score,
            "phone":          bool(l.phone),
            "email":          bool(l.email),
            "source":         l.source,
            "added":          l.lead_created_at.isoformat() if l.lead_created_at else None,
        }
        for l in hot_new
    ]

    # ── Pipeline Health ───────────────────────────────────────────────────
    total_leads = db.query(Lead).filter(Lead.status != "synthetic").count()

    # By call status
    status_rows = (
        db.query(Lead.call_status, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.call_status)
        .all()
    )
    by_call_status = {s: c for s, c in status_rows}

    # By product
    prod_rows = (
        db.query(Lead.target_product, func.count(Lead.id))
        .filter(Lead.status != "synthetic")
        .group_by(Lead.target_product)
        .all()
    )
    by_product = {(p or "unknown"): c for p, c in prod_rows}

    # Score distribution
    score_hot  = db.query(Lead).filter(Lead.status != "synthetic", Lead.score >= 70).count()
    score_warm = db.query(Lead).filter(Lead.status != "synthetic", Lead.score >= 40, Lead.score < 70).count()
    score_cold = db.query(Lead).filter(Lead.status != "synthetic", Lead.score < 40).count()

    pipeline_health = {
        "total": total_leads,
        "by_call_status": by_call_status,
        "by_product": by_product,
        "tiers": {"hot": score_hot, "warm": score_warm, "cold": score_cold},
    }

    # ── Harvest Status — last job per source ─────────────────────────────
    harvest_sources = [
        "nabl_labs", "aipma_members", "exhibition_pdf",
        "iba_transporters", "d2c_brands", "re_dealers",
    ]
    harvest_status = []
    for src in harvest_sources:
        job = (
            db.query(ScrapeJob)
            .filter(ScrapeJob.source.ilike(f"%{src}%"))
            .order_by(ScrapeJob.started_at.desc())
            .first()
        )
        if job:
            harvest_status.append({
                "source":       job.source,
                "status":       job.status,
                "records":      job.records_stored or 0,
                "started_at":   job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            })
        else:
            harvest_status.append({
                "source": src, "status": "never_run", "records": 0,
                "started_at": None, "completed_at": None,
            })

    # ── Outreach Snapshot ─────────────────────────────────────────────────
    cooldown_cutoff = now - timedelta(days=3)
    outreach_ready = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.outreach_status.notin_(["exhausted", "opted_out"]),
        or_(Lead.response_status.is_(None), Lead.response_status == "no_response"),
        or_(Lead.follow_up_count.is_(None), Lead.follow_up_count < 3),
        or_(Lead.phone.isnot(None), Lead.email.isnot(None)),
        or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at <= cooldown_cutoff),
    ).count()

    try:
        outreach_sent_30d = db.query(OutreachLog).filter(
            OutreachLog.created_at >= thirty_ago,
            OutreachLog.status == "sent",
        ).count()
        wa_sent = db.query(OutreachLog).filter(
            OutreachLog.created_at >= thirty_ago,
            OutreachLog.channel == "whatsapp",
            OutreachLog.status == "sent",
        ).count()
    except Exception:
        outreach_sent_30d = 0
        wa_sent = 0

    outreach_snapshot = {
        "ready_to_contact": outreach_ready,
        "sent_30d": outreach_sent_30d,
        "wa_sent_30d": wa_sent,
        "email_sent_30d": outreach_sent_30d - wa_sent,
    }

    # ── Recent Activity ───────────────────────────────────────────────────
    recent_calls = db.query(LeadFeedback).order_by(
        LeadFeedback.created_at.desc()
    ).limit(6).all()

    recent_activity = [
        {
            "type":       "call",
            "lead_id":    str(f.lead_id),
            "outcome":    f.call_outcome,
            "notes":      (f.notes or "")[:60],
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in recent_calls
    ]

    return {
        "today_stats":      today_stats,
        "morning_calls":    morning_calls,
        "hot_alerts":       hot_alerts,
        "pipeline_health":  pipeline_health,
        "harvest_status":   harvest_status,
        "outreach_snapshot": outreach_snapshot,
        "recent_activity":  recent_activity,
        "generated_at":     now.isoformat(),
    }
