"""
Full OEM dealer-network harvest (DMS source).

Usage:
  python scripts/harvest_oem_dealers.py --oem royal_enfield --states focus
  python scripts/harvest_oem_dealers.py --oem royal_enfield --states all
  python scripts/harvest_oem_dealers.py --oem royal_enfield --states maharashtra,gujarat
  python scripts/harvest_oem_dealers.py --smoke        # 3-page smoke test

Resumable: progress in exports/oem_dealers_progress.json (per oem:state).
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.scrapers.oem_dealers import OemDealerScraper

PROGRESS_FILE = Path(__file__).resolve().parent.parent / "exports" / "oem_dealers_progress.json"

# States covering the DMS profile cities (Pune, Mumbai, Nashik / Ahmedabad,
# Surat / Chennai) — harvested first; --states all does the whole country.
FOCUS_STATES = ["maharashtra", "gujarat", "tamil-nadu"]


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {}


def save_progress(progress: dict):
    PROGRESS_FILE.parent.mkdir(exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oem", default="royal_enfield")
    ap.add_argument("--states", default="focus",
                    help="'focus', 'all', or comma-separated state slugs")
    ap.add_argument("--smoke", action="store_true", help="3-page smoke test only")
    args = ap.parse_args()

    db = SessionLocal()
    # Dealer network is a parked future vertical — no target_product tag
    scraper = OemDealerScraper(db, target_product=None, oem=args.oem)

    if args.smoke:
        stats = scraper.run("maharashtra", "pune", max_pages=3)
        print(f"SMOKE RESULT: {stats}")
        db.close()
        return

    available = scraper.states()
    print(f"[{args.oem}] states in sitemap: {len(available)}, "
          f"total dealer pages: {sum(available.values())}")

    if args.states == "focus":
        targets = [s for s in FOCUS_STATES if s in available]
    elif args.states == "all":
        # focus states first, then the rest by dealer count
        rest = sorted((s for s in available if s not in FOCUS_STATES),
                      key=lambda s: -available[s])
        targets = [s for s in FOCUS_STATES if s in available] + rest
    else:
        targets = [s.strip().lower() for s in args.states.split(",") if s.strip()]

    progress = load_progress()
    total_stored = 0
    for state in targets:
        key = f"{args.oem}:{state}"
        if progress.get(key, {}).get("done"):
            print(f"[skip] {key} already harvested "
                  f"(stored {progress[key].get('stored', '?')})")
            continue
        print(f"[run ] {key} — {available.get(state, '?')} dealer pages")
        try:
            stats = scraper.run(state, city=None)
            progress[key] = {"done": True, **stats}
            total_stored += stats.get("stored", 0)
            save_progress(progress)
            print(f"[done] {key}: {stats}")
        except Exception as e:
            print(f"[FAIL] {key}: {e}")
            progress[key] = {"done": False, "error": str(e)[:200]}
            save_progress(progress)

    print(f"\nHARVEST COMPLETE: {total_stored} new dealers stored this run")
    db.close()


if __name__ == "__main__":
    main()
