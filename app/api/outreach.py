"""
Micraft Growth Engine - Outreach API Endpoints

POST /api/outreach/send          Trigger a batch outreach run
POST /api/outreach/preview       Preview templates for a lead (no send)
GET  /api/outreach/stats         Outreach stats by channel / product / day
GET  /api/outreach/log           Outreach log (paginated)
GET  /api/outreach/cadence       Cadence pipeline — step counts + ready-to-contact leads
GET  /api/outreach/templates     All templates rendered with a sample lead
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from app.auth import require_auth, require_admin
from app.database import get_db
from app.models import Lead, OutreachLog
from app.outreach import cadence
from app.outreach.templates import select_template, render

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SendRequest(BaseModel):
    product: str = "all"
    tier: str = "hot"
    limit: int = 50
    cooldown_days: int = 3
    dry_run: bool = True   # default safe: must explicitly set False


class PreviewRequest(BaseModel):
    lead_id: str
    step: int = 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/send")
def trigger_send(
    req: SendRequest,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    """
    Trigger a batch outreach run.
    dry_run=true (default) returns a preview — no messages sent.
    Set dry_run=false to send live.
    """
    valid_products = {"all", "mes", "dms", "tms", "courier", "calibration", "ecom"}
    valid_tiers = {"all", "hot", "warm"}
    if req.product not in valid_products:
        raise HTTPException(400, f"product must be one of {valid_products}")
    if req.tier not in valid_tiers:
        raise HTTPException(400, f"tier must be one of {valid_tiers}")
    if req.limit > 200:
        raise HTTPException(400, "limit cannot exceed 200 per run")

    summary = cadence.run_batch(
        db=db,
        product=req.product,
        tier=req.tier,
        limit=req.limit,
        cooldown_days=req.cooldown_days,
        dry_run=req.dry_run,
    )
    return summary


@router.post("/preview")
def preview_template(
    req: PreviewRequest,
    db: Session = Depends(get_db),
    user=Depends(require_auth),
):
    """Preview the rendered template for a specific lead at a given step."""
    lead = db.query(Lead).filter(Lead.id == req.lead_id).first()
    if not lead:
        raise HTTPException(404, "lead not found")

    lead_dict = {
        "full_name": lead.full_name,
        "company_name": lead.company_name,
        "target_product": lead.target_product,
        "source": lead.source,
    }
    tkey = select_template(lead_dict, step=req.step)
    rendered = render(tkey, lead_dict)

    return {
        "lead_id": str(lead.id),
        "company_name": lead.company_name,
        "template_key": tkey,
        "step": req.step,
        **rendered,
    }


@router.get("/stats")
def outreach_stats(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    """Outreach stats over the last N days."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(
            OutreachLog.channel,
            OutreachLog.status,
            func.count(OutreachLog.id).label("count"),
        )
        .filter(OutreachLog.created_at >= since)
        .group_by(OutreachLog.channel, OutreachLog.status)
        .all()
    )

    stats: dict = {}
    for channel, status, count in rows:
        ch = channel or "unknown"
        stats.setdefault(ch, {})[status] = count

    total_sent = sum(
        v.get("sent", 0) for v in stats.values()
    )

    return {
        "period_days": days,
        "total_sent": total_sent,
        "by_channel": stats,
    }


@router.get("/templates")
def list_templates(user=Depends(require_auth)):
    """Return all templates rendered with a sample lead."""
    from app.outreach.templates import TEMPLATES, render
    sample = {
        "full_name": "Rajesh Kumar",
        "company_name": "ABC Instruments Pvt Ltd",
    }
    result = []
    for key, tpl in TEMPLATES.items():
        product = key.split("_")[0] if "_" in key else "all"
        rendered = render(key, sample)
        result.append({
            "key": key,
            "product": product,
            "wa_name": rendered["wa_name"],
            "wa_params_count": len(rendered["wa_params"]),
            "wa_preview": rendered["wa_preview"],
            "email_subject": rendered["email_subject"],
            "email_html": rendered["email_html"],
        })
    return {"templates": result}


