"""
Micraft Growth Engine - Outreach Cadence Engine

Sequencer rules:
  Step 0 (intro):      WhatsApp if phone exists, else Email
  Step 1 (followup_1): WhatsApp if phone, else Email  [min 3 days after step 0]
  Step 2 (final):      Email if email, else WhatsApp  [min 7 days after step 1]
  → After step 2: mark outreach_status = exhausted

Eligibility rules (lead is skipped if ANY fail):
  - outreach_status NOT IN (exhausted, opted_out)
  - response_status NOT IN (interested, converted)  [don't re-contact warm responses]
  - has phone OR email
  - cooldown: min N days since last_contacted_at (configurable, default 3)
  - follow_up_count < 3

Dry-run mode: calculates what WOULD be sent, writes nothing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import Lead, OutreachLog
from app.outreach.templates import select_template, render
from app.outreach.whatsapp import WhatsAppClient
from app.outreach.email_sender import EmailSender
from app.utils.logger import get_logger

log = get_logger("outreach_cadence")

COOLDOWN_DAYS = 3        # minimum days between any two outreach touches
MAX_FOLLOW_UPS = 3       # total touches before marking exhausted
DO_NOT_CONTACT = {"exhausted", "opted_out"}
SKIP_RESPONSE = {"interested", "converted"}  # already warm — handled by sales rep


def _eligible_leads(
    db: Session,
    product: Optional[str],
    tier: Optional[str],
    limit: int,
    cooldown_days: int,
) -> list[Lead]:
    cutoff = datetime.utcnow() - timedelta(days=cooldown_days)

    q = db.query(Lead).filter(
        Lead.outreach_status.notin_(list(DO_NOT_CONTACT)),
        or_(Lead.response_status.notin_(list(SKIP_RESPONSE)),
            Lead.response_status.is_(None)),
        or_(
            Lead.phone.isnot(None),
            Lead.email.isnot(None),
        ),
        or_(
            Lead.last_contacted_at.is_(None),
            Lead.last_contacted_at <= cutoff,
        ),
        or_(
            Lead.follow_up_count.is_(None),
            Lead.follow_up_count < MAX_FOLLOW_UPS,
        ),
    )

    if product and product != "all":
        q = q.filter(Lead.target_product == product)

    if tier == "hot":
        q = q.filter(Lead.score >= 70)
    elif tier == "warm":
        q = q.filter(Lead.score >= 40, Lead.score < 70)

    # Hot leads first, then by score desc
    q = q.order_by(Lead.score.desc())

    if limit:
        q = q.limit(limit)

    return q.all()


def _step_for_lead(lead: Lead) -> int:
    """Determine which outreach step this lead is on."""
    count = lead.follow_up_count or 0
    return min(count, 2)


def _send_outreach(
    lead: Lead,
    step: int,
    wa_client: WhatsAppClient,
    email_client: EmailSender,
    dry_run: bool,
    db: Session,
) -> dict:
    """Execute one outreach touch for a lead. Returns result dict."""
    template_key = select_template(
        {"target_product": lead.target_product, "source": lead.source},
        step=step,
    )
    rendered = render(template_key, {
        "full_name": lead.full_name,
        "company_name": lead.company_name,
        "target_product": lead.target_product,
        "source": lead.source,
    })

    # Channel selection: WA first (step 0,1); Email first (step 2)
    channel_order = (
        ["email", "whatsapp"] if step == 2
        else ["whatsapp", "email"]
    )

    result = {"lead_id": str(lead.id), "template_key": template_key,
               "channel": None, "success": False, "message_id": None, "error": None}

    for channel in channel_order:
        if channel == "whatsapp" and lead.phone:
            if dry_run:
                result.update({"channel": "whatsapp", "success": True,
                                "preview": rendered["wa_preview"][:120]})
                break
            r = wa_client.send_template(
                lead.phone, rendered["wa_name"], rendered["wa_params"])
            result.update({"channel": "whatsapp", **r})
            if r["success"]:
                break

        elif channel == "email" and lead.email:
            if dry_run:
                result.update({"channel": "email", "success": True,
                                "preview": rendered["email_subject"]})
                break
            r = email_client.send(
                lead.email, rendered["email_subject"], rendered["email_html"])
            result.update({"channel": "email", **r})
            if r["success"]:
                break

    if dry_run:
        return result

    # Persist to outreach_log and update lead
    now = datetime.utcnow()
    log_entry = OutreachLog(
        lead_id=lead.id,
        channel=result.get("channel"),
        template_key=template_key,
        message_preview=(rendered.get("wa_preview") or rendered.get("email_subject", ""))[:200],
        status="sent" if result["success"] else "failed",
        wa_message_id=result.get("message_id"),
        error=result.get("error"),
        sent_at=now if result["success"] else None,
    )
    db.add(log_entry)

    if result["success"]:
        lead.last_contacted_at = now
        if not lead.first_contacted_at:
            lead.first_contacted_at = now
        lead.follow_up_count = (lead.follow_up_count or 0) + 1
        lead.last_outreach_channel = result.get("channel")
        if lead.follow_up_count >= MAX_FOLLOW_UPS:
            lead.outreach_status = "exhausted"
        else:
            lead.outreach_status = "contacted"
        db.add(lead)

    db.commit()
    return result


def run_batch(
    db: Session,
    product: str = "all",
    tier: str = "all",
    limit: int = 50,
    cooldown_days: int = COOLDOWN_DAYS,
    dry_run: bool = False,
) -> dict:
    """
    Main entry point: send outreach to a batch of eligible leads.

    Returns summary dict with counts and per-lead results.
    """
    leads = _eligible_leads(db, product, tier, limit, cooldown_days)
    log.info("cadence_batch_start", product=product, tier=tier,
             eligible=len(leads), dry_run=dry_run)

    wa_client = WhatsAppClient()
    email_client = EmailSender()

    sent_wa = sent_email = failed = 0
    results = []

    for lead in leads:
        step = _step_for_lead(lead)
        r = _send_outreach(lead, step, wa_client, email_client, dry_run, db)
        results.append(r)

        if r["success"]:
            if r.get("channel") == "whatsapp":
                sent_wa += 1
            else:
                sent_email += 1
        else:
            failed += 1

    summary = {
        "eligible": len(leads),
        "sent_whatsapp": sent_wa,
        "sent_email": sent_email,
        "failed": failed,
        "dry_run": dry_run,
        "results": results,
    }
    log.info("cadence_batch_done", **{k: v for k, v in summary.items() if k != "results"})
    return summary
