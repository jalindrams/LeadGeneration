"""Orchestration: discovery runs, parallel per-store processing, daily cycle."""
import os
import random
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select

from app.database import SessionLocal, engine, Base
from app.pipeline import stages
from app.pipeline.models import Store, SourceRun
from app.pipeline.sources import REGISTRY
from app.utils.logger import get_logger

log = get_logger("pipeline_runner")

DAILY_TARGET = int(os.getenv("ECOM_DAILY_TARGET", "50"))
# Per-run discovery quotas (Tranco/limit = domains probed; others = candidates returned)
DISCOVERY_QUOTAS = {
    "shopify_app_reviews": 300,
    "tranco_in": 2000,
    "tranco_com": 4000,
    "commoncrawl": 500,
    "new_domains": 600,
    "amazon_sellers": 30,
}
PROCESS_BATCH = int(os.getenv("ECOM_PROCESS_BATCH", "400"))
WORKERS = int(os.getenv("ECOM_WORKERS", "8"))


def ensure_tables():
    import app.models  # noqa: F401
    import app.pipeline.models  # noqa: F401
    Base.metadata.create_all(engine)


def run_discover(source: str, limit: int | None = None) -> SourceRun:
    mod = REGISTRY[source]
    if not limit:
        from app.pipeline.ranking import quota_multiplier
        limit = max(10, int(DISCOVERY_QUOTAS.get(source, 200) * quota_multiplier(source)))
    db = SessionLocal()
    run = SourceRun(source=source, stage="discover")
    db.add(run)
    db.commit()
    try:
        items = mod.discover(db, limit=limit, source=source)
        run.discovered = stages.add_candidates(db, items, source=source)
        if hasattr(mod, "commit_state"):
            mod.commit_state()
        run.processed = len(items)
        run.status = "ok"
    except Exception as e:
        db.rollback()
        run.status, run.error = "failed", f"{type(e).__name__}: {e}"[:2000]
        log.warning("discover_failed", source=source, error=str(e)[:200])
    run.finished_at = datetime.now()
    db.add(run)
    db.commit()
    db.refresh(run)
    db.close()
    return run


def _process_once(store_id: int, wrong_numbers: set, use_places: bool) -> str:
    db = SessionLocal()
    try:
        store = db.get(Store, store_id)
        if store.state == "discovered":
            stages.qualify_store(db, store)
        if store.state == "qualified":
            stages.resolve_store(db, store, use_places=use_places)
        if store.state == "resolved":
            stages.accept_store(db, store, wrong_numbers=wrong_numbers)
        return store.state
    finally:
        db.close()


def process_store(store_id: int, wrong_numbers: set, use_places: bool = True) -> str:
    """Each stage commits, so a retry resumes from the last committed state."""
    for attempt in range(4):
        try:
            return _process_once(store_id, wrong_numbers, use_places)
        except Exception as e:
            if "40001" in str(e) or "deadlock" in str(e).lower():   # deadlock victim: retry
                time.sleep(0.5 + attempt + random.random())
                continue
            log.warning("process_failed", store_id=store_id, error=traceback.format_exc()[-400:])
            return "error"
    return "error"


def run_process(limit: int | None = None, use_places: bool = True) -> dict:
    limit = limit or PROCESS_BATCH
    db = SessionLocal()
    run = SourceRun(source="pipeline", stage="process")
    db.add(run)
    db.commit()
    ids = [i for (i,) in db.execute(
        select(Store.id).where(Store.state.in_(("discovered", "qualified", "resolved")))
        .order_by(Store.discovered_at).limit(limit))]
    wrong = stages._wrong_number_phones(db)
    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(lambda i: process_store(i, wrong, use_places), ids))
    counts = {s: results.count(s) for s in set(results)}
    run.processed = len(ids)
    run.accepted = counts.get("accepted", 0)
    run.rejected = counts.get("rejected", 0)
    run.status, run.finished_at = "ok", datetime.now()
    db.commit()
    db.close()
    return counts


def run_batch(target: int | None = None):
    db = SessionLocal()
    b = stages.build_daily_batch(db, target=target or DAILY_TARGET)
    out = {"date": str(b.batch_date), "delivered": b.delivered, "target": b.target,
           "shortfall": b.shortfall_reason}
    db.close()
    return out


def run_daily(sources: list[str] | None = None) -> dict:
    """Full unattended cycle: discover from every source, process, build the batch."""
    ensure_tables()
    report = {"discover": {}}
    for src in sources or list(DISCOVERY_QUOTAS):
        r = run_discover(src)
        report["discover"][src] = {"status": r.status, "new": r.discovered, "error": r.error}
    report["process"] = run_process()
    report["batch"] = run_batch()
    return report
