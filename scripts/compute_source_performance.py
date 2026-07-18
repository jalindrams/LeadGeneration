"""
Micraft Growth Engine - Source Performance Computation (Module 7)
Computes per-source scores + SCALE/MAINTAIN/REDUCE/KILL recommendations.
Run weekly (cron) or on demand.

Usage:
  python scripts/compute_source_performance.py [--days 30]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.revenue.source_scorer import compute_source_performance
from app.utils.logger import setup_logging

setup_logging()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        results = compute_source_performance(db, period_days=args.days)
        print(f"\nSource performance (last {args.days} days):\n")
        header = f"{'source':18s} {'raw':>5s} {'qual':>5s} {'cont':>5s} {'conv%':>6s} {'resp%':>6s} {'compl%':>7s} {'score':>6s}  recommendation"
        print(header)
        print("-" * len(header))
        for r in results:
            print(f"{r['source']:18s} {r['total_raw']:>5d} {r['qualified']:>5d} "
                  f"{r['contacted']:>5d} {r['conversion_rate']:>6.1f} {r['response_rate']:>6.1f} "
                  f"{r['data_completeness']:>7.1f} {r['source_score']:>6.1f}  {r['recommendation'].upper()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
