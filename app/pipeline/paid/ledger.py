"""
Spend ledger with hard monthly caps (INR), checked BEFORE every paid call.

  PAID_TOTAL_CAP_INR=25000          # all paid providers together, per month
  PAID_<PROVIDER>_CAP_INR=4000      # per provider, e.g. PAID_SERPER_CAP_INR
Both default to 0, which blocks all paid usage.
"""
import os
import threading
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.database import SessionLocal
from app.pipeline.models import SpendLedger

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def _month() -> str:
    return date.today().strftime("%Y-%m")


def provider_cap(provider: str) -> Decimal:
    return Decimal(os.getenv(f"PAID_{provider.upper()}_CAP_INR", "0") or "0")


def total_cap() -> Decimal:
    return Decimal(os.getenv("PAID_TOTAL_CAP_INR", "0") or "0")


def spent(db, provider: str | None = None) -> Decimal:
    q = select(func.coalesce(func.sum(SpendLedger.cost_inr), 0)).where(SpendLedger.month == _month())
    if provider:
        q = q.where(SpendLedger.provider == provider)
    return Decimal(str(db.execute(q).scalar() or 0))


def charge(provider: str, units: int, unit_cost_inr: float, db=None) -> None:
    """Reserve spend before a paid call. Raises BudgetExceeded instead of overspending."""
    cost = Decimal(str(unit_cost_inr)) * units
    own = db is None
    db = db or SessionLocal()
    try:
        with _lock:
            pcap, tcap = provider_cap(provider), total_cap()
            if pcap <= 0 or tcap <= 0:
                raise BudgetExceeded(f"{provider}: paid usage disabled (cap not set)")
            if spent(db, provider) + cost > pcap:
                raise BudgetExceeded(f"{provider}: monthly cap ₹{pcap} reached")
            if spent(db) + cost > tcap:
                raise BudgetExceeded(f"total paid cap ₹{tcap} reached")
            row = db.execute(select(SpendLedger).where(SpendLedger.provider == provider,
                                                       SpendLedger.month == _month())).scalar_one_or_none()
            if not row:
                row = SpendLedger(provider=provider, month=_month(), units=0, cost_inr=0, cap_inr=pcap)
                db.add(row)
            row.units = (row.units or 0) + units
            row.cost_inr = Decimal(str(row.cost_inr or 0)) + cost
            row.cap_inr = pcap
            db.commit()
    finally:
        if own:
            db.close()


def summary(db) -> dict:
    rows = db.execute(select(SpendLedger).where(SpendLedger.month == _month())).scalars().all()
    return {"month": _month(), "total_cap": float(total_cap()), "total_spent": float(spent(db)),
            "providers": [{"provider": r.provider, "units": r.units, "spent": float(r.cost_inr or 0),
                           "cap": float(provider_cap(r.provider))} for r in rows]}
