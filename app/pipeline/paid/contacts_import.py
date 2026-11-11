"""
Import owner mobiles bought from a paid provider (EasyLeadz, Lusha, etc.) as a
CSV export, so no vendor API has to be guessed. Columns (header names, any case):
  domain (required), mobile/phone (required), name, title/designation
Each row becomes a StoreContact with phone_type 'paid' and source_url naming the
file, then the store is re-checked. Cost is recorded in the ledger per row.

  python scripts/run_pipeline.py import-contacts --file exports/easyleadz.csv --provider easyleadz --cost 40
"""
import csv
from pathlib import Path

from sqlalchemy import select

from app.pipeline import stages
from app.pipeline.models import Store, StoreContact
from app.pipeline.paid import ledger
from app.pipeline.verify import normalize_mobile


def _col(row: dict, *names):
    low = {k.lower().strip(): v for k, v in row.items() if k}
    for n in names:
        if low.get(n):
            return low[n].strip()
    return None


def import_csv(db, path: str, provider: str, cost_per_row_inr: float) -> dict:
    out = {"rows": 0, "stored": 0, "bad_mobile": 0, "unknown_store": 0, "reaccepted": 0}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out["rows"] += 1
            dom = stages.clean_domain(_col(row, "domain", "website", "company website") or "")
            phone = normalize_mobile(_col(row, "mobile", "phone", "mobile number", "direct dial"))
            if not phone:
                out["bad_mobile"] += 1
                continue
            store = db.execute(select(Store).where(Store.domain == dom)).scalar_one_or_none()
            if not store:
                out["unknown_store"] += 1
                continue
            ledger.charge(provider, 1, cost_per_row_inr, db=db)
            db.add(StoreContact(store_id=store.id, phone=phone, phone_type="paid",
                                name=_col(row, "name", "full name", "contact name"),
                                role=_col(row, "title", "designation", "role") or "owner",
                                source=provider, source_url=f"{provider} export {Path(path).name}",
                                confidence=70))
            out["stored"] += 1
            if store.state == "rejected" and store.reject_reason in ("no_mobile", "no_clean_mobile"):
                store.state, store.reject_reason = "resolved", None
                db.flush()
                if stages.accept_store(db, store) == "accepted":
                    out["reaccepted"] += 1
    db.commit()
    return out
