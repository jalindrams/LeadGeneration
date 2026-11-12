"""
Source ranking from call outcomes (plan Phase 2). Per ecom source over the last
30 days: delivered, called, reached, wrong-number and positive rates; a
recommendation; and a discovery quota multiplier the runner applies, so weak
sources are throttled automatically. Needs MIN_CALLS calls before judging.
"""
import json
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CallLog, Lead, SourcePerformance
from app.pipeline.outcomes import OUTCOMES, POSITIVE, canonical

MIN_CALLS = 30
QUOTA_FILE = Path("exports") / "source_quotas.json"
MULTIPLIER = {"scale": 1.5, "maintain": 1.0, "reduce": 0.5, "kill": 0.2, "learning": 1.0}


def recommend(called: int, reach_rate: float, wrong_rate: float, positive_rate: float) -> str:
    if called < MIN_CALLS:
        return "learning"
    if wrong_rate >= 0.35 or reach_rate < 0.15:
        return "kill"
    if positive_rate >= 0.08 and wrong_rate < 0.15:
        return "scale"
    if positive_rate < 0.02 or wrong_rate >= 0.25:
        return "reduce"
    return "maintain"


def source_stats(db: Session, days: int = 30) -> dict:
    since = date.today() - timedelta(days=days)
    leads = db.execute(select(Lead.id, Lead.source).where(
        Lead.target_product == "ecom", Lead.source.like("ecom:%"),
        Lead.lead_created_at >= since)).all()
    by_lead = {lid: src.split(":", 1)[1] for lid, src in leads}
    stats = {src: {"delivered": 0, "called": 0, "reached": 0, "wrong": 0, "positive": 0}
             for src in set(by_lead.values())}
    for src in by_lead.values():
        stats[src]["delivered"] += 1
    if by_lead:
        logs = db.execute(select(CallLog.lead_id, CallLog.call_status)
                          .where(CallLog.lead_id.in_(list(by_lead)))).all()
        last = {}
        for lid, status in logs:          # latest outcome per lead wins
            last[lid] = canonical(status) or last.get(lid)
        for lid, code in last.items():
            s = stats[by_lead[lid]]
            s["called"] += 1
            if code and OUTCOMES[code][1]:
                s["reached"] += 1
            if code == "wrong_number":
                s["wrong"] += 1
            if code in POSITIVE:
                s["positive"] += 1
    for s in stats.values():
        c = s["called"] or 1
        s["reach_rate"] = round(s["reached"] / c, 3)
        s["wrong_rate"] = round(s["wrong"] / c, 3)
        s["positive_rate"] = round(s["positive"] / c, 3)
        s["recommendation"] = recommend(s["called"], s["reach_rate"], s["wrong_rate"], s["positive_rate"])
    return stats


def recompute(db: Session | None = None, days: int = 30) -> dict:
    from app.database import SessionLocal
    own = db is None
    db = db or SessionLocal()
    stats = source_stats(db, days)
    start, end = date.today() - timedelta(days=days), date.today()
    for src, s in stats.items():
        name = f"ecom:{src}"
        row = db.execute(select(SourcePerformance).where(SourcePerformance.source == name,
                                                         SourcePerformance.period_start == start)
                         ).scalar_one_or_none() or SourcePerformance(source=name, period_start=start)
        row.period_end = end
        row.total_raw = s["delivered"]
        row.total_qualified = s["delivered"]
        row.total_contacted = s["called"]
        row.total_converted = s["positive"]
        row.conversion_rate = round(100 * s["positive_rate"], 2)
        row.response_rate = round(100 * s["reach_rate"], 2)
        row.recommendation = s["recommendation"]
        db.add(row)
    db.commit()
    QUOTA_FILE.parent.mkdir(exist_ok=True)
    QUOTA_FILE.write_text(json.dumps({src: MULTIPLIER[s["recommendation"]] for src, s in stats.items()},
                                     indent=1))
    if own:
        db.close()
    return stats


def quota_multiplier(source: str) -> float:
    try:
        return float(json.loads(QUOTA_FILE.read_text()).get(source, 1.0))
    except Exception:
        return 1.0
