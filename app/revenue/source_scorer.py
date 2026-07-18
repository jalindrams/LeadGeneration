"""
Micraft Growth Engine - Source Performance Scoring (Module 7)
Computes per-source quality scores over a period and recommends
SCALE / MAINTAIN / REDUCE / KILL.

Formula (locked spec):
  source_score = conversion_rate*0.40 + data_completeness*0.25
               + response_rate*0.25 + avg_lead_score_normalized*0.10
All components normalized to 0-100.

Definitions on available data:
  contacted        leads with any feedback recorded
  reached          contacted leads where a human answered
                   (interested / not_interested / converted)
  conversion_rate  converted+interested / contacted   (early-stage proxy —
                   true 'converted' only, once deals close)
  response_rate    reached / contacted
  data_completeness  avg over leads of (phone,email,title,gst present)
"""

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Lead, SourcePerformance
from app.utils.logger import get_logger

log = get_logger("source_scorer")


def _recommendation(score: float) -> str:
    if score >= 80:
        return "scale"
    if score >= 60:
        return "maintain"
    if score >= 40:
        return "reduce"
    return "kill"


def compute_source_performance(db: Session, period_days: int = 30) -> list[dict]:
    """Compute and upsert source_performance rows for the trailing period."""
    period_end = date.today()
    period_start = period_end - timedelta(days=period_days)
    start_dt = datetime.combine(period_start, datetime.min.time())

    leads = (
        db.query(Lead)
        .filter(Lead.status != "synthetic")
        .filter(Lead.lead_created_at >= start_dt)
        .all()
    )

    by_source: dict[str, list[Lead]] = {}
    for lead in leads:
        by_source.setdefault(lead.source, []).append(lead)

    results = []
    for source, src_leads in by_source.items():
        total_raw = len(src_leads)
        qualified = [l for l in src_leads if l.status in ("qualified", "pushed")]
        contacted = [l for l in src_leads if (l.feedback_count or 0) > 0]
        reached = [l for l in contacted
                   if l.response_status in ("interested", "not_interested", "converted")]
        positive = [l for l in contacted
                    if l.response_status in ("interested", "converted")]
        converted = [l for l in src_leads if l.response_status == "converted"]

        conversion_rate = (len(positive) / len(contacted) * 100) if contacted else 0.0
        response_rate = (len(reached) / len(contacted) * 100) if contacted else 0.0

        def completeness(l: Lead) -> float:
            fields = [bool(l.phone), bool(l.email), bool(l.title), bool(l.gst_number)]
            return sum(fields) / len(fields) * 100

        data_completeness = (sum(completeness(l) for l in src_leads) / total_raw) if total_raw else 0.0
        avg_score = (sum(l.score or 0 for l in src_leads) / total_raw) if total_raw else 0.0

        source_score = (conversion_rate * 0.40 + data_completeness * 0.25
                        + response_rate * 0.25 + avg_score * 0.10)
        rec = _recommendation(source_score)

        row = (
            db.query(SourcePerformance)
            .filter(SourcePerformance.source == source,
                    SourcePerformance.period_start == period_start)
            .first()
        )
        if not row:
            row = SourcePerformance(source=source, period_start=period_start)
            db.add(row)

        row.period_end = period_end
        row.total_raw = total_raw
        row.total_qualified = len(qualified)
        row.total_contacted = len(contacted)
        row.total_converted = len(converted)
        row.conversion_rate = round(conversion_rate, 2)
        row.data_completeness = round(data_completeness, 2)
        row.response_rate = round(response_rate, 2)
        row.avg_lead_score = round(avg_score, 2)
        row.source_score = round(source_score, 2)
        row.recommendation = rec

        results.append({
            "source": source, "total_raw": total_raw, "qualified": len(qualified),
            "contacted": len(contacted), "conversion_rate": round(conversion_rate, 1),
            "response_rate": round(response_rate, 1),
            "data_completeness": round(data_completeness, 1),
            "avg_lead_score": round(avg_score, 1),
            "source_score": round(source_score, 1), "recommendation": rec,
        })
        log.info("source_scored", source=source, score=round(source_score, 1),
                 recommendation=rec)

    db.commit()
    return sorted(results, key=lambda r: -r["source_score"])
