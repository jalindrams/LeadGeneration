"""
Pipeline alerts: short daily batch, failing or zero-yield sources.
Always written to exports/pipeline_alerts.log. Sent by Slack/email ONLY when
PIPELINE_ALERTS_ENABLED=true (off by default; owner switches it on).
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.pipeline.models import SourceRun

LOG = Path("exports") / "pipeline_alerts.log"


def _enabled() -> bool:
    return os.getenv("PIPELINE_ALERTS_ENABLED", "false").lower() in ("1", "true", "yes")


def emit(messages: list[str]) -> int:
    if not messages:
        return 0
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for m in messages:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M} {m}\n")
    if _enabled():
        from app.revenue.hot_trigger import _send_slack, _send_email
        body = "\n".join(messages)
        _send_slack(body)
        _send_email(body, subject="Shiplystic lead pipeline alert")
    return len(messages)


def source_health(db: Session, days: int = 3) -> list[str]:
    since = datetime.now() - timedelta(days=days)
    runs = db.execute(select(SourceRun).where(SourceRun.stage == "discover", SourceRun.started_at >= since)
                      .order_by(SourceRun.source, SourceRun.id.desc())).scalars().all()
    by = {}
    for r in runs:
        by.setdefault(r.source, []).append(r)
    out = []
    for src, rs in by.items():
        last2 = rs[:2]
        if len(last2) == 2 and all(r.status == "failed" for r in last2):
            out.append(f"Source {src} failed twice in a row: {(last2[0].error or '')[:160]}")
        elif len(rs) >= 3 and all((r.discovered or 0) == 0 for r in rs[:3]):
            out.append(f"Source {src} found nothing new in its last 3 runs")
    return out


def batch_alert(batch: dict, db: Session | None = None) -> int:
    msgs = []
    if batch.get("delivered", 0) < batch.get("target", 50):
        msgs.append(f"Daily batch {batch.get('date')}: {batch.get('delivered')}/{batch.get('target')} "
                    f"leads delivered. {batch.get('shortfall') or ''}")
    from app.database import SessionLocal
    own = db is None
    db = db or SessionLocal()
    msgs += source_health(db)
    if own:
        db.close()
    return emit(msgs)
