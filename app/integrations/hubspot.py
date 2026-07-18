"""
Micraft Growth Engine - HubSpot CRM Integration (Phase 3)
Batch-upserts qualified leads to HubSpot Free Tier via the Contacts v3 API.

Activation: set HUBSPOT_API_KEY in .env (Private App token, pat-...).
HubSpot setup (one-time, in HubSpot UI):
  Settings -> Integrations -> Private Apps -> create app with
  crm.objects.contacts.read + write scopes.
Custom contact properties expected (create in HubSpot, Settings -> Properties):
  lead_score (number), lead_source (single-line text),
  lead_response_status (dropdown: interested/not_interested/no_response/wrong_contact/converted)

Free-tier safe: batch endpoint, 100 records per call, well under API limits.
"""

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Lead
from app.utils.logger import get_logger
from app.utils import yield_tracker

log = get_logger("hubspot")

BASE = "https://api.hubapi.com"


def is_configured() -> bool:
    return bool(settings.HUBSPOT_API_KEY)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.HUBSPOT_API_KEY}",
            "Content-Type": "application/json"}


def _lead_properties(lead: Lead) -> dict:
    first, last = lead.first_name, lead.last_name
    if not (first or last) and lead.full_name:
        parts = lead.full_name.split(None, 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
    props = {
        "company": lead.company_name or "",
        "firstname": first or "",
        "lastname": last or "",
        "jobtitle": lead.title or "",
        "phone": lead.phone or "",
        "city": (lead.location or "").split(",")[0],
        "website": lead.company_url or "",
        "lead_score": str(lead.score or 0),
        "lead_source": lead.source or "",
    }
    if lead.email:
        props["email"] = lead.email
    if lead.response_status:
        props["lead_response_status"] = lead.response_status
    return {k: v for k, v in props.items() if v != ""}


def sync_leads(db: Session, leads: list[Lead], batch_size: int = 100) -> dict:
    """
    Upsert leads to HubSpot in batches. Leads with a hubspot_contact_id are
    updated; others are created (then their id is stored back).

    Returns {created, updated, failed}.
    """
    if not is_configured():
        log.warning("hubspot_not_configured")
        return {"created": 0, "updated": 0, "failed": len(leads),
                "error": "HUBSPOT_API_KEY not set"}

    stats = {"created": 0, "updated": 0, "failed": 0}

    with httpx.Client(headers=_headers(), timeout=30) as client:
        to_create = [l for l in leads if not l.hubspot_contact_id]
        to_update = [l for l in leads if l.hubspot_contact_id]

        for i in range(0, len(to_create), batch_size):
            chunk = to_create[i:i + batch_size]
            payload = {"inputs": [{"properties": _lead_properties(l)} for l in chunk]}
            try:
                resp = client.post(f"{BASE}/crm/v3/objects/contacts/batch/create",
                                   json=payload)
                if resp.status_code == 201:
                    results = resp.json().get("results", [])
                    # Results come back in input order for batch create
                    for lead, res in zip(chunk, results):
                        lead.hubspot_contact_id = res.get("id")
                        lead.status = "pushed" if lead.status == "qualified" else lead.status
                        yield_tracker.increment(db, lead.source, "pushed_to_crm")
                    stats["created"] += len(results)
                    db.commit()
                else:
                    stats["failed"] += len(chunk)
                    log.error("hubspot_batch_create_failed", status=resp.status_code,
                              body=resp.text[:300])
            except httpx.HTTPError as e:
                stats["failed"] += len(chunk)
                log.error("hubspot_batch_create_error", error=str(e))

        for i in range(0, len(to_update), batch_size):
            chunk = to_update[i:i + batch_size]
            payload = {"inputs": [{"id": l.hubspot_contact_id,
                                   "properties": _lead_properties(l)} for l in chunk]}
            try:
                resp = client.post(f"{BASE}/crm/v3/objects/contacts/batch/update",
                                   json=payload)
                if resp.status_code == 200:
                    stats["updated"] += len(chunk)
                    db.commit()
                else:
                    stats["failed"] += len(chunk)
                    log.error("hubspot_batch_update_failed", status=resp.status_code,
                              body=resp.text[:300])
            except httpx.HTTPError as e:
                stats["failed"] += len(chunk)
                log.error("hubspot_batch_update_error", error=str(e))

    log.info("hubspot_sync_complete", **stats)
    return stats