@router.get("/log")
def outreach_log(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    """Paginated outreach log."""
    q = db.query(OutreachLog).order_by(OutreachLog.created_at.desc())
    if channel:
        q = q.filter(OutreachLog.channel == channel)
    if status:
        q = q.filter(OutreachLog.status == status)

    total = q.count()
    rows = q.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": r.id,
                "lead_id": str(r.lead_id),
                "channel": r.channel,
                "template_key": r.template_key,
                "message_preview": r.message_preview,
                "status": r.status,
                "wa_message_id": r.wa_message_id,
                "error": r.error,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.get("/cadence")
def cadence_pipeline(
    product: str = Query("all"),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    """
    Cadence pipeline dashboard data.

    Returns:
    - pipeline: counts at each outreach stage (pending → step1 → step2 → exhausted / responses)
    - by_product: per-product breakdown
    - ready: top-50 leads ready for next touch (cooldown elapsed)
    - responses: leads with positive response_status in last 30 days
    - recent_activity: last 10 outreach log entries
    """
    COOLDOWN_DAYS = 3
    cutoff = datetime.utcnow() - timedelta(days=COOLDOWN_DAYS)

    base_q = db.query(Lead).filter(Lead.status != "synthetic")
    if product != "all":
        base_q = base_q.filter(Lead.target_product == product)

    # ── Pipeline stage counts ──────────────────────────────────────────────
    total_in_scope = base_q.count()

    opted_out  = base_q.filter(Lead.outreach_status == "opted_out").count()
    exhausted  = base_q.filter(Lead.outreach_status == "exhausted").count()
    converted  = base_q.filter(Lead.response_status == "converted").count()
    interested = base_q.filter(
        Lead.response_status == "interested",
        Lead.outreach_status != "opted_out",
    ).count()

    # never contacted
    pending = base_q.filter(
        or_(Lead.follow_up_count.is_(None), Lead.follow_up_count == 0),
        Lead.outreach_status.notin_(["exhausted", "opted_out"]),
        or_(Lead.response_status.is_(None), Lead.response_status == "no_response"),
    ).count()

    # touched once
    step1 = base_q.filter(
        Lead.follow_up_count == 1,
        Lead.outreach_status.notin_(["exhausted", "opted_out"]),
        or_(Lead.response_status.is_(None), Lead.response_status == "no_response"),
    ).count()

    # touched twice
    step2 = base_q.filter(
        Lead.follow_up_count == 2,
        Lead.outreach_status.notin_(["exhausted", "opted_out"]),
        or_(Lead.response_status.is_(None), Lead.response_status == "no_response"),
    ).count()

    pipeline = {
        "total": total_in_scope,
        "pending":    {"label": "Not Yet Contacted", "count": pending,    "step": 0},
        "step1":      {"label": "Intro Sent",        "count": step1,      "step": 1},
        "step2":      {"label": "Follow-up 1 Sent",  "count": step2,      "step": 2},
        "exhausted":  {"label": "Exhausted",          "count": exhausted,  "step": -1},
        "interested": {"label": "Interested",         "count": interested, "step": -1},
        "converted":  {"label": "Converted",          "count": converted,  "step": -1},
        "opted_out":  {"label": "Opted Out",          "count": opted_out,  "step": -1},
    }

    # ── Per-product breakdown ──────────────────────────────────────────────
    products = ["calibration", "dms", "mes", "tms", "courier", "ecom"]
    by_product = {}
    for p in products:
        pq = db.query(Lead).filter(Lead.status != "synthetic", Lead.target_product == p)
        by_product[p] = {
            "total":      pq.count(),
            "pending":    pq.filter(or_(Lead.follow_up_count.is_(None), Lead.follow_up_count == 0),
                                    Lead.outreach_status.notin_(["exhausted","opted_out"])).count(),
            "in_seq":     pq.filter(Lead.follow_up_count >= 1,
                                    Lead.outreach_status.notin_(["exhausted","opted_out"])).count(),
            "exhausted":  pq.filter(Lead.outreach_status == "exhausted").count(),
            "interested": pq.filter(Lead.response_status == "interested").count(),
            "converted":  pq.filter(Lead.response_status == "converted").count(),
        }

    # ── Ready to contact (cooldown elapsed, not exhausted) ────────────────
    ready_q = db.query(Lead).filter(
        Lead.status != "synthetic",
        Lead.outreach_status.notin_(["exhausted", "opted_out"]),
        or_(Lead.response_status.is_(None), Lead.response_status == "no_response"),
        or_(Lead.follow_up_count.is_(None), Lead.follow_up_count < 3),
        or_(Lead.phone.isnot(None), Lead.email.isnot(None)),
        or_(Lead.last_contacted_at.is_(None), Lead.last_contacted_at <= cutoff),
    )
    if product != "all":
        ready_q = ready_q.filter(Lead.target_product == product)

    ready_leads = ready_q.order_by(Lead.score.desc()).limit(50).all()

    ready = [
        {
            "id":              str(l.id),
            "full_name":       l.full_name,
            "company_name":    l.company_name,
            "target_product":  l.target_product,
            "phone":           bool(l.phone),
            "email":           bool(l.email),
            "score":           l.score,
            "follow_up_count": l.follow_up_count or 0,
            "last_contacted":  l.last_contacted_at.isoformat() if l.last_contacted_at else None,
            "next_step":       min((l.follow_up_count or 0), 2),
        }
        for l in ready_leads
    ]

    # ── Positive responses (last 30 days) ─────────────────────────────────
    since_30d = datetime.utcnow() - timedelta(days=30)
    resp_leads = (
        db.query(Lead)
        .filter(
            Lead.status != "synthetic",
            Lead.response_status.in_(["interested", "converted"]),
            Lead.updated_at >= since_30d,
        )
        .order_by(Lead.updated_at.desc())
        .limit(20)
        .all()
    )

    responses = [
        {
            "id":             str(l.id),
            "full_name":      l.full_name,
            "company_name":   l.company_name,
            "target_product": l.target_product,
            "response_status": l.response_status,
            "score":          l.score,
            "updated_at":     l.updated_at.isoformat() if l.updated_at else None,
        }
        for l in resp_leads
    ]

    # ── Recent outreach activity ───────────────────────────────────────────
    try:
        recent_log = (
            db.query(OutreachLog)
            .order_by(OutreachLog.created_at.desc())
            .limit(10)
            .all()
        )
        recent_activity = [
            {
                "lead_id":      str(r.lead_id),
                "channel":      r.channel,
                "template_key": r.template_key,
                "status":       r.status,
                "created_at":   r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_log
        ]
    except Exception:
        recent_activity = []

    return {
        "pipeline":        pipeline,
        "by_product":      by_product,
        "ready":           ready,
        "ready_count":     len(ready),
        "responses":       responses,
        "recent_activity": recent_activity,
    }
