"""
Shiplystic store pipeline CLI.

  python scripts/run_pipeline.py init                       # create tables
  python scripts/run_pipeline.py discover --source tranco_in --limit 2000
  python scripts/run_pipeline.py process --limit 400 [--no-places]
  python scripts/run_pipeline.py batch [--target 50]
  python scripts/run_pipeline.py daily                      # discover all + process + batch
  python scripts/run_pipeline.py status
Sources: shopify_app_reviews, tranco_in, tranco_com, commoncrawl, new_domains, amazon_sellers
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.pipeline import runner  # noqa: E402
from app.pipeline.models import Store, SourceRun  # noqa: E402


def status():
    db = SessionLocal()
    rows = db.execute(select(Store.state, func.count()).group_by(Store.state)).all()
    print("stores by state:", dict(rows))
    rej = db.execute(select(Store.reject_reason, func.count()).where(Store.state == "rejected")
                     .group_by(Store.reject_reason).order_by(func.count().desc())).all()
    print("reject reasons:", dict(rej))
    src = db.execute(select(Store.source, Store.state, func.count())
                     .group_by(Store.source, Store.state)).all()
    per = {}
    for s, st, n in src:
        per.setdefault(s, {})[st] = n
    print("by source:", json.dumps(per, indent=1))
    tiers = db.execute(select(Store.tier, func.count()).where(Store.state.in_(("accepted", "delivered")))
                       .group_by(Store.tier)).all()
    print("accepted/delivered by tier:", dict(tiers))
    last = db.execute(select(SourceRun).order_by(SourceRun.id.desc()).limit(8)).scalars().all()
    for r in last:
        print(f"  run {r.id} {r.source}/{r.stage} {r.status} new={r.discovered} processed={r.processed} "
              f"accepted={r.accepted} err={(r.error or '')[:80]}")
    db.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "discover", "process", "batch", "daily", "status"])
    ap.add_argument("--source")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--target", type=int)
    ap.add_argument("--no-places", action="store_true")
    a = ap.parse_args()
    runner.ensure_tables()
    if a.cmd == "discover":
        r = runner.run_discover(a.source, a.limit)
        print(f"{a.source}: {r.status} new={r.discovered} seen={r.processed} {r.error or ''}")
    elif a.cmd == "process":
        print(runner.run_process(a.limit, use_places=not a.no_places))
    elif a.cmd == "batch":
        print(runner.run_batch(a.target))
    elif a.cmd == "daily":
        print(json.dumps(runner.run_daily(), indent=1, default=str))
    elif a.cmd == "status":
        status()
    else:
        print("tables ready")


if __name__ == "__main__":
    main()
