"""
Paid backfill: Store Leads database of online stores (plan Phase 3, item 1).
Auth: header "Authorization: Bearer <key>". List domains filtered by country
(f:cc=IN) and optionally installed apps (f:an=shopify.<token>), paged with
cursor / next_cursor. Contact entries come in domain["contact_info"] as
{type, value, source}.
NOTE: the list endpoint path and response key are taken from Store Leads'
public docs on 2026-11-11 and could not be tested without a key. Run
`python scripts/run_pipeline.py discover --source storeleads --limit 50` first.

Cost is the flat subscription (record it once via SUBSCRIPTION_INR); per-call
cost is 0 but every call still goes through the ledger so it can be capped.
"""
import json
import os
from pathlib import Path

import requests

from app.pipeline.paid import ledger

SOURCE = "storeleads"
PROVIDER = "storeleads"
BASE = "https://storeleads.app/json/api/v1/all/domain"
STATE = Path("exports") / "storeleads_state.json"
# Competitor shipping apps on Shopify, as Store Leads app tokens (edit after checking their app list)
COMPETITOR_APPS = os.getenv("STORELEADS_COMPETITOR_APPS", "")


def enabled() -> bool:
    return bool(os.getenv("STORELEADS_API_KEY")) and ledger.provider_cap(PROVIDER) > 0


def _record_subscription(db):
    sub = float(os.getenv("STORELEADS_SUBSCRIPTION_INR", "0") or 0)
    if sub <= 0:
        return
    marker = Path("exports") / f"storeleads_sub_{ledger._month()}.flag"
    if not marker.exists():
        ledger.charge(PROVIDER, 1, sub, db=db)
        marker.write_text("charged")


def to_candidate(d: dict) -> dict:
    contacts = d.get("contact_info") or []
    phones = [c.get("value") for c in contacts if c.get("type") == "phone"]
    apps = [a.get("name") for a in (d.get("apps") or []) if a.get("name")]
    return {"domain": d.get("name"), "name": d.get("merchant_name") or d.get("title") or d.get("name"),
            "platform": (d.get("platform") or "").lower() or None,
            "source_ref": "storeleads", "paid_phones": phones,
            "note": ("Apps: " + ", ".join(apps[:12])) if apps else None}


def discover(db, limit: int = 500, source: str = SOURCE) -> list[dict]:
    if not enabled():
        raise RuntimeError("storeleads disabled: set STORELEADS_API_KEY and PAID_STORELEADS_CAP_INR")
    _record_subscription(db)
    try:
        cursor = json.loads(STATE.read_text()).get("cursor")
    except Exception:
        cursor = None
    params = {"f:cc": "IN"}
    if COMPETITOR_APPS:
        params.update({"f:an": COMPETITOR_APPS, "f:an:op": "or"})
    found = []
    while len(found) < limit:
        if cursor:
            params["cursor"] = cursor
        ledger.charge(PROVIDER, 1, 0, db=db)
        r = requests.get(BASE, params=params, timeout=60,
                         headers={"Authorization": f"Bearer {os.environ['STORELEADS_API_KEY']}"})
        r.raise_for_status()
        body = r.json()
        items = body.get("domains") or body.get("data") or []
        found += [to_candidate(d) for d in items if d.get("name")]
        cursor = body.get("next_cursor")
        if not cursor or not items:
            break
    global _pending
    _pending = {"cursor": cursor}
    return found[:limit]


_pending: dict | None = None


def commit_state():
    global _pending
    if _pending is not None:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(_pending))
        _pending = None
