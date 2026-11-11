"""
Unattended scheduler for the Shiplystic store pipeline (runs on the owner's PC
or a server, next to SQL Server). Start it once; it keeps running.

  python scripts/pipeline_worker.py            # run forever on the schedule below
  python scripts/pipeline_worker.py --once     # run the full daily cycle now and exit

Schedule (local time):
  05:15  discovery from every source (quotas in app/pipeline/runner.py)
  :40    every hour 06:40-22:40, process the backlog (qualify -> resolve -> accept)
  07:30  build today's batch of 50 and assign to callers; alert if short
  Sun 21:10  recompute source ranking from call outcomes (throttles weak sources)
  :05    every hour, apply call outcomes (wrong number / do-not-call -> suppression)
  07:45  queue WhatsApp intros for Tier A (queued for a person to send; never sent here)
Windows auto-start: see run_pipeline_worker.bat (register it in Task Scheduler "At log on").
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: E402

from app.pipeline import runner  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

log = get_logger("pipeline_worker")


def job_discover():
    for src in runner.DISCOVERY_QUOTAS:
        r = runner.run_discover(src)
        log.info("discover", source=src, status=r.status, new=r.discovered, error=(r.error or "")[:120])


def job_process():
    log.info("process", result=runner.run_process())


def job_batch():
    out = runner.run_batch()
    log.info("batch", **{k: str(v) for k, v in out.items()})
    try:
        from app.pipeline import alerts
        alerts.batch_alert(out)
    except ImportError:
        pass


OUTCOME_CURSOR = os.path.join("exports", "outcome_sync.json")


def job_outcomes():
    from app.database import SessionLocal
    from app.pipeline.outcomes import sync_outcomes
    try:
        since = json.load(open(OUTCOME_CURSOR))["last_id"]
    except Exception:
        since = 0
    db = SessionLocal()
    res = sync_outcomes(db, since)
    db.close()
    json.dump(res, open(OUTCOME_CURSOR, "w"))
    log.info("outcomes", **{k: str(v) for k, v in res.items()})


def job_queue_intros():
    from app.database import SessionLocal
    from app.pipeline.outreach_queue import queue_intros
    db = SessionLocal()
    log.info("intros_queued", count=queue_intros(db))   # queued only, never sent
    db.close()


def job_rank():
    try:
        from app.pipeline import ranking
        log.info("ranking", result=ranking.recompute())
    except ImportError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    runner.ensure_tables()
    if a.once:
        print(json.dumps(runner.run_daily(), indent=1, default=str))
        return
    sched = BlockingScheduler(job_defaults={"coalesce": True, "max_instances": 1,
                                            "misfire_grace_time": 3600})
    sched.add_job(job_discover, "cron", hour=5, minute=15, id="discover")
    sched.add_job(job_process, "cron", hour="6-22", minute=40, id="process")
    sched.add_job(job_batch, "cron", hour=7, minute=30, id="batch")
    sched.add_job(job_rank, "cron", day_of_week="sun", hour=21, minute=10, id="rank")
    sched.add_job(job_outcomes, "cron", minute=5, id="outcomes")
    sched.add_job(job_queue_intros, "cron", hour=7, minute=45, id="intros")
    log.info("worker_started", jobs=[j.id for j in sched.get_jobs()])
    sched.start()


if __name__ == "__main__":
    main()
