"""
Shiplystic call outcome codes (one tap each in the caller screen) and what they
mean for the data. The ASP.NET API writes call_logs.call_status with these
codes; sync_outcomes() turns them into suppression entries and lead status.
Keep in sync with web/Api/Domain/Outcomes.cs.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CallLog, Lead
from app.pipeline.models import Suppression

# code: (label, reached_business, lead.response_status, suppress_phone_reason)
OUTCOMES = {
    "no_answer":               ("No answer",                   False, "no_response",    None),
    "wrong_number":            ("Wrong number",                False, "wrong_contact",  "wrong_number"),
    "not_owner":               ("Reached, not decision maker", True,  None,             None),
    "call_back":               ("Asked to call back",          True,  None,             None),
    "already_with_competitor": ("Happy with current shipper",  True,  "not_interested", None),
    "not_interested":          ("Not interested",              True,  "not_interested", None),
    "interested":              ("Interested",                  True,  "interested",     None),
    "demo_booked":             ("Demo booked",                 True,  "interested",     None),
    "signed_up":               ("Signed up",                   True,  "converted",      None),
    "do_not_call":             ("Asked not to be called",      True,  "not_interested", "do_not_call"),
}
POSITIVE = {"interested", "demo_booked", "signed_up"}
# legacy codes from the old calling UI
LEGACY = {"interested": "interested", "not_interested": "not_interested", "no_answer": "no_answer",
          "closed": "wrong_number", "follow_up": "call_back"}


def canonical(code: str | None) -> str | None:
    c = (code or "").strip().lower()
    return c if c in OUTCOMES else LEGACY.get(c)


def apply_outcome(db: Session, lead: Lead, code: str, by: str = "caller") -> None:
    c = canonical(code)
    if not c:
        return
    _, _, response, suppress = OUTCOMES[c]
    if response:
        lead.response_status = response
    # Rescore: ecom leads keep the store-pipeline score with outcome adjustments;
    # other products use the manufacturer scorer (which reads response_status).
    if lead.target_product == "ecom":
        delta = {"wrong_number": -100, "do_not_call": -100, "not_interested": -20,
                 "already_with_competitor": -15, "interested": 10, "demo_booked": 15, "signed_up": 20}.get(c, 0)
        lead.score = max(0, min(100, (lead.score or 0) + delta))
    else:
        from app.processing.scorer import score_and_qualify
        lead.score = score_and_qualify(lead)["score"]
    if suppress and lead.phone:
        phone = lead.phone[-10:]
        exists = db.execute(select(Suppression.id).where(Suppression.kind == "phone",
                                                         Suppression.value == phone)).first()
        if not exists:
            db.add(Suppression(kind="phone", value=phone, reason=suppress, added_by=by))


def sync_outcomes(db: Session, since_id: int = 0) -> dict:
    """Apply suppression/status for call logs written by the API. Returns last id seen."""
    rows = db.execute(select(CallLog, Lead).join(Lead, Lead.id == CallLog.lead_id)
                      .where(CallLog.id > since_id).order_by(CallLog.id)).all()
    last, applied = since_id, 0
    for log, lead in rows:
        apply_outcome(db, lead, log.call_status, by=log.called_by or "caller")
        last, applied = log.id, applied + 1
    db.commit()
    return {"last_id": last, "applied": applied, "at": datetime.now().isoformat()}
