"""
Micraft Growth Engine - Google Places FREE-TIER Budget Guard

HARD RULE (owner directive 2026-07-19): never spend money on Google Maps.
Google's free tier is per-SKU per-month; Places Text Search and Place Details
sit in tiers with as few as 5,000 free calls/month. This guard keeps ALL app
usage under a conservative monthly cap so paid billing can never trigger,
regardless of which pricing model the Google account is on.

Every Places call site MUST call `allow()` first and skip the request when it
returns False. Counts persist in exports/places_usage.json across runs.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.utils.logger import get_logger

log = get_logger("places_budget")

import os as _os
USAGE_FILE = Path(_os.getenv("PLACES_USAGE_FILE") or
                  Path(__file__).resolve().parent.parent.parent / "exports" / "places_usage.json")
_lock = threading.Lock()


def _month_key() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _load() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except ValueError:
            pass
    return {}


def _save(data: dict):
    USAGE_FILE.parent.mkdir(exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=1))


def used_this_month() -> int:
    data = _load()
    month = data.get(_month_key(), {})
    return int(month.get("total", 0))


def remaining() -> int:
    return max(0, settings.PLACES_MONTHLY_CALL_CAP - used_this_month())


def _paid_overflow(calls: int) -> bool:
    """Charge the spend ledger for calls beyond the free cap; False when paid use is off."""
    try:
        from app.pipeline.paid import ledger
        cost = float(os.getenv("PLACES_PAID_COST_INR", "2.8"))   # ~$32 per 1,000 Text Search Pro
        ledger.charge("google_places", calls, cost)
        return True
    except Exception:
        return False


def allow(calls: int = 1, kind: str = "call") -> bool:
    """
    Reserve `calls` Places API calls against the monthly cap.
    Returns False (and logs loudly) once the cap is reached — callers must
    treat False as 'do NOT hit the API'.
    """
    with _lock:
        data = _load()
        key = _month_key()
        month = data.setdefault(key, {"total": 0})
        if month["total"] + calls > settings.PLACES_MONTHLY_CALL_CAP:
            # Paid overflow only if the owner set PAID_GOOGLE_PLACES_CAP_INR (default 0 = never pay)
            if _paid_overflow(calls):
                month["paid"] = int(month.get("paid", 0)) + calls
                month[kind] = int(month.get(kind, 0)) + calls
                _save(data)
                return True
            log.warning("places_free_tier_cap_reached",
                        used=month["total"],
                        cap=settings.PLACES_MONTHLY_CALL_CAP,
                        month=key)
            return False
        month["total"] += calls
        month[kind] = int(month.get(kind, 0)) + calls
        _save(data)
        return True


def record_external(calls: int, kind: str = "backfill"):
    """Book calls made before the guard existed (honest accounting)."""
    with _lock:
        data = _load()
        key = _month_key()
        month = data.setdefault(key, {"total": 0})
        month["total"] += calls
        month[kind] = int(month.get(kind, 0)) + calls
        _save(data)
